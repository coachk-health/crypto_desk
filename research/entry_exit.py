#!/usr/bin/env python3
"""Entry-day / exit-day grid and partial-profit + trailing-stop tests on the v3 trades.

Trades: research/v3_trades.json (build year + 2023-25 unseen) and the 2021-25 history
TAKEs in research/hist_test.json. Prices: Binance daily candles (candles.token_days).
Costs: 0.10% fees, 0.03% funding a day, 0.5% slippage on stops. A day whose high reaches
the stop is counted as stopped before any low that day (worst case).
Writes research/entry_exit.json and prints the tables.
"""
import json, random, statistics as st, sys, collections
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import candles  # noqa: E402

FEES, FUND, SLIP = 0.10, 0.03, 0.5
STOP, TGT = 12, 35
UNIT = STOP * (1 + SLIP / 100) + SLIP + FEES      # 1R in % of the position


def load():
    T = [dict(token=t["tok"], date=t["date"], set=t["set"]) for t in json.loads((ROOT / "research/v3_trades.json").read_text())]
    H = json.loads((ROOT / "research/hist_test.json").read_text())["rows"]
    T += [dict(token=r["token"], date=r["date"], set="2021-25") for r in H if r["call"].startswith("TAKE")]
    out = []
    for t in T:
        d0 = date.fromisoformat(t["date"])
        src, _, days = candles.token_days(t["token"], d0 - timedelta(days=20), d0 + timedelta(days=31))
        b = {(date.fromisoformat(k) - d0).days: (v["o"], v["h"], v["l"], v["c"]) for k, v in days.items()}
        if any(k not in b for k in range(-14, 15)):
            continue
        out.append(dict(t, src=src, b=b, full30=all(k in b for k in range(15, 31))))
    return out


def plain(b, E, X):
    """Short at the open of day E, cover at the close of day X, no stop. % return."""
    P, px = b[E][0], b[X][3]
    return (P - px) / P * 100 - FEES - FUND * (X - E + 1)


def stopped(b, E, X, stop=STOP, tgt=None):
    """Short at the open of day E with a stop; optional target; else cover at the close of day X. Returns % pnl."""
    P = b[E][0]
    sp, tp = P * (1 + stop / 100), (P * (1 - tgt / 100) if tgt else None)
    for d in range(E, X + 1):
        o, h, l, c = b[d]
        if d > E and o >= sp:
            px, day = o * (1 + SLIP / 100), d; break
        if h >= sp:
            px, day = sp * (1 + SLIP / 100), d; break
        if tp and l <= tp:
            px, day = (o if d > E and o <= tp else tp), d; break
    else:
        px, day = b[X][3], X
    return (P - px) / P * 100 - FEES - FUND * (day - E + 1)


def zone(b, X):
    """Thirds at the -14, -7 and -3 opens, each with its own 12% stop; cover at the close of day X. % of the full position."""
    return sum(stopped(b, E, X) for E in (-14, -7, -3)) / 3


def partial(b, frac=0.6, trail=None, breakeven=True, last=30):
    """Short at the day -7 open, stop 12%. At the 35% target close `frac`; the rest then trails
    `trail`% above the lowest low since entry (None = hold to `last`), with the stop at least at
    entry if breakeven. Cover anything left at the close of day `last`. % pnl of the full position."""
    E = -7
    P = b[E][0]
    sp, tp = P * 1.12, P * (1 - TGT / 100)
    hit, low, pnl_part = False, P, 0.0
    for d in range(E, last + 1):
        if d not in b:
            return None
        o, h, l, c = b[d]
        if not hit:
            if (d > E and o >= sp) or h >= sp:
                px = max(o, sp) if d > E else sp
                return (P - px * (1 + SLIP / 100)) / P * 100 - FEES - FUND * (d - E + 1)
            if l <= tp:
                hit, low = True, l
                pnl_part = frac * ((P - tp) / P * 100)
                if frac >= 1:
                    return pnl_part - FEES - FUND * (d - E + 1)
                continue
        else:
            low = min(low, l)
            stop_now = min(P if breakeven else sp, low * (1 + trail / 100)) if trail else (P if breakeven else sp)
            if h >= stop_now:
                px = max(o, stop_now) * (1 + SLIP / 100)
                return pnl_part + (1 - frac) * (P - px) / P * 100 - FEES - FUND * (d - E + 1)
    px = b[last][3]
    if not hit:
        return (P - px) / P * 100 - FEES - FUND * (last - E + 1)
    return pnl_part + (1 - frac) * (P - px) / P * 100 - FEES - FUND * (last - E + 1)


