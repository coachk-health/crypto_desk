#!/usr/bin/env python3
"""Unlock trade signals: applies one fixed playbook to every past unlock and records
each trade it would have taken, so the plan can be judged on its whole record.

The rules are fixed before looking at any single trade. They come from published
unlock research and from the track record's group results (data/backtest.json):

  Signal fires if ANY of:
    big        the unlock is 10% or more of circulating supply
    investors  60% or more goes to investors
    first      it is the token's first insider (team or investor) unlock
  (A fourth trigger, "worth 3+ days of trading volume", was tested and dropped: only 4 trades
  fired on it alone, all from one token, so it had no evidence of its own.)
  Skip if:    the token rose 30% or more from 30 days before to the entry day (shorting into a
              pump is how the worst losses happened; this guard was added after seeing them,
              so its record is shown both ways and tracked live)
  Trade:      short at the close 7 days before the unlock, cover at the close 7 days after
  Costs:      0.10% exchange fees for the round trip plus funding of 0.03% a day held

Results are also shown with a stop (cover if a daily close is 20% above entry), by
half-year, and without the three best trades, so one lucky period or token cannot carry it.

Input:  data/backtest.json (needs pathUsd per event)
Output: data/signals.json
"""
import json, statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BT = ROOT / "data" / "backtest.json"
OUT = ROOT / "data" / "signals.json"

RULES = {
    "big": {"label": "10%+ of circulating supply", "field": "pctCirculating", "min": 10},
    "investors": {"label": "Mostly to investors (60%+)", "field": "investorsShare", "min": 0.6},
    "first": {"label": "First insider unlock", "field": "firstInsiderUnlock", "equals": True},
}
ENTRY, EXIT = -7, 7
EXITS_COMPARE = [0, 3, 7, 14]
FEES = 0.10          # % round trip
FUNDING_DAY = 0.03   # % per day held (assumption: shorts usually pay on unlock tokens)
STOP = 20.0          # % adverse close that closes the trade in the 'with stop' version
NOTIONAL = 1000      # $ per trade in the account curve
PUMP = 30.0          # % rise from day -30 to entry that blocks the trade


def investors_share(mix):
    if not isinstance(mix, dict):
        return None
    tot = sum(v or 0 for v in mix.values())
    return (mix.get("investors") or 0) / tot if tot else None


def matched(facts):
    hits = []
    for k, r in RULES.items():
        v = facts.get(r["field"])
        if "equals" in r and v is r["equals"]:
            hits.append(k)
        elif "min" in r and isinstance(v, (int, float)) and v >= r["min"]:
            hits.append(k)
    return hits


def trade(path, entry=ENTRY, exit_=EXIT, stop=None):
    """Short from day `entry` to day `exit_` using the USD path (set to 0% on unlock day).
    Returns (pnl %, worst adverse %, days held, stopped) after costs, or None."""
    pe = path.get(str(entry))
    if pe is None:
        return None
    base = 1 + pe / 100
    worst = 0.0
    for d in range(entry + 1, exit_ + 1):
        v = path.get(str(d))
        if v is None:
            return None
        ratio = (1 + v / 100) / base
        worst = max(worst, (ratio - 1) * 100)
        if stop is not None and (ratio - 1) * 100 >= stop and d < exit_:
            held = d - entry
            return round(-(ratio - 1) * 100 - FEES - FUNDING_DAY * held, 2), round(worst, 2), held, True
    ratio = (1 + path[str(exit_)] / 100) / base
    held = exit_ - entry
    return round(-(ratio - 1) * 100 - FEES - FUNDING_DAY * held, 2), round(worst, 2), held, False


def stats(trades, key="pnl"):
    v = [t[key] for t in trades if t.get(key) is not None]
    if not v:
        return None
    wins = [x for x in v if x > 0]
    losses = [x for x in v if x <= 0]
    s = sorted(v, reverse=True)
    return {
        "n": len(v), "tokens": len({t["token"] for t in trades}),
        "win": round(100 * len(wins) / len(v)), "median": round(statistics.median(v), 2),
        "mean": round(statistics.mean(v), 2), "best": round(max(v), 2), "worst": round(min(v), 2),
        "profitFactor": round(sum(wins) / abs(sum(losses)), 2) if losses and sum(losses) != 0 else None,
        "totalUsd": round(sum(v) / 100 * NOTIONAL),
        "totalUsdWithoutBest3": round(sum(s[3:]) / 100 * NOTIONAL) if len(s) > 3 else None,
    }


def curve(trades, key="pnl"):
    """Cumulative $ result with $1,000 per trade, booked on each trade's exit date."""
    pts, cum, peak, dd = [], 0.0, 0.0, 0.0
    for t in sorted(trades, key=lambda t: t["exitDate"]):
        cum += t[key] / 100 * NOTIONAL
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
        pts.append({"date": t["exitDate"], "cum": round(cum), "token": t["token"]})
    return pts, round(dd)


def max_open(trades):
    ev = []
    for t in trades:
        ev += [(t["entryDate"], 1), (t["exitDate"], -1)]
    cur = best = 0
    for _, x in sorted(ev):
        cur += x
        best = max(best, cur)
    return best


