import copy
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from engines.cto_engine import compute_cto_chart, compute_cto_snapshot, CTO_HISTORY_BARS
from decision_pipeline import evaluate_decision, new_state, input_quality, fresh_context, replay_recorded
from opportunities import assess_variant, build_opportunity, meaningful_transition
from opportunity_journal import OpportunityJournal
from backtest.cto_study import outcome, run_study
from test_signal_reliability import candles, favorable, CONTEXT


def candidate(**changes):
    row = dict(favorable(), symbol="BTC/USDT", timeframe="4h", signal="LIGHT_LONG", baseline_signal="LIGHT_LONG",
               signal_status="ready", signal_bar_close_time=1440000, decision_price=150,
               structure={"swing_low":100,"swing_high":200}, evidence_coverage=.8,
               cto={"data_quality":"ready","state":"strong_up","direction":"up","direction_age_bars":2})
    row.update(changes)
    return row


class CTOTests(unittest.TestCase):
    def test_chart_scanner_parity_and_unfinished_bar_isolation(self):
        data=candles(700);asof=data['timestamp'][-1]+1000
        snapshot=compute_cto_snapshot(data,'4h',asof);chart=compute_cto_chart(data,'4h',asof)
        self.assertEqual(snapshot,chart['cto_snapshot'])
        self.assertEqual(snapshot['history_bars'],CTO_HISTORY_BARS)
        self.assertEqual(snapshot['fast'],chart['cto_fast'][-1]['value'])
        data['high'][-1]*=100
        self.assertEqual(snapshot,compute_cto_snapshot(data,'4h',asof))
        self.assertTrue(chart['cto_preview']['provisional'])
        self.assertGreater(chart['cto_preview']['time'],snapshot['time'])

    def test_missing_gaps_invalid_and_short_history(self):
        for data in (candles(10),None):
            self.assertEqual(compute_cto_snapshot(data,'4h',1e15)['data_quality'],'unavailable')
        data=candles(100);data['timestamp'][40]+=1
        self.assertEqual(compute_cto_snapshot(data,'4h',1e15)['reason'],'candle gaps')
        data=candles(100);data['close'][70]=np.nan
        self.assertEqual(compute_cto_snapshot(data,'4h',1e15)['data_quality'],'unavailable')

    def test_confirmation_persistence_shorts_reversals_and_exits(self):
        row=candidate()
        self.assertEqual(assess_variant(row,'cto_confirmation',2)['signal'],'LIGHT_LONG')
        self.assertEqual(assess_variant(row,'cto_confirmation',3)['signal'],'WAIT')
        row['baseline_signal']='LIGHT_SHORT'
        self.assertEqual(assess_variant(row,'cto_veto',2)['status'],'blocked')
        row['cto']['direction']='down'
        self.assertEqual(assess_variant(row,'cto_confirmation',2)['signal'],'LIGHT_SHORT')
        row.update(baseline_signal='LIGHT_LONG',regime='CAP')
        self.assertEqual(assess_variant(row,'cto_confirmation')['status'],'emerging')
        row.update(baseline_signal='TRIM',entry_blocked=True,cto={})
        self.assertEqual(assess_variant(row,'cto_confirmation')['status'],'risk_warning')


class PipelineTests(unittest.TestCase):
    def test_stale_future_and_missing_inputs(self):
        q=input_quality({'funding':{'observed_at':1},'macro':{'observed_at':10001}},10000)
        self.assertEqual(q['funding']['status'],'stale');self.assertEqual(q['macro']['status'],'future')
        self.assertIsNone(fresh_context(CONTEXT,q)['positioning'])

    def test_recorded_parity_after_json_roundtrip_with_history(self):
        state=new_state()
        for i in range(4):
            row=candidate(signal_bar_close_time=1440000+i*14400);asof=row['signal_bar_close_time']+10
            metadata={k:{'source':'fixture','observed_at':asof} for k in ('funding','sentiment','stablecoin')}
            evaluate_decision(row,dict(consensus={'consensus':'RISK-ON'},**CONTEXT),state,as_of=asof,metadata=metadata)
            reproduced=replay_recorded(json.loads(json.dumps(row)))
            for key in ('signal','signal_score','signal_first_seen_at','conditions_detail','cto_shadow','regime_changes_7d'):
                self.assertEqual(reproduced[key],row[key],key)
        self.assertEqual(len(state.signal_history['BTC/USDT:4h']),4)

    def test_stale_candles_suppress_entries(self):
        row=candidate()
        evaluate_decision(row,{'consensus':{'consensus':'RISK-ON'}},new_state(),as_of=row['signal_bar_close_time']+30000)
        self.assertEqual(row['signal'],'WAIT');self.assertEqual(row['input_quality']['candles']['status'],'stale')


