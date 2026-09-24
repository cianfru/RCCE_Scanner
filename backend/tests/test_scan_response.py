import unittest

from models import ScanResponse


class ScanResponseTests(unittest.TestCase):
    def test_unknown_flow_survives_response_serialization(self):
        row = dict(symbol="BTC/USDT", timeframe="4h", price=100,
                   regime="ACCUM", confidence=50, signal="WAIT", zscore=0,
                   energy=0, vol_state="NORMAL", momentum=0,
                   asset_class="crypto", vpin=None, cvd_trend="UNAVAILABLE")
        for value in (None, 0.0, 0.7):
            with self.subTest(vpin=value):
                row["vpin"] = value
                response = ScanResponse(results=[row], scan_running=False)
                self.assertEqual(response.model_dump()["results"][0]["vpin"], value)
