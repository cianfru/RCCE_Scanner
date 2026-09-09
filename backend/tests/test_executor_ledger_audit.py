import unittest
from unittest.mock import patch
import executor_marks
from executor_marks import midpoint, converted_native_mark
from executor_ledger_audit import AUDITED_UNIT_MISMATCHES, closure_issue
from executor_performance import performance

class LedgerAuditTests(unittest.TestCase):
    def test_only_evidenced_closures_are_flagged(self):
        for symbol, entered, exited, entry, exit_price in AUDITED_UNIT_MISMATCHES:
            row=dict(symbol=symbol,entry_time=entered+.1,exit_time=exited+.1,entry_price=entry,exit_price=exit_price)
            self.assertIsNotNone(closure_issue(row))
            self.assertIsNone(closure_issue({**row,'entry_time':entered+86400}))
            self.assertIsNone(closure_issue({**row,'exit_price':entry*.0001}))
        self.assertIsNone(closure_issue({'entry_time':None}))

    def test_flagged_record_is_preserved_but_excluded_from_all_performance(self):
        symbol,entered,exited,entry,exit_price=AUDITED_UNIT_MISMATCHES[0]
        row=dict(symbol=symbol,entry_time=entered,exit_time=exited,entry_price=entry,exit_price=exit_price,pnl_usd=-120)
        result=performance([], [row,{**row,'symbol':'BTC/USDT','pnl_usd':-30}],{},1000,1800000000)
        self.assertEqual(result['realized_pnl_usd'],-30)
        self.assertEqual(result['recorded_realized_pnl_usd'],-150)
        self.assertEqual(result['flagged_closed_trades'],1)
        self.assertEqual(result['unflagged_realized_pnl_usd'],-30)
        self.assertEqual(result['combined_pnl_usd'],-30)
        self.assertEqual(result['closed_trades'],1)
        self.assertEqual(result['losses'],1)
        self.assertEqual(result['excluded_closed_trades'],1)
        self.assertEqual(result['realized_curve'][-1]['pnl_usd'],-30)
        self.assertEqual(sum(x['pnl_usd'] for x in result['monthly_realized']),-30)
        self.assertEqual([t['symbol'] for t in result['included_closed_trades']],['BTC/USDT'])
        self.assertIsNone(result['estimated_equity_usd'])
        self.assertIsNone(result['return_on_starting_capital_pct'])
        self.assertEqual(row['pnl_usd'],-120)

    def test_unit_conversion_is_limited_to_verified_entries(self):
        for symbol,(entered,entry,native) in executor_marks.VERIFIED_TOKEN_ENTRIES.items():
            position=dict(symbol=symbol,entry_time=entered+.1,entry_price=entry,cost_usd=100,peak_unrealized_pct=200000)
            marks={native:{'price':entry*2000,'observed_at':1800000000}}
            mark=converted_native_mark(position,marks)
            result=performance([position],[],{symbol:mark},1000,1800000000)
            self.assertAlmostEqual(result['unrealized_pnl_usd'],100)
            self.assertIsNone(converted_native_mark({**position,'entry_time':entered+10},marks))
            self.assertIsNone(converted_native_mark({**position,'entry_price':entry*1000},marks))
            self.assertIsNone(converted_native_mark(position,{}))

    def test_reference_quotes_require_usable_two_sided_market(self):
        self.assertEqual(midpoint('10','10.1','100'),10.05)
        for quote in [(0,10,100),(11,10,100),(10,12,100),(10,10,0),('nan',10,100),(10,10,'inf'),(None,10,100)]:
            self.assertIsNone(midpoint(*quote))

class ReferenceCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_cached_result_and_failure_do_not_fetch_again(self):
        for cached in ({'TON/USDT':{'price':1.3}},{}):
            with patch.object(executor_marks,'_cached',cached), patch.object(executor_marks,'_refreshed',100), patch.object(executor_marks.time,'monotonic',return_value=200), patch.object(executor_marks.aiohttp,'ClientSession',side_effect=AssertionError('must not fetch')):
                self.assertEqual(await executor_marks.external_marks(['TON/USDT']),cached)
                self.assertEqual(await executor_marks.external_marks(['YZY/USDT']),{})