class LifecycleTests(unittest.TestCase):
    def test_poll_expiry_and_invalidation(self):
        row=candidate();now=row['signal_bar_close_time'];first=build_opportunity(row,None,as_of=now)
        again=build_opportunity(row,first,as_of=now+10)
        self.assertEqual(first['id'],again['id']);self.assertFalse(meaningful_transition(first,again))
        self.assertEqual(build_opportunity(row,first,as_of=now+4*14400)['status'],'expired')
        row['decision_price']=99
        self.assertEqual(build_opportunity(row,first,as_of=now+14400)['status'],'invalidated')
        row.update(baseline_signal='WAIT',signal='WAIT');lost=build_opportunity(row,first,as_of=now+14400)
        self.assertEqual(lost['id'],first['id']);self.assertEqual(lost['invalidation_level'],100)

    def test_journal_restart_and_deduplication(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'journal.db';row=candidate(decision_version='decision-2')
            opportunity=build_opportunity(row,None,as_of=row['signal_bar_close_time']);journal=OpportunityJournal(path)
            self.assertTrue(journal.record(row,opportunity,as_of=1));self.assertFalse(journal.record(row,opportunity,as_of=2))
            journal.close();journal=OpportunityJournal(path)
            self.assertEqual(journal.previous(row['symbol'],'4h'),opportunity);self.assertEqual(len(journal.recent()),1)
            self.assertEqual(journal.db.execute('select count(*) from snapshots').fetchone()[0],1);journal.close()


class StudyTests(unittest.TestCase):
    def test_next_open_costs_and_unknown_funding(self):
        row=candidate();t=row['signal_bar_close_time']
        bars=[dict(time=t+i*14400,open=160,high=170,low=155,close=165) for i in range(6)]
        trade=outcome(row,bars);self.assertAlmostEqual(trade['entry'],160*1.0005)
        self.assertFalse(trade['funding_known']);self.assertLess(trade['net_return'],165/160-1)
        row['evaluated_at']=t+10;self.assertIsNone(outcome(row,bars))
        bars.append(dict(bars[-1],time=t+6*14400));self.assertIsNotNone(outcome(row,bars))

    def test_short_funding_and_gap_stop(self):
        row=candidate(baseline_signal='LIGHT_SHORT',signal='LIGHT_SHORT');t=row['signal_bar_close_time']
        bars=[dict(time=t+i*14400,open=150,high=160,low=140,close=150) for i in range(6)]
        funded=outcome(row,bars,funding=[dict(time=t+3600,rate=.01)],funding_coverage=[t,t+86400])
        self.assertAlmostEqual(funded['net_return']-outcome(row,bars)['net_return'],.01)
        bars[1].update(open=210,high=215,low=205,close=210);trade=outcome(row,bars)
        self.assertTrue(trade['stopped']);self.assertAlmostEqual(trade['exit'],210*1.0005)

    def test_holdout_isolation_and_promotion_refusal(self):
        rows=[];bars=[]
        for i in range(200):
            t=(100+i)*14400;rows.append(candidate(signal_bar_close_time=t));bars.append(dict(time=t,open=150,high=152,low=149,close=151))
        report=run_study(dict(decisions=rows,candles={'BTC/USDT':bars},context_complete=False),horizon=2)
        self.assertFalse(report['promotion']['approved'])
        changed=copy.deepcopy(bars);boundary=report['partitions']['holdout'][0]
        for bar in changed:
            if bar['time']>=boundary:bar.update(high=180,close=170)
        altered=run_study(dict(decisions=rows,candles={'BTC/USDT':changed},context_complete=False),horizon=2)
        self.assertEqual(report['selected'],altered['selected']);self.assertEqual(report['train'],altered['train'])

if __name__=='__main__':unittest.main()

class GateTests(unittest.TestCase):
    def test_policy_requires_approved_unchanged_report(self):
        from cto_policy import validate_artifact
        from backtest.cto_study import fingerprint, promotion_gate, STUDY_VERSION
        from opportunities import POLICY_VERSION
        from decision_pipeline import VERSION
        metrics=dict(n=60,funding_coverage=1,lower_95_mean=.001,net_expectancy=.002,basket_max_drawdown=.01)
        selected=dict(metrics=metrics,cohorts={'symbol':{s:dict(metrics,n=20) for s in ['BTC','ETH','SOL']},'regime':{},'setup':{}})
        baseline=dict(metrics=dict(metrics,net_expectancy=.001,basket_max_drawdown=.02))
        part=dict(selected=selected,baseline=baseline,incremental_edge=dict(blocks=12,lower_95=.0005))
        report=dict(version=STUDY_VERSION,decision_version=VERSION,selected=['cto_confirmation',2],holdout_fresh=True,
                    context_complete=True,recorded_parity_verified=True,validation=part,holdout=part,
                    scope=dict(symbols=['BTC'],timeframe='4h'))
        artifact=dict(decision_version=VERSION,policy_version=POLICY_VERSION,report_hash=fingerprint(report),
                      policy=report['selected'],scope=report['scope'])
        self.assertTrue(promotion_gate(report)['approved'])
        self.assertEqual(validate_artifact(artifact,report),('cto_confirmation',2))
        report['holdout_fresh']=False
        self.assertFalse(promotion_gate(report)['approved'])
        with self.assertRaises(ValueError):validate_artifact(artifact,report)

    def test_repeated_regime_corrections_do_not_manufacture_chop(self):
        state=new_state();row=candidate();asof=row['signal_bar_close_time']
        evaluate_decision(row,{'consensus':{}},state,as_of=asof)
        row['signal_bar_close_time']+=14400
        for i in range(5):
            row['regime']='ACCUM' if i%2 else 'MARKUP'
            evaluate_decision(row,{'consensus':{}},state,as_of=asof+14400+i)
            self.assertLessEqual(row['regime_changes_7d'],1)

class ChartRouteTests(unittest.TestCase):
    def test_chart_window_and_completed_cto_share_the_same_input(self):
        # Isolate this route from web-server startup and optional trading clients.
        import ast, asyncio, time
        from unittest.mock import AsyncMock, patch
        source=Path(__file__).resolve().parents[1]/'main.py'
        node=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.AsyncFunctionDef) and n.name=='chart_data')
        node.decorator_list=[]
        scope={'Query':lambda value,**kw:value,'time':time,'HTTPException':RuntimeError,
               'logger':__import__('logging').getLogger('test')}
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),scope)
        data=candles(700);weekly=candles(100,'1w');asof=data['timestamp'][-1]/1000+1
        async def fetch(symbol,tf,**kw):return weekly if tf=='1w' else data
        with patch('data_fetcher.fetch_ohlcv',side_effect=fetch),patch('time.time',return_value=asof):
            result=asyncio.run(scope['chart_data']('BTC/USDT','4h',50))
        self.assertEqual(len(result['candles']),50)
        self.assertEqual(result['cto_snapshot'],compute_cto_snapshot(data,'4h',asof*1000))
        self.assertGreaterEqual(result['cto_fast'][0]['time'],result['candles'][0]['time'])
        self.assertLess(result['cto_fast'][-1]['time'],result['candles'][-1]['time'])
