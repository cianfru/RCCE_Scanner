import json
import tempfile
import unittest
from pathlib import Path
from executor_shadow import ShadowStudy,volatility

SIZING={'STRONG_LONG':{'STRONG':1.0}}
NOW=1800000000

class ShadowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'study.json';self.study=ShadowStudy(self.path,1000,SIZING)
    def tick(self,offset=0,price=100,signal='STRONG_LONG',atr=3,observed=None):
        now=NOW+offset
        self.study.process([{'symbol':'BTC/USDT','price':price,'signal':signal,'confluence':{'label':'STRONG'}}],{'BTC/USDT'},{'BTC/USDT':{'atr':atr,'observed_at':now if observed is None else observed}},now,allocation_count=10)
    def portfolios(self):return self.study.state['portfolios']

    def test_fresh_start_sizing_and_fixed_atr_stop(self):
        self.tick(atr=8)
        p=self.portfolios();base=p['baseline']['positions']['BTC/USDT'];alt=p['reset_4h_atr']['positions']['BTC/USDT']
        self.assertEqual(base['cost'],100)
        self.assertAlmostEqual(alt['stop_fraction'],.12)
        self.assertAlmostEqual(alt['planned_risk_usd'],base['planned_risk_usd'])
        self.tick(100,101,atr=1)
        self.assertEqual(self.portfolios()['reset_4h_atr']['positions']['BTC/USDT']['stop_price'],88)

    def test_reset_and_cooldown_both_required_and_survive_restart(self):
        self.tick();self.tick(100,90) # stopped
        self.tick(200,100)
        self.assertIn('BTC/USDT',self.portfolios()['baseline']['positions'])
        self.assertNotIn('BTC/USDT',self.portfolios()['reset_4h']['positions'])
        self.tick(15000,100) # cooldown passed, but no reset
        self.assertNotIn('BTC/USDT',self.portfolios()['reset_4h']['positions'])
        self.tick(15100,100,'WAIT')
        self.study=ShadowStudy(self.path,1000,SIZING)
        self.tick(15200,100)
        self.assertIn('BTC/USDT',self.portfolios()['reset_4h']['positions'])
        self.assertEqual(self.portfolios()['reset_4h']['closed'],1)

    def test_missing_volatility_only_blocks_atr_variant(self):
        self.tick(atr=None)
        self.assertIn('BTC/USDT',self.portfolios()['baseline']['positions'])
        self.assertFalse(self.portfolios()['reset_4h_atr']['positions'])

    def test_be_exit_and_costs_use_observed_fill_not_stop_price(self):
        self.tick();self.tick(100,106);self.tick(200,99)
        p=self.portfolios()['baseline']
        self.assertEqual(p['closed'],1)
        self.assertAlmostEqual(p['realized'],-1)
        self.assertAlmostEqual(p['fees'],.0995)
        self.assertEqual(p['trades'][-1]['exit_signal'],'BE_STOP')
        self.assertEqual(p['trades'][-1]['exit_price'],99)

    def test_stale_prices_never_open_and_stale_marks_withhold_total(self):
        self.tick(observed=NOW-22000)
        self.assertFalse(self.portfolios()['baseline']['positions'])
        self.tick(100)
        self.assertIsNone(self.study.status(NOW+23000)['portfolios'][0]['combined'])

    def test_corrupt_or_changed_configuration_does_not_reset_history(self):
        self.path.write_text('{invalid')
        study=ShadowStudy(self.path,1000,SIZING)
        self.assertTrue(study.status(NOW)['error']);self.assertEqual(self.path.read_text(),'{invalid')
        self.path.unlink();self.tick();original=self.path.read_text()
        changed=ShadowStudy(self.path,2000,SIZING)
        self.assertTrue(changed.error);self.assertEqual(self.path.read_text(),original)

    def test_cash_budget_prevents_unfunded_entries(self):
        rows=[{'symbol':str(i),'price':100,'signal':'STRONG_LONG','confluence':{'label':'STRONG'}} for i in range(15)]
        self.study.process(rows,{str(i) for i in range(15)},{str(i):{'atr':4,'observed_at':NOW} for i in range(15)},NOW,allocation_count=10)
        self.assertEqual(len(self.portfolios()['baseline']['positions']),9)

    def test_closed_candle_volatility_and_gap_handling(self):
        timestamps=[(NOW-14400*(16-i))*1000 for i in range(17)]
        data={'timestamp':timestamps,'high':[102]*17,'low':[98]*17,'close':[100]*17}
        data['high'][-1]=9999 # open candle cannot affect ATR
        self.assertEqual(volatility(data,NOW),4)
        data['timestamp'][5]+=1000
        self.assertIsNone(volatility(data,NOW))

class HookTests(unittest.IsolatedAsyncioTestCase):
    async def test_shadow_failure_does_not_prevent_active_processing(self):
        from unittest.mock import patch,AsyncMock,Mock
        from executor import Executor
        from data_fetcher import _ohlcv_store
        with tempfile.TemporaryDirectory() as directory, patch('executor._STATE_FILE',Path(directory)/'executor.json'):
            executor=Executor();executor.initialized=True;executor.enabled=True
            executor.pair_map={'BTC/USDT':'BTC'};executor.whitelist=['BTC/USDT']
            executor._process_signal=AsyncMock(return_value=None);executor._save_state=Mock()
            executor.shadow.process=Mock(side_effect=RuntimeError('research error'))
            with patch.object(_ohlcv_store,'get',return_value=None),patch.object(_ohlcv_store,'observed_at',return_value=NOW),patch('executor.logger'):
                await executor.process_scan_results([{'symbol':'BTC/USDT','signal':'STRONG_LONG','price':100}])
            executor._process_signal.assert_awaited_once()
            self.assertIn('research error',executor.shadow.error)
