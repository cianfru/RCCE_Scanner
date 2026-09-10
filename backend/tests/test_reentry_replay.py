import unittest
from research.reentry_replay import select,summary,horizon_returns

def row(i,entered,exited,pnl=1):
    return dict(id=str(i),symbol='BTC/USDT',entry_time=entered*3600,exit_time=exited*3600,pnl=pnl,cost=100,entry_price=100,exit_price=100+pnl,open=False)

class ReentryTests(unittest.TestCase):
    def test_skipped_trade_does_not_reset_clock(self):
        rows=[row(1,0,1),row(2,2,30),row(3,25,26)]
        kept,skipped=select(rows,24)
        self.assertEqual([x['id'] for x in kept],['1','3'])
        self.assertEqual([x['id'] for x in skipped],['2'])

    def test_loss_filter_first_only_and_market_independence(self):
        rows=[row(1,0,1,10),row(2,2,3,-5),row(3,4,5),{**row(4,4,5),'symbol':'ETH/USDT'}]
        kept,_=select(rows,24,loss_only=True)
        self.assertEqual([x['id'] for x in kept],['1','2','4'])
        kept,_=select(rows,first_only=True)
        self.assertEqual([x['id'] for x in kept],['1','4'])

    def test_open_winner_is_also_skipped_and_costs_include_both_sides(self):
        rows=[row(1,0,1,-8),{**row(2,2,200,100),'open':True}]
        kept,skipped=select(rows,24);r=summary(kept,skipped,1000)
        self.assertEqual(r['total'],-8)
        self.assertEqual(r['skipped_positive'],100)
        self.assertAlmostEqual(r['net_10bps'],-8.192)

    def test_price_path_rejects_wrong_units_and_incomplete_future(self):
        bars=[dict(t=i*14400000,T=(i+1)*14400000-1,l=90,h=120,c=110) for i in range(7)]
        r=row(1,1,10)
        self.assertAlmostEqual(horizon_returns(r,bars,90000)['1'],10)
        self.assertNotIn('7',horizon_returns(r,bars,90000))
        self.assertIsNone(horizon_returns({**r,'entry_price':10},bars,90000))
        self.assertAlmostEqual(horizon_returns({**r,'entry_price':.1},bars,90000)['1'],10)


class SignalResetTests(unittest.TestCase):
    def test_requires_logged_reset_since_accepted_exit(self):
        rows=[row(1,0,1),row(2,2,3),row(3,4,5)]
        kept,skipped=select(rows,resets={'BTC/USDT':[3.5*3600]})
        self.assertEqual([x['id'] for x in kept],['1','3'])
        self.assertEqual([x['id'] for x in skipped],['2'])
        kept,_=select(rows,resets={'BTC/USDT':[.5*3600]})
        self.assertEqual([x['id'] for x in kept],['1'])
