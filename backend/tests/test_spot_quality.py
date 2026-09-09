import unittest
from unittest.mock import patch
from types import SimpleNamespace
from spot_quality import candle_reason, volume_reason
from hyperliquid_universe import parse_markets, apply_universe, MARKETS

class SpotQualityTests(unittest.TestCase):
    def candles(self, price=0.0000000123):
        return {'timestamp':[i*86400000 for i in range(61)],
                'open':[price]*61,'close':[price]*61,'high':[price*1.1]*61,
                'low':[price*.9]*61,'volume':[100]*61}

    def test_tiny_prices_are_valid_but_zero_is_not(self):
        bars=self.candles()
        self.assertIsNone(candle_reason(bars,'1d',now=61*86400))
        bars['close'][-2]=0
        self.assertIn('Invalid', candle_reason(bars,'1d',now=61*86400))

    def test_sparse_stale_flat_and_short_history(self):
        self.assertIn('stale',candle_reason(self.candles(),'1d',now=70*86400))
        bars=self.candles()
        bars['timestamp']=[t*3 for t in bars['timestamp']]
        self.assertIn('sparse',candle_reason(bars,'1d',now=181*86400))
        bars=self.candles();bars['volume']=[0]*61
        self.assertIn('activity',candle_reason(bars,'1d',now=61*86400))
        self.assertIn('50',candle_reason({k:v[:20] for k,v in self.candles().items()},'1d',now=21*86400))

    def test_missing_nan_low_volume_fail_closed_perps_unchanged(self):
        for value in (None,'nan','0','24999'):
            self.assertIsNotNone(volume_reason({'kind':'spot','quote':'USDC','volume_24h_usd':value}))
        self.assertIsNone(volume_reason({'kind':'spot','quote':'USDC','volume_24h_usd':'25000'}))
        self.assertIsNone(volume_reason({'kind':'perpetual'}))

    def test_context_identity_and_eligibility_prune_cached_signals(self):
        meta={'universe':[{'name':'BTC'}]}
        spot={'tokens':[{'index':0,'name':'USDC'},{'index':1,'name':'BTC'},{'index':2,'name':'PICKL'}],
              'universe':[{'index':1,'name':'@1','tokens':[1,0]},{'index':2,'name':'@2','tokens':[2,0]}]}
        markets=parse_markets(meta,spot,[{'coin':'@2','dayNtlVlm':'0'},{'coin':'@1','dayNtlVlm':'50000'}])
        self.assertIsNone(markets['BTC/USDC']['exclusion_reason'])
        cache=SimpleNamespace(symbols=[],results={'1d':[{'symbol':'PICKL/USDC'}]},_results_by_sym={'PICKL/USDC':{}})
        with patch.dict(MARKETS,markets,clear=True):apply_universe(cache)
        self.assertEqual(set(cache.symbols),{'BTC/USDT','BTC/USDC'})
        self.assertEqual(cache.results['1d'],[])
        self.assertNotIn('PICKL/USDC',cache._results_by_sym)
