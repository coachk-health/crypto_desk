#!/usr/bin/env python3
"""Fair entry-day test: the v3 call is made with only what was known on the entry day.
For entry day E: pump = open(E) / open(E-23) - 1 (same 23-day span as -30..-7),
open interest change = OI(E-1) / OI(E-8) - 1. Candidates: every big (25%+) or first insider
unlock in the build year, the 2023-25 unseen set and the 2021-25 history set.
Trade: short at the day-E open, stop 12%, target 35%, cover day +14 (current plan)."""
import json, sys, statistics as st
from datetime import date, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "research")); sys.path.insert(0, "/home/claude/work")
import candles
from entry_exit import stopped, summ, UNIT
from hist_test import metrics_oi
from buckets import rows as BR
C = [dict(token=r["tok"], date=r["date"], set=r["set"], pct=r["pct"], first=r["first"]) for r in BR if r["first"] or (r["pct"] or 0) >= 25]
C += [dict(token=r["token"], date=r["date"], set="2021-25", pct=r["pct"], first=r["first"]) for r in json.loads((ROOT/"research/hist_test.json").read_text())["rows"]]
out = {}
for c in C:
    d0 = date.fromisoformat(c["date"])
    src, sym, days = candles.token_days(c["token"], d0 - timedelta(days=40), d0 + timedelta(days=15))
    b = {(date.fromisoformat(k) - d0).days: (v["o"], v["h"], v["l"], v["c"]) for k, v in days.items()}
    if src != "binance-futures" or any(k not in b for k in range(-37, 15)):
        continue
    for E in (-14, -7, -3):
        pump = (b[E][0] / b[E - 23][0] - 1) * 100
        big = (c["pct"] or 0) >= 25
        oi = None
        if not big and c["first"]:
            a, z = metrics_oi(sym, d0 + timedelta(days=E - 8)), metrics_oi(sym, d0 + timedelta(days=E - 1))
            oi = (z / a - 1) * 100 if a and z else None
        take = pump < 30 and (big or (c["first"] and oi is not None and oi <= -10))
        if take:
            out.setdefault(E, []).append(dict(c, k=stopped(b, E, 14, tgt=35)))
for E in (-14, -7, -3):
    rs = out.get(E, [])
    s = summ(rs, "k")
    print(f"entry day {E}: {s}")
    for setn in ("build", "unseen", "2021-25"):
        g = [r for r in rs if r["set"] == setn]
        if g: print(f"     {setn:<8} n={len(g):>3} avg {st.mean(r['k'] for r in g)/UNIT:+.2f}R won {round(100*sum(r['k']>0 for r in g)/len(g))}%")
json.dump({str(E): [{k: v for k, v in r.items() if not k.endswith('_s')} for r in rs] for E, rs in out.items()}, open(ROOT / "research/entry_fair.json", "w"), indent=1)