def boot(rows, key, n=3000):
    by = collections.defaultdict(list)
    for r in rows:
        by[r["token"]].append(r[key])
    g = list(by.values()); rng = random.Random(5)
    m = sorted(st.mean([v for x in rng.choices(g, k=len(g)) for v in x]) for _ in range(n))
    return round(m[int(n * .05)], 2), round(m[int(n * .95)], 2)


def summ(rows, key, as_r=True):
    v = [r[key] / UNIT if as_r else r[key] for r in rows]
    for r, x in zip(rows, v):
        r[key + "_s"] = x
    lo, hi = boot(rows, key + "_s")
    return dict(n=len(v), won=round(100 * sum(x > 0 for x in v) / len(v)), avg=round(st.mean(v), 2),
                total=round(sum(v), 1), range90=[lo, hi])


def main():
    T = load()
    print(f"{len(T)} trades with candles from day -14 to +14 ({sum(t['full30'] for t in T)} also to +30)")
    res = {"trades": len(T), "grid_noStop_pct": {}, "grid_stop12_R": {}, "zone_R": {}, "exits_R": {}}
    print("\nAverage % return, no stop (short at the open of entry day, cover at the close of exit day):")
    print("entry\\exit " + "".join(f"{'+%d' % X:>10}" for X in (1, 3, 7, 14)))
    for E in (-14, -7, -3):
        line = f"day {E:<6}"
        for X in (1, 3, 7, 14):
            for t in T: t["k"] = plain(t["b"], E, X)
            s = summ(T, "k", as_r=False); res["grid_noStop_pct"][f"{E}|{X}"] = s
            line += f"{s['avg']:>+8.1f}% "
        print(line)
    print("\nWith the 12% stop, in R (1R = a stopped loss). avg R / % won:")
    print("entry\\exit " + "".join(f"{'+%d' % X:>14}" for X in (1, 3, 7, 14)))
    for E in (-14, -7, -3):
        line = f"day {E:<6}"
        for X in (1, 3, 7, 14):
            for t in T: t["k"] = stopped(t["b"], E, X)
            s = summ(T, "k"); res["grid_stop12_R"][f"{E}|{X}"] = s
            line += f"  {s['avg']:+.2f}R {s['won']:>3}%"
        print(line)
    print("\nEntry zone (thirds at -14, -7, -3, each with its own 12% stop):")
    for X in (1, 3, 7, 14):
        for t in T: t["k"] = zone(t["b"], X)
        s = summ(T, "k"); res["zone_R"][str(X)] = s
        print(f"  exit +{X:<3} {s}")
    F = [t for t in T if t["full30"]]
    print(f"\nExit management, entry day -7, on the {len(F)} trades with prices to day +30:")
    variants = {
        "current: all out at 35% target, else day +14": lambda b: stopped(b, -7, 14, tgt=35),
        "all out at 35% target, else day +30": lambda b: partial(b, 1.0, None, True, 30),
        "60% at target, 40% held to day +30 (stop at entry)": lambda b: partial(b, .6, None, True, 30),
        "60% at target, 40% trails 10%": lambda b: partial(b, .6, 10, True, 30),
        "60% at target, 40% trails 15%": lambda b: partial(b, .6, 15, True, 30),
        "60% at target, 40% trails 20%": lambda b: partial(b, .6, 20, True, 30),
        "60% at target, 40% trails 15%, no breakeven": lambda b: partial(b, .6, 15, False, 30),
    }
    for name, f in variants.items():
        for t in F: t["k"] = f(t["b"])
        s = summ(F, "k"); res["exits_R"][name] = s
        print(f"  {name:<52} {s}")
    for t in T:
        t.pop("b"); t.pop("k", None)
    res["tradeList"] = [{k: v for k, v in t.items() if not k.endswith("_s")} for t in T]
    (ROOT / "research" / "entry_exit.json").write_text(json.dumps(res, indent=1) + "\n")


if __name__ == "__main__":
    main()
