#!/usr/bin/env python3
"""Out-of-sample test of the frozen unlock-short rules (data/strategy_frozen.json) on unlocks the
rules were never chosen on (Nov 2023 to Nov 2025, researched with scripts/frozen-test-research.md).

  python3 scripts/frozen_test.py research1.json [research2.json ...]

Prices: Binance USDT-perpetual daily candles (spot if no perpetual), from Binance's free files.
Ticker check: the Binance open on the unlock day must be within 35% of the price a source reported
for that day; events failing it are dropped (a ticker can be reused by another token).
Writes data/frozen_test.json and prints the verdict against the pre-registered pass mark.
"""
import json, random, statistics as st, sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import candles  # noqa: E402

F = json.loads((ROOT / "data" / "strategy_frozen.json").read_text())
STOP, TGT, COVER = F["trade"]["stopPct"], F["trade"]["targetPct"], F["trade"]["coverDay"]
FEES, FUND, SLIP = 0.10, 0.03, 0.5
D = lambda s: datetime.strptime(s, "%Y-%m-%d").date()


def sim(b, stop=STOP, tgt=TGT, cover=COVER):
    """b: {day: (o,h,l,c)} relative to the unlock date. Short at day -7 open."""
    if any(d not in b for d in range(-7, cover + 1)):
        return None
    P = b[-7][0]
    sp, tp = P * (1 + stop / 100), P * (1 - tgt / 100)
    px, why, day = None, "time", cover
    for d in range(-7, cover):
        o, h, l, c = b[d]
        if d > -7 and o >= sp:
            px, why, day = o, "stop", d; break
        if d > -7 and o <= tp:
            px, why, day = o, "target", d; break
        if h >= sp:
            px, why, day = sp * (1 + SLIP / 100), "stop", d; break
        if l <= tp:
            px, why, day = tp, "target", d; break
    if px is None:
        px = b[cover][0]
    pnl = (P - px) / P * 100 - FEES - FUND * max(1, day + 7)
    return {"R": round(pnl / (stop * (1 + SLIP / 100) + SLIP + FEES), 3), "why": why, "exitDay": day,
            "pnlPct": round(pnl, 2)}


def boot(rows, n=4000):
    by = {}
    for r in rows:
        by.setdefault(r["token"], []).append(r["R"])
    g = list(by.values())
    rng = random.Random(11)
    ms = sorted(st.mean([v for x in rng.choices(g, k=len(g)) for v in x]) for _ in range(n))
    return round(ms[int(n * .05)], 3), round(ms[int(n * .95)], 3)


def summary(rows):
    if not rows:
        return None
    R = [r["R"] for r in rows]
    lo, hi = boot(rows) if len(rows) >= 3 else (None, None)
    return {"n": len(R), "tokens": len({r["token"] for r in rows}), "won": round(100 * sum(x > 0 for x in R) / len(R)),
            "meanR": round(st.mean(R), 3), "totalR": round(sum(R), 2), "range90": [lo, hi],
            "stops": sum(r["why"] == "stop" for r in rows), "targets": sum(r["why"] == "target" for r in rows)}


def main():
    events, dropped = [], []
    for path in sys.argv[1:]:
        for t in json.loads(Path(path).read_text()):
            for e in t.get("events") or []:
                if e.get("date") and "2023-11-15" <= e["date"] <= "2025-11-16":
                    events.append(dict(e, token=t["token"]))
    seen, rows = set(), []
    for e in sorted(events, key=lambda e: (e["token"], e["date"])):
        key = (e["token"], e["date"])
        if key in seen:
            continue
        seen.add(key)
        d0 = D(e["date"])
        src, sym, days = candles.token_days(e["token"], d0 - timedelta(days=40), d0 + timedelta(days=COVER + 2))
        if not src:
            dropped.append(dict(key=key, why="no Binance prices")); continue
        b = {}
        for k, x in days.items():
            b[(D(k) - d0).days] = (x["o"], x["h"], x["l"], x["c"])
        if 0 not in b or -30 not in b or -14 not in b or -7 not in b:
            dropped.append(dict(key=key, why="prices do not cover the month before")); continue
        p = e.get("priceUsd")
        if p:
            if abs(b[0][0] / p - 1) > 0.35:
                dropped.append(dict(key=key, why=f"ticker check failed: Binance {b[0][0]:.4g} vs reported {p}")); continue
        pct = e.get("pctCirculating")
        first = bool(e.get("firstInsiderUnlock"))
        pump = (b[-7][0] / b[-30][0] - 1) * 100
        week = (b[-7][0] / b[-14][0] - 1) * 100
        r = {"token": e["token"], "date": e["date"], "first": first, "pct": pct, "shape": e.get("shape"),
             "pump": round(pump, 1), "week": round(week, 1), "priceChecked": bool(p), "source": src}
        core = first or (pct or 0) >= 25
        r["core"] = core
        r["passes"] = core and pump < 30 and week <= -5
        for lab, kw in (("frozen", {}), ("v1", {"tgt": 35, "cover": 14})):
            s = sim(b, **kw)
            r[lab] = s
        if r["frozen"] is None:
            dropped.append(dict(key=key, why="not enough days after the unlock yet")); continue
        rows.append(r)
    flat = lambda lab, f: [dict(token=r["token"], date=r["date"], **r[lab]) for r in rows if f(r) and r[lab]]
    out = {
        "frozenRules": "data/strategy_frozen.json", "window": ["2023-11-15", "2025-11-16"],
        "rulesPass": summary(flat("frozen", lambda r: r["passes"])),
        "rulesPass_v1exits": summary(flat("v1", lambda r: r["passes"])),
        "coreAnyWeek": summary(flat("frozen", lambda r: r["core"] and r["pump"] < 30)),
        "coreFlatOrUp": summary(flat("frozen", lambda r: r["core"] and r["pump"] < 30 and r["week"] > -5)),
        "corePumped": summary(flat("frozen", lambda r: r["core"] and r["pump"] >= 30)),
        "allResearched": summary(flat("frozen", lambda r: True)),
        "trades": rows, "dropped": dropped,
    }
    rp = out["rulesPass"]
    out["verdict"] = ("PASS" if rp and rp["meanR"] > 0.25 and rp["range90"][0] is not None and rp["range90"][0] > 0
                      else "NOT PROVEN")
    (ROOT / "data" / "frozen_test.json").write_text(json.dumps(out, indent=1) + "\n")
    for k in ("rulesPass", "rulesPass_v1exits", "coreAnyWeek", "coreFlatOrUp", "corePumped", "allResearched"):
        print(f"{k:<20} {out[k]}")
    print("verdict:", out["verdict"], "| dropped:", len(dropped))


if __name__ == "__main__":
    main()
