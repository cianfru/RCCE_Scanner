import unittest
from executor_performance import performance

NOW=1800000000

def pos(symbol='BTC/USDT', side='LONG', cost=100):
    return dict(symbol=symbol,side=side,cost_usd=cost,entry_price=10,entry_time=NOW-180*86400)
def trade(pnl, month_days=20):
    return dict(symbol='BTC/USDT',pnl_usd=pnl,entry_time=NOW-180*86400,exit_time=NOW-month_days*86400,exit_signal='BE_STOP')

class PerformanceTests(unittest.TestCase):
    def test_realized_unrealized_and_starting_capital_not_turnover(self):
        p=performance([pos()], [trade(20),trade(-10),trade(0)], {'BTC/USDT':{'price':15,'observed_at':NOW}},1000,NOW)
        self.assertEqual(p['realized_pnl_usd'],10)
        self.assertEqual(p['unrealized_pnl_usd'],50)
        self.assertEqual(p['return_on_starting_capital_pct'],6)
        self.assertAlmostEqual(p['closed_win_rate'],100/3)
        self.assertEqual((p['wins'],p['losses'],p['breakeven']),(1,1,1))
        self.assertEqual(p['history_days'],180)
        self.assertEqual(p['realized_curve'][-1]['pnl_usd'],10)
        self.assertEqual(sum(m['pnl_usd'] for m in p['monthly_realized']),10)

    def test_short_mark_and_unpriced_prevents_false_total(self):
        p=performance([pos(side='SHORT'),pos('OLD/USDT')],[],{'BTC/USDT':{'price':8,'observed_at':NOW}},1000,NOW)
        self.assertAlmostEqual(p['unrealized_pnl_usd'],20)
        self.assertEqual(p['priced_positions'],1)
        self.assertAlmostEqual(p['combined_pnl_usd'],20)
        self.assertEqual(p['excluded_open_positions'],1)
        self.assertEqual(len(p['positions']),1)
        self.assertIsNone(p['estimated_equity_usd'])

    def test_stale_and_legacy_unit_errors_are_not_astronomical_winners(self):
        bad=pos('MKR/USDT');bad['peak_unrealized_pct']=2467955
        p=performance([bad,pos('XMR/BTC'),pos()],[],{s:{'price':10000,'observed_at':NOW-30000} for s in ['MKR/USDT','XMR/BTC','BTC/USDT']},1000,NOW)
        self.assertEqual(p['priced_positions'],0)
        self.assertEqual(p['unrealized_pnl_usd'],0)
        self.assertEqual(p['positions'],[])
        self.assertEqual(p['excluded_open_positions'],3)

    def test_empty_and_invalid_records(self):
        p=performance([],[],{},1000,NOW)
        self.assertIsNone(p['closed_win_rate'])
        self.assertIsNone(p['first_entry_at'])
        self.assertEqual(p['combined_pnl_usd'],0)
        p=performance([], [trade(float('nan'))],{},1000,NOW)
        self.assertEqual(p['unusable_closed_records'],1)
        self.assertFalse(p['valuation_complete'])

class CleanupTests(unittest.TestCase):
    def test_assistant_session_retention_is_bounded(self):
        from unittest.mock import patch
        import assistant
        with patch.object(assistant,'MAX_SESSIONS',2):
            manager=assistant.AssistantManager()
            manager.get_or_create_session('a');manager.get_or_create_session('b');manager.get_or_create_session('a');manager.get_or_create_session('c')
            self.assertEqual(set(manager.sessions),{'a','c'})

class ReconciliationTests(unittest.TestCase):
    def test_cash_mismatch_does_not_invent_account_equity(self):
        p=performance([pos()],[],{'BTC/USDT':{'price':10,'observed_at':NOW}},1000,NOW,portfolio={'cash':1000})
        self.assertEqual(p['cash_reconciliation_difference_usd'],100)
        self.assertFalse(p['accounting_reconciled'])
        self.assertIsNone(p['estimated_equity_usd'])
