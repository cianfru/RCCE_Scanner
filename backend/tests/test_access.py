import os
import unittest
from unittest import mock

import access


class AccessTests(unittest.TestCase):
    def test_open_until_a_code_is_configured(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(access.enforced())
            self.assertTrue(access.allowed("/api/scan", {}, {}))
            self.assertFalse(access.check_code(""))

    def test_enforced_api_requires_a_valid_token(self):
        with mock.patch.dict(os.environ, {"REFLEX_ACCESS_CODE": "s3cret"}, clear=True):
            self.assertTrue(access.check_code("s3cret"))
            self.assertFalse(access.check_code("wrong"))
            token = access.issue_token()
            self.assertTrue(access.allowed("/api/scan", {"authorization": f"Bearer {token}"}, {}))
            self.assertTrue(access.allowed("/ws/scan", {}, {"token": token}))
            self.assertFalse(access.allowed("/api/scan", {}, {}))
            self.assertFalse(access.allowed("/api/scan", {"authorization": "Bearer 99999999999.bad"}, {}))
            for public in ("/api/auth/login", "/api/public/preview", "/health", "/"):
                self.assertTrue(access.allowed(public, {}, {}), public)

    def test_tokens_expire_and_die_with_the_secret(self):
        with mock.patch.dict(os.environ, {"REFLEX_ACCESS_CODE": "a"}, clear=True):
            old = access.issue_token(now=0)
            self.assertFalse(access.token_valid(old))
            token = access.issue_token()
        with mock.patch.dict(os.environ, {"REFLEX_ACCESS_CODE": "b"}, clear=True):
            self.assertFalse(access.token_valid(token))


if __name__ == "__main__":
    unittest.main()
