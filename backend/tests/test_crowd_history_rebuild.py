"""The profitable traders re-picked each day: marked 30-day profit from fills, the daily rule, the weighted count."""
import json
import os
import shutil
import tempfile
import unittest

from backtest import crowd_history_rebuild as C
from backtest import wallet_history_rebuild as R

DAY = R.DAY


class ProfitTests(unittest.TestCase):
    def test_marked_profit_is_value_change_less_what_was_paid(self):
        # Buy 1 at 100 between the closes, the close at 110: +10. Sell 2 short at 50 from flat, close 40: +20.
        rows = {"BTC": [[5, 1, 0.0, 1.0, 100.0, 0]], "ETH": [[6, 2, 0.0, -2.0, 50.0, 0]]}
        flows = {c: C.cash_flows(r) for c, r in rows.items()}
        px = {"BTC": 110.0, "ETH": 40.0}
        got = C.profit({}, {"BTC": 1.0, "ETH": -2.0}, flows, 0, 10, lambda c: None, lambda c: px[c])
        self.assertAlmostEqual(got, 10.0 + 20.0)
        # A round trip inside the window counts even though nothing is held at either close.
        rt = {"SOL": [[3, 1, 0.0, 5.0, 10.0, 0], [4, 2, 5.0, -5.0, 12.0, 0]]}
        self.assertAlmostEqual(C.profit({}, {}, {"SOL": C.cash_flows(rt["SOL"])}, 0, 10, None, None), 10.0)
        # A held coin without a price gives no answer rather than a wrong one.
        self.assertIsNone(C.profit({"BTC": 1.0}, {"BTC": 1.0}, flows, 0, 10, lambda c: None, lambda c: 1.0))

    def test_paid_by_counts_fills_up_to_and_including_the_time(self):
        f = C.cash_flows([[5, 1, 0, 1.0, 100.0, 0], [8, 2, 1, 1.0, 120.0, 0]])
        self.assertEqual((C.paid_by(f, 4), C.paid_by(f, 5), C.paid_by(f, 9)), (0.0, 100.0, 220.0))


class RosterTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="crowd_test_")
        self.conn = R.db(os.path.join(self.dir, "rebuild.db"))

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def wallet(self, addr, fills, equity, current, pnl=1_000_000.0):
        key = 0                                            # in every sample
        self.conn.execute("INSERT INTO wallets (addr, skey, lb_av, lb_pnl, lb_vlm, census, fills_done) VALUES (?,?,?,?,?,?,1)",
                          (addr, key, 1e5, 1e6, 1e7, json.dumps({"eq": [[0, equity], [10**13, equity]], "pnl": [[0, pnl], [10**13, pnl]]})))
        self.conn.execute("INSERT INTO fills (addr, current, data, coverage_start) VALUES (?,?,?,?)",
                          (addr, json.dumps(current), json.dumps(fills), R.START))

    def test_a_wallet_is_on_the_list_while_its_last_30_days_pass_the_rule(self):
        d0 = R.START // DAY                                # 1 Sep 2025
        # Bought 1 BTC on day d0 + 1 at 100,000; it closes 140,000 from day d0 + 20 on: +$40,000 on $100,000 of equity.
        t_buy = (d0 + 1) * DAY + 3_600_000
        self.wallet("0xa", {"BTC": [[t_buy, 1, 0.0, 1.0, 100_000.0, 0]]}, 100_000.0, {"BTC": 1.0})
        # A second wallet short 1 BTC from the same moment: it loses, so it is never on the list.
        self.wallet("0xb", {"BTC": [[t_buy, 2, 0.0, -1.0, 100_000.0, 0]]}, 100_000.0, {"BTC": -1.0})
        closes = [[d, 100_000.0 if d < d0 + 20 else 140_000.0] for d in range(d0 - 2, d0 + 80)]
        self.conn.execute("INSERT INTO candles VALUES (?,?)", ("BTC", json.dumps(closes)))
        self.conn.commit()
        rows = C.roster_rows(self.conn, 0.10, 0.35, end_ms=(d0 + 70) * DAY)
        on = sorted(d for d, r in rows.items() if r["sampled"])
        self.assertEqual(on[0], d0 + 30, "the first day whose 30 days are covered")
        self.assertEqual(on[-1], d0 + 49, "30 days after the move the window no longer holds it")
        r = rows[d0 + 35]
        self.assertEqual((r["long"], r["short"], r["members"], r["sampled"]), (10, 0, 10, 1))   # one in ten sampled
        self.assertEqual(r["coins"]["BTC"], [10, 0])
        self.assertEqual(rows[d0 + 60]["sampled"], 0, "a covered day with nobody on the list")

    def test_seed_keeps_days_with_positions_and_the_coins(self):
        rows = {10: {"long": 3, "short": 1, "members": 2, "sampled": 1, "coins": {c: [1, 0] if c == "BTC" else [0, 0] for c in R.COINS}},
                11: {"long": 0, "short": 0, "members": 0, "sampled": 0, "coins": {c: [0, 0] for c in R.COINS}}}
        doc = C.seed(rows)
        self.assertEqual(doc["rows"], [[10, 3, 1]])
        self.assertEqual(doc["coins"]["BTC"], [[10, 1, 0]])
        self.assertEqual(doc["coins"]["ETH"], [])


if __name__ == "__main__":
    unittest.main()
