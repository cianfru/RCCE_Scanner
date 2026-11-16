# Brief: what to pull from the Chart Champions videos

The rules in docs/reviews/auction-levels-spec.md still rest on a summary with no citations. This brief is for whoever can read the videos' transcripts (Gemini, or a Claude session with a logged-in browser): it says which videos, what to look for, and the form the answer must take so each rule can be checked.

## The form of the answer

One line per statement, nothing summarised:

```
[video id @ mm:ss] "the words as spoken"
```

- The video id is the part after `v=` in the address.
- Quote the transcript as it is, mistakes included. No paraphrase, no merging of two statements.
- If a topic below is never stated, write "not found" for it. Do not fill the gap from general knowledge.
- Say who is speaking when it is not Daniel (the channel has several presenters).

Save the answers as one text file. Pasting it into the chat, or putting it in the repository at `docs/reviews/auction-video-quotes.md`, is enough.

## Videos, most useful first

| id | Title |
|---|---|
| Qk8fIwKTS30 | Trading Discipline: How to Only Take A+ Setups (Free Cheat Sheet) |
| xGDj5EMtsXQ | Why I Longed, AMAZING FAILED AUCTION TRADE NASDAQ SETUP |
| BUnEXf7jkfw | Bitcoin's Failed Auction = BEARISH, But I Will Long The Drop |
| mgK6kHH3RJI | The Previous Day High & Low Method: Trade Reversals Like A Pro |
| ShwSLLP_uUM | Why Your Support & Resistance Trades Keep Failing |
| AlxYbw1fTMQ | Price Action Trading Strategy: Support, Resistance, Structure & Confluence |
| nWCsje3qrSA | The 30-Minute Weekly Trade Review |
| AWHRwXqXXpw | Why I Shorted Bitcoin - HTF Swing Trading Stocks, Gold, Crypto |
| 8Q-z0Lr6MbI | Bitcoin's ongoing mid time frame range |
| OSQ_o1yRLao | I'm Long BTC, ETH and SOL. Here's How I'm Managing It |
| 8CC91vgGTVk | How I lost $0 Getting Bitcoin Call Incorrect |

Plus any older teaching video on the value area, the 80% rule or "CCV", naked POCs, VWAP, the 0.618 to 0.66 zone, swing failure patterns, open interest or delta.

## What to look for

1. **The 80% rule, or "CCV".** The exact conditions: which open, outside which value area, what counts as back inside (how many candles, which timeframe), entry, stop, exits. Which session times he uses for crypto. Any condition on the day before ("range day") and how he defines it.
2. **Value area, VAH, VAL, POC, naked POC.** Which profile (day, week, month, a chosen range), which day boundary, and what he says naked POCs do.
3. **Failed auction.** His definition, the confirming candle and its timeframe, entry, stop, exits.
4. **Acceptance against rejection** at a value-area edge: what counts as acceptance.
5. **Balance against trend.** How he decides which he is in.
6. **Previous day high and low, Monday range, weekly and monthly opens, midpoints, Initial Balance, overnight high and low.**
7. **Swing failure pattern.** Definition and the timeframe of the confirming close.
8. **Order flow.** Open interest, delta or CVD, funding, footprint, any named tool: what exactly he looks for.
9. **Fibonacci and VWAP.** Which levels, anchored where.
10. **Confluence.** How many factors, his A+ checklist word for word, and when he does not trade.
11. **Risk.** Stop placement, risk a trade, minimum reward to risk, partial exits, moving stops.
12. **Any number he gives as a chance or win rate**, word for word.

## What happens with it

Each quote either confirms a rule in the spec, corrects it, or adds one. A rule that changes becomes a new declared study before anything is tested, as with the 80% rule (docs/reviews/value-area-rule-study.md).
