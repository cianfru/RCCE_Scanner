import json
import re
from pathlib import Path

import pytest

from wallet_names import ADJECTIVES, NOUNS, codename, short_address, wallet_label

FIXTURE = Path(__file__).parent / "fixtures" / "wallet_names.json"
JS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "utils" / "walletName.js"


def test_parity_with_frontend_for_fixed_addresses():
    # The same 20 addresses and names are checked by frontend/src/utils/walletName.test.js.
    fixed = json.loads(FIXTURE.read_text())
    assert len(fixed) == 20
    for addr, name in fixed.items():
        assert codename(addr) == name
        assert codename(addr.upper().replace("0X", "0x")) == name


@pytest.mark.skipif(not JS.exists(), reason="frontend source not present")
def test_word_lists_match_frontend():
    js = JS.read_text()

    def words(name):
        body = re.search(rf"export const {name} = \[(.*?)\];", js, re.S).group(1)
        return tuple(re.findall(r'"([A-Za-z]+)"', body))

    assert words("ADJECTIVES") == ADJECTIVES
    assert words("NOUNS") == NOUNS


def test_lists_and_labels():
    assert len(set(ADJECTIVES)) == len(ADJECTIVES) >= 96
    assert len(set(NOUNS)) == len(NOUNS) >= 96
    assert ADJECTIVES[:2] == ("Silent", "Golden") and NOUNS[:2] == ("Fox", "Whale")
    a = "0x9cd0a696c7cbb9d44de99268194cb08e5684e5fe"
    assert codename(a) == "Opal Reindeer"
    assert codename("") == ""
    assert short_address(a) == "0x9cd0…e5fe"
    assert wallet_label(a) == "Opal Reindeer (0x9cd0…e5fe)"