def main():
    bt = json.loads(BT.read_text())
    past = json.loads((ROOT / "data" / "past_unlocks.json").read_text())
    ids = {t["token"]: t["coingeckoId"] for t in past.get("tokens", []) if t.get("coingeckoId")}
    trades = []
    for e in bt["events"]:
        facts = {"pctCirculating": e.get("pctCirculating"), "investorsShare": investors_share(e.get("recipientsMix")),
                 "firstInsiderUnlock": bool(e.get("firstInsiderUnlock")), "advDays": e.get("advDays")}
        hits = matched(facts)
        if not hits:
            continue
        path = e.get("pathUsd") or {}
        r = trade(path)
        if not r:
            continue
        rs = trade(path, stop=STOP)
        p30, pen = path.get("-30"), path.get(str(ENTRY))
        momentum = round(((1 + pen / 100) / (1 + p30 / 100) - 1) * 100, 2) if p30 is not None and pen is not None else None
        d0 = datetime.strptime(e["date"], "%Y-%m-%d")
        pe = path.get(str(ENTRY))
        alt = {}
        for z in EXITS_COMPARE:
            if z > ENTRY:
                x = trade(path, ENTRY, z)
                alt[str(z)] = x[0] if x else None
        trades.append({
            "token": e["token"], "name": e.get("name"), "unlockDate": e["date"],
            "entryDate": (d0 + timedelta(days=ENTRY)).strftime("%Y-%m-%d"),
            "exitDate": (d0 + timedelta(days=EXIT)).strftime("%Y-%m-%d"),
            "rules": hits, "grade": e.get("grade"), "usdM": e.get("usdM"),
            "pctCirculating": e.get("pctCirculating"), "advDays": e.get("advDays"),
            "investorsShare": round(facts["investorsShare"], 2) if facts["investorsShare"] is not None else None,
            "firstInsiderUnlock": facts["firstInsiderUnlock"],
            "entryVsUnlockDay": pe,  # % the price was above (+) or below (-) the unlock-day price at entry
            "pnl": r[0], "worstAgainst": r[1], "held": r[2],
            "pnlStop": rs[0] if rs else None, "stopped": rs[3] if rs else None,
            "exits": alt,
            "edgeVsRandom": (e.get("shorts") or {}).get(f"{ENTRY}:{EXIT}", {}).get("edge"),
            "live": bool(e.get("predicted")), "check": e.get("check"),
            "momentum": momentum, "skipped": momentum is not None and momentum >= PUMP,
        })
    trades.sort(key=lambda t: t["entryDate"], reverse=True)

    every = trades
    trades = [t for t in every if not t["skipped"]]
    dates = sorted(t["unlockDate"] for t in trades)
    split = dates[len(dates) // 2] if dates else None
    pts, dd = curve(trades)
    pts_s, dd_s = curve([dict(t, pnl=t["pnlStop"]) for t in trades if t["pnlStop"] is not None])
    by_rule = {k: stats([t for t in trades if k in t["rules"]]) for k in RULES}
    exits = {z: stats([{"token": t["token"], "pnl": t["exits"].get(z)} for t in trades if t["exits"].get(z) is not None])
             for z in [str(z) for z in EXITS_COMPARE]}
    edges = [t["edgeVsRandom"] for t in trades if t["edgeVsRandom"] is not None]

    OUT.write_text(json.dumps({
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "playbook": {"entry": ENTRY, "exit": EXIT, "pumpPct": PUMP, "feesPct": FEES, "fundingPctPerDay": FUNDING_DAY,
                     "stopPct": STOP, "notional": NOTIONAL,
                     "rules": {k: {kk: vv for kk, vv in r.items() if kk != "field"} | {"field": r["field"]} for k, r in RULES.items()}},
        "summary": stats(trades), "summaryStop": stats(trades, "pnlStop"),
        "summaryNoGuard": stats(every), "skippedStats": stats([t for t in every if t["skipped"]]),
        "drawdownUsdNoGuard": curve(every)[1],
        "drawdownUsd": dd, "drawdownUsdStop": dd_s, "maxOpen": max_open(trades),
        "medianEdgeVsRandom": round(statistics.median(edges), 2) if edges else None,
        "halves": {"split": split,
                   "first": stats([t for t in trades if t["unlockDate"] < split]) if split else None,
                   "second": stats([t for t in trades if t["unlockDate"] >= split]) if split else None},
        "byRule": by_rule, "exitCompare": exits,
        "live": stats([t for t in trades if t["live"]]),
        "curve": pts, "curveStop": pts_s, "curveNoGuard": curve(every)[0], "trades": every,
        "ids": ids,
        "method": ("Fixed playbook applied to every past unlock in the track record. Entry and exit use CoinGecko "
                   "daily prices at 00:00 UTC; day 0 is the unlock date. Profit is for a short: positive when the "
                   "price fell. Costs assumed: 0.10% fees for the round trip and 0.03% funding per day held. The "
                   "'with stop' version covers at the first daily close 20% above entry, so a real stop-loss order "
                   "could fill earlier or later. The account curve books $1,000 per trade on its exit date. "
                   "Trades are skipped when the token rose 30% or more from 30 days before the unlock to the entry day; "
                   "that guard was chosen after seeing the worst losses, so results are shown with and without it. "
                   "Rules were chosen from published research and this same year of data, so the first-half and "
                   "second-half results and the live-tracked trades are the fairer test."),
    }, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(trades)} signal trades")


if __name__ == "__main__":
    main()
