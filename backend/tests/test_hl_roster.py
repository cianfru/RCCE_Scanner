"""Roster version 2: cohort sizes and rules on a synthetic leaderboard."""
import unittest

import hl_intelligence as hl


def row(addr, av, pnl, roi_pct, all_time_pnl, vlm=0.0):
    return {"ethAddress": addr, "accountValue": str(av), "displayName": "",
            "windowPerformances": [["month", {"pnl": str(pnl), "roi": str(roi_pct / 100), "vlm": str(vlm)}],
                                   ["allTime", {"pnl": str(all_time_pnl), "roi": "1.0"}],
                                   ["week", {"pnl": "0", "roi": "0"}]]}


def board():
    rows = []
    # 700 profitable traders: ROI 31%..730%, $40K accounts, $20K monthly profit, profitable before.
    for i in range(700):
        rows.append(row(f"0xmp{i:04d}", 40_000 + i, 20_000, 31 + i, 50_000))
    rows += [
        row("0xlucky", 60_000, 50_000, 500, 50_000 - 1),       # all of its profit came this month
        row("0xdust", 60_000, 9_999, 900, 90_000),             # monthly profit under $10K
        row("0xlow", 60_000, 20_000, 29.9, 90_000),            # ROI under 30%
        row("0xtiny", 9_000, 20_000, 400, 90_000),             # leaderboard account under $10K
        row("0xempty", 60_000, 20_000, 2_000_000, 90_000),     # began the month near empty: ROI dropped
        row("0xmm", 60_000, 20_000, 800, 90_000, vlm=60_000 * 101),   # market maker
        row("0xspot", 60_000, 20_000, 950, 90_000),            # perp account is empty (spot holder)
    ]
    # 400 large accounts ($1M+), ranked by account value; two of them are also profitable traders.
    for i in range(400):
        rows.append(row(f"0xsm{i:04d}", 50e6 - i * 1e5, 0, 0, 0))
    rows.append(row("0xelitea", 50e6 - 100.5 * 1e5, 400_000, 900, 900_000))    # large-account rank ~101
    rows.append(row("0xeliteb", 50e6 - 250.5 * 1e5, 400_000, 800, 900_000))    # rank ~251: kept only as elite
    rows.append(row("0xelitefar", 50e6 - 390.5 * 1e5, 400_000, 700, 900_000))  # rank ~391: not elite
    return rows


class RosterRulesTests(unittest.TestCase):
    def setUp(self):
        self.wallets = hl.parse_leaderboard(board())
        self.perp = {"0xspot": 0.0, "0xsm0003": 1_000.0}     # known perp equity readings

    def test_profit_rules_are_unchanged_and_the_cohort_is_capped_by_rank(self):
        mp, sm, elite = hl.build_cohorts(self.wallets, self.perp, mp_target=600, sm_target=60)
        mp_addr = [w.address for w in mp]
        self.assertEqual(len(mp), 600)
        for bad in ("0xlucky", "0xdust", "0xlow", "0xtiny", "0xempty", "0xmm", "0xspot"):
            self.assertNotIn(bad, mp_addr, bad)
        rois = [w.roi for w in mp]
        self.assertEqual(rois, sorted(rois, reverse=True))                  # best ROI first
        self.assertIn("0xelitea", mp_addr)
        # 0xmp0000 (lowest ROI) is cut by the rank cap; 0xmp0699 (best) is kept.
        self.assertIn("0xmp0699", mp_addr)
        self.assertNotIn("0xmp0000", mp_addr)

    def test_large_accounts_cut_to_target_but_elite_always_kept(self):
        mp, sm, elite = hl.build_cohorts(self.wallets, self.perp, mp_target=600, sm_target=60)
        sm_addr = [w.address for w in sm]
        self.assertEqual(len(sm), 60)
        self.assertEqual(elite, {"0xelitea", "0xeliteb"})                  # 0xelitefar ranks past ELITE_KEEP_RANK
        self.assertIn("0xeliteb", sm_addr)                                  # outside the top 60, kept as elite
        self.assertNotIn("0xsm0003", sm_addr)                               # empty perp account: skipped
        self.assertEqual(sm_addr[:3], ["0xsm0000", "0xsm0001", "0xsm0002"])
        avs = [w.account_value for w in sm]
        self.assertEqual(avs, sorted(avs, reverse=True))                    # large-account ranking kept
        self.assertEqual(len([a for a in sm_addr if a not in elite]), 58)   # 60 in all

    def test_unknown_perp_equity_is_not_a_reason_to_drop(self):
        mp, _, _ = hl.build_cohorts(self.wallets, {}, mp_target=10_000, sm_target=60)
        self.assertIn("0xspot", [w.address for w in mp])                   # no reading on hand: kept
        self.assertEqual(len(mp), 700 + 1 + 3)                              # 700 + spot + 3 elite candidates

    def test_defaults(self):
        self.assertEqual((hl.MP_TARGET, hl.SM_TARGET, hl.ELITE_KEEP_RANK, hl.ROSTER_VERSION), (600, 60, 300, 2))
        self.assertEqual(hl._MIN_PERP_EQUITY, 5_000)
        self.assertEqual(hl._EVICTION_THRESHOLD, hl._MIN_PERP_EQUITY)


if __name__ == "__main__":
    unittest.main()


class RosterVersionRecordTests(unittest.TestCase):
    def test_trader_lean_rows_carry_the_roster_version_and_old_files_migrate(self):
        import os
        import sqlite3
        import tempfile
        from unittest import mock
        import hl_persistence as hp
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "hl.db")
            old = sqlite3.connect(path)                        # a file from before version 2
            old.execute("CREATE TABLE trader_lean (bar_close INTEGER NOT NULL, grp TEXT NOT NULL, long INTEGER NOT NULL, "
                        "short INTEGER NOT NULL, long_usd REAL NOT NULL, short_usd REAL NOT NULL, PRIMARY KEY (bar_close, grp))")
            old.execute("INSERT INTO trader_lean VALUES (1900000000, 'coin:BTC', 3, 1, 10, 5)")
            old.commit()
            old.close()
            with mock.patch.object(hp, "_DB_PATH", path), mock.patch.object(hp, "_conn", None):
                hp.save_trader_lean(1_900_014_400, {"coin:BTC": {"long": 5, "short": 2, "long_usd": 1, "short_usd": 2}},
                                    hl.ROSTER_VERSION)
                rows = hp._get_conn().execute("SELECT bar_close, roster_version FROM trader_lean ORDER BY bar_close").fetchall()
                self.assertEqual(len(hp.load_trader_lean("coin:", 0)[0]), 6)      # readers unchanged
                hp._conn.close()
        self.assertEqual(rows, [(1_900_000_000, None), (1_900_014_400, 2)])
