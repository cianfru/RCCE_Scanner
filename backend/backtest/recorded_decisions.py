"""Export/verify first-observed live snapshots without importing the web server.

python -m backtest.recorded_decisions /data/opportunities.db snapshots.json --timeframe 4h
Combine the exported decisions with independently obtained OHLCV/funding histories
in the cto_study dataset schema. Never backfill unknown historical context.
"""
import argparse
import json
import sqlite3
from pathlib import Path
from decision_pipeline import replay_recorded


def export(path, timeframe):
    with sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True) as db:
        rows = db.execute("SELECT payload FROM snapshots WHERE timeframe=? ORDER BY candle,symbol", (timeframe,))
        snapshots = [json.loads(row[0]) for row in rows]
    mismatches = []
    for row in snapshots:
        reproduced = replay_recorded(row)
        if reproduced['baseline_signal'] != row.get('baseline_signal', row['signal']):
            mismatches.append([row['symbol'],row['signal_bar_close_time']])
    return dict(decisions=snapshots, parity_mismatches=mismatches,
                context_complete=bool(snapshots) and not mismatches)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('journal',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--timeframe',choices=['4h','1d'],default='4h')
    args=parser.parse_args();result=export(args.journal,args.timeframe)
    with args.output.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)
    print(f"{len(result['decisions'])} snapshots; {len(result['parity_mismatches'])} mismatches")

if __name__=='__main__':main()
