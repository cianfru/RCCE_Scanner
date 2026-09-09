import asyncio
import json
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from hyperliquid_universe import parse_markets, apply_universe, MARKETS
from assistant_snapshot import snapshot
from assistant import AssistantManager

class UniverseTests(unittest.TestCase):
    def test_perps_spot_native_ids_delist_and_duplicate_tickers(self):
        meta = {"universe": [{"name":"BTC"},{"name":"kPEPE"},{"name":"OLD","isDelisted":True},{"name":"xyz:GOLD"}]}
        spot = {"tokens":[{"index":0,"name":"USDC"},{"index":1,"name":"BTC"},{"index":2,"name":"NEW"},{"index":3,"name":"NEW"}],
                "universe":[{"index":0,"name":"@0","tokens":[1,0]},{"index":1,"name":"@1","tokens":[2,0]}, {"index":2,"name":"@2","tokens":[3,0]}]}
        result = parse_markets(meta,spot)
        self.assertEqual(set(result), {"BTC/USDT","KPEPE/USDT","NEW~2/USDC","NEW~3/USDC"})
        self.assertEqual(result["KPEPE/USDT"]["coin"],"kPEPE")
        self.assertEqual(result["NEW~2/USDC"]["coin"],"@1")

    def test_prunes_legacy_results_without_mutating_tradfi(self):
        cache = SimpleNamespace(symbols=[],results={"1d":[{"symbol":"BTC/USDT"},{"symbol":"XMR/BTC"}]},_results_by_sym={"XMR/BTC":{},"BTC/USDT":{}},tradfi_results={"1d":[{"symbol":"xyz:GOLD"}]})
        with patch.dict(MARKETS, {"BTC/USDT":{}}, clear=True):
            apply_universe(cache)
        self.assertEqual(cache.symbols,["BTC/USDT"])
        self.assertEqual(cache.results["1d"],[{"symbol":"BTC/USDT"}])
        self.assertEqual(list(cache._results_by_sym),["BTC/USDT"])
        self.assertEqual(cache.tradfi_results["1d"][0]["symbol"],"xyz:GOLD")

class SnapshotTests(unittest.TestCase):
    def cache(self):
        rows={"1d":[{"symbol":"BTC/USDT","timeframe":"1d","signal":"LIGHT_LONG","signal_confidence":82,"confidence":99.8,"priority_score":70,"signal_warnings":["4H disagrees"]}],
              "4h":[{"symbol":"BTC/USDT","timeframe":"4h","signal":"WAIT","price":100}]}
        return SimpleNamespace(get_results=lambda tf:rows.get(tf,[]),get_cache_age=lambda:30,consensus={},sentiment=None,global_metrics=None,alt_season={},symbols=["BTC/USDT"])

    def test_exact_timeframe_percentages_and_missing_not_zero(self):
        data=json.loads(snapshot(self.cache(),["BTC/USDT","MISSING/USDC"],"1d"))
        row=data['markets'][0]
        self.assertEqual(row['signal'],'LIGHT_LONG')
        self.assertEqual(row['signal_confidence'],82)
        self.assertEqual(row['confidence'],99.8)
        self.assertIsNone(row['price'])
        self.assertEqual(row['signal_warnings'],['4H disagrees'])
        self.assertEqual(data['unavailable_symbols'],['MISSING/USDC'])
        self.assertEqual(data['best_setups_in_priority_order'],['BTC/USDT'])

    def test_public_model_mutation_is_rejected(self):
        manager=AssistantManager()
        original=manager.get_current_model()
        self.assertFalse(manager.set_model('anthropic/expensive'))
        self.assertEqual(manager.get_current_model(),original)

    def test_paid_or_missing_model_fails_closed(self):
        manager=AssistantManager()
        async def models(): return [{"id":"google/gemma-4-31b-it:free","is_free":True}]
        manager.get_available_models=models
        for model in ('anthropic/expensive','gone/model:free'):
            manager._current_model=model
            with self.assertRaises(RuntimeError): asyncio.run(manager._validate_free_model())

    def test_word_boundaries_no_bitcoin_substring_in_sentence(self):
        fake=self.cache()
        with patch.dict(sys.modules, {"scanner":SimpleNamespace(cache=fake)}):
            manager=AssistantManager()
            self.assertIsNone(manager._detect_symbol("ABTC is not BTCB"))
            self.assertEqual(manager._detect_symbol("Explain BTC please"),'BTC/USDT')

    def test_trading_words_do_not_select_same_named_spot_tokens(self):
        fake=self.cache()
        original=fake.get_results
        fake.get_results=lambda tf: original(tf)+[{"symbol":"SELL/USDC"},{"symbol":"NEAR/USDT"}]
        with patch.dict(sys.modules, {"scanner":SimpleNamespace(cache=fake)}):
            manager=AssistantManager()
            self.assertEqual(manager._detect_all_symbols("Should I sell BTC near this price?"),["BTC/USDT"])
            self.assertEqual(manager._detect_all_symbols("Explain $SELL"),["SELL/USDC"])

    def test_selected_timeframe_and_zero_price_routing_reach_provider(self):
        cache=self.cache()
        captured={}
        def create(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Snapshot explanation"))])
        manager=AssistantManager()
        manager._mode='openrouter'
        manager._client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        async def valid(): pass
        manager._validate_free_model=valid
        with patch.dict(sys.modules, {"scanner":SimpleNamespace(cache=cache),"assistant_memory":None}):
            reply,_=asyncio.run(manager.chat('test','Explain this signal',symbol='BTC/USDT',timeframe='4h'))
        self.assertEqual(reply,'Snapshot explanation')
        data=json.loads(captured['messages'][0]['content'].split('Current scanner snapshot:\n')[1])
        self.assertEqual(data['selected_timeframe'],'4h')
        self.assertEqual(data['markets'][0]['signal'],'WAIT')
        self.assertEqual(captured['extra_body']['provider']['max_price'],{'prompt':0,'completion':0})

class ProviderErrorTests(unittest.TestCase):
    def test_safe_capacity_and_configuration_messages(self):
        from assistant_errors import public_assistant_error
        error=RuntimeError("secret provider response")
        error.status_code=429
        status,message=public_assistant_error(error)
        self.assertEqual(status,429)
        self.assertIn("capacity",message)
        self.assertNotIn("secret",message)
        status,message=public_assistant_error(RuntimeError("server needs OPENROUTER_API_KEY"))
        self.assertEqual(status,503)
        self.assertIn("configured by the operator",message)

if __name__ == '__main__': unittest.main()
