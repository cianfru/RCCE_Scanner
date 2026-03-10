"""
On-chain whale tracking module.

Monitors token transfers across Ethereum, Base, and Solana to detect
smart-money accumulation, insider distribution, and trending tokens.
"""

from .tracker import WhaleTracker

__all__ = ["WhaleTracker"]
