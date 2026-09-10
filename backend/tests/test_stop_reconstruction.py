import unittest
from research.stop_reconstruction import stop_fill,simulate


def pos(peak=0):return {'entry_price':100,'stop':.08,'peak':peak,'divisor':1}
def bar(o,h,l,c,t=14400000):return {'t':t,'T':t+14400000-1,'o':o,'h':h,'l':l,'c':c}

class StopReconstructionTests(unittest.TestCase):
    def test_same_bar_orderings_produce_different_fills(self):
        b=bar(100,106,90,101)
        self.assertEqual(stop_fill(pos(),b,'high_then_low'),(100,'BE_STOP'))
        self.assertEqual(stop_fill(pos(),b,'low_then_high'),(92,'STOP_LOSS'))
        self.assertIsNone(stop_fill(pos(),b,'close'))

    def test_prearmed_stop_gap_and_close_price_execution(self):
        self.assertEqual(stop_fill(pos(.06),bar(89,105,88,94),'high_then_low'),(89,'BE_STOP'))
        self.assertEqual(stop_fill(pos(),bar(100,104,87,89),'close'),(89,'STOP_LOSS'))
        self.assertEqual(stop_fill(pos(),bar(100,104,87,89),'low_then_high'),(92,'STOP_LOSS'))

    def test_price_unit_conversion(self):
        p={**pos(),'entry_price':.1,'divisor':1000}
        price,reason=stop_fill(p,bar(100,104,90,91),'low_then_high')
        self.assertAlmostEqual(price,.092);self.assertEqual(reason,'STOP_LOSS')

    def test_changed_exit_can_block_later_recorded_entry(self):
        rows=[{'id':'a','symbol':'BTC','entry_time':1,'entry_price':100,'cost':100,'divisor':1,'atr':3}, {'id':'b','symbol':'BTC','entry_time':35000,'entry_price':101,'cost':100,'divisor':1,'atr':3}]
        bars=[bar(100,104,98,102),bar(102,104,100,103,28800000),bar(103,104,98,100,43200000)]
        r=simulate(rows,{'BTC':bars},{'BTC':[(0,1,'STRONG_LONG')]},60000,'baseline','close')
        self.assertEqual(r['open'],1);self.assertEqual(r['skipped'],1)
        self.assertEqual(r['positions']['BTC']['id'],'a')

    def test_future_signal_not_used_and_recorded_exit_not_forced(self):
        rows=[{'id':'a','symbol':'BTC','entry_time':1,'entry_price':100,'cost':100,'divisor':1,'atr':3}]
        bars=[bar(100,103,99,102)]
        r=simulate(rows,{'BTC':bars},{'BTC':[(0,1,'STRONG_LONG'),(40000,2,'RISK_OFF')]},30000,'baseline','close')
        self.assertEqual(r['open'],1);self.assertAlmostEqual(r['unrealized'],2)


class BreakEvenVariants(unittest.TestCase):
    def test_disabling_break_even_keeps_hard_stop(self):
        p={**pos(.2),'be_arm':None}
        self.assertIsNone(stop_fill(p,bar(103,110,95,99),'close'))
        self.assertEqual(stop_fill(p,bar(99,100,88,89),'close'),(89,'STOP_LOSS'))

    def test_later_arming_does_not_use_five_percent_peak(self):
        p={**pos(.06),'be_arm':.10}
        self.assertIsNone(stop_fill(p,bar(103,108,97,99),'high_then_low'))

class ReconstructionPolicyTests(unittest.TestCase):
    def test_reset_uses_reconstructed_exit_and_skipped_entry_does_not_reset_clock(self):
        def candidate(i,t):return {'id':i,'symbol':'BTC','entry_time':t,'entry_price':100,'cost':100,'divisor':1,'atr':3}
        rows=[candidate('a',1),candidate('b',30000),candidate('c',44000)]
        bars=[bar(100,103,89,90),bar(100,103,99,100,28800000),bar(100,103,99,100,43200000)]
        log={'BTC':[(0,1,'STRONG_LONG'),(29000,2,'WAIT'),(29900,3,'STRONG_LONG')]}
        r=simulate(rows,{'BTC':bars},log,60000,'reset','close')
        self.assertEqual(r['positions']['BTC']['id'],'c')
        self.assertEqual(r['skipped_entries'],[{'id':'b','reason':'Four-hour cooldown'}])

    def test_entry_bar_extremes_are_not_looked_back_and_wider_stop_reduces_size(self):
        rows=[{'id':'a','symbol':'BTC','entry_time':20000,'entry_price':100,'cost':100,'divisor':1,'atr':8}]
        r=simulate(rows,{'BTC':[bar(100,500,1,100)]},{'BTC':[(0,1,'STRONG_LONG')]},30000,'atr','high_then_low')
        self.assertEqual(r['open'],1)
        self.assertAlmostEqual(r['positions']['BTC']['cost'],100*8/12)
