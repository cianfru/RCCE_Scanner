import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

import access
import main


class AdminKeyTests(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(main.app)

    def test_open_until_the_key_is_set(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("REFLEX_ADMIN_KEY", None)
            self.assertTrue(access.write_allowed("POST", "/api/executor/disable", {}))

    def test_writes_need_the_key_reads_and_login_do_not(self):
        with mock.patch.dict(os.environ, {"REFLEX_ADMIN_KEY": "k3y"}):
            self.assertFalse(access.write_allowed("POST", "/api/executor/disable", {}))
            self.assertFalse(access.write_allowed("DELETE", "/api/tradfi/symbols/GOLD", {"x-admin-key": "wrong"}))
            self.assertTrue(access.write_allowed("POST", "/api/executor/disable", {"x-admin-key": "k3y"}))
            self.assertTrue(access.write_allowed("GET", "/api/executor/status", {}))
            self.assertTrue(access.write_allowed("POST", "/api/auth/login", {}))
            r = self.c.post("/api/admin/features", json={})
            self.assertEqual(r.status_code, 403)
            self.assertIn("Admin key", r.json()["detail"])
            self.assertEqual(self.c.get("/health").status_code, 200)
            self.assertNotEqual(self.c.post("/api/auth/login", json={"code": "x"}).status_code, 403)

    def test_no_stand_in_fear_and_greed(self):
        with mock.patch.object(main.cache, "sentiment", None):
            body = self.c.get("/api/sentiment").json()
        self.assertIsNone(body["fear_greed_value"])
        self.assertIsNone(body["fear_greed_label"])


if __name__ == "__main__":
    unittest.main()
