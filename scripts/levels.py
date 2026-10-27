#!/usr/bin/env python3
"""Entry zone, stop-loss and take-profit tests for the unlock short, on daily exchange
candles (open, high, low, close) from scripts/candles.py.

The trade, as a trader would place it:
  Check day   day -8: the unlock data is confirmed and the token has not pumped. P = the price
              at 00:00 UTC on day -7 (the daily open), which sets every level.
  Entry       'market': all at P.
              'ladder z': half at P, half as a sell limit at P x (1 + z%) that only fills if the
              price trades up there before the unlock (day -7 to day -1). Unfilled = smaller trade.
  Stop        buy-stop at P x (1 + stop%), fixed when the trade is planned.
  Target      buy-limit at P x (1 - target%). It must be at least 1.5 times the stop distance
              (reward:risk of 1.5R or more) for a setting to be chosen.
  Time exit   whatever is still open is covered at 00:00 UTC on day +7, +10 or +14 (tested).

Results are measured in R: one R is what a stopped trade loses (the stop distance, plus 0.5%
slippage and fees). Sizing every trade to risk the same dollars (position = risk / stop
distance) makes R the fair way to compare a tight stop with a wide one.

Daily candles do not show the order of moves inside a day, so every guess is the cautious one:
  - a day whose high reaches the stop counts as stopped, even if it also hit the target;
  - a limit sell that fills on a day is exposed to that whole day's high;
  - a stop fills 0.5% worse than its price (slippage), or at the open if the price gapped through.
Costs: 0.10% exchange fees on what was traded, funding 0.03% a day on what was held.
"""
import statistics

FEES = 0.10
FUNDING_DAY = 0.03
SLIP = 0.5
START, END = -7, 7
MIN_RR = 1.5

MODES = [("market", 0.0), ("ladder", 3.0), ("ladder", 5.0), ("ladder", 8.0)]
STOPS = [None, 6, 8, 10, 12, 15, 20, 25, 30, 35]
TARGETS = [None, 10, 15, 20, 25, 30, 35, 40, 50]
COVERS = [7, 10, 14]


def risk(stop):
    """% lost when stopped: stop distance filled 0.5% worse, plus fees."""
    return stop * (1 + SLIP / 100) + SLIP + FEES if stop else None


def rr(stop, target):
    return round(target / stop, 2) if stop and target else None


def bars(ohlc):
    """{day: (open, high, low, close)} as multiples of the unlock-day open."""
    return {int(d): tuple(1 + x / 100 for x in v) for d, v in ohlc.items()}


def sim(b, mode="market", z=0.0, stop=None, target=None, end=None):
    end = end or END
    if any(d not in b for d in range(START, end + 1)):
        return None
    P = b[START][0]
    legs = [{"w": 0.5 if mode == "ladder" else 1.0, "px": P, "day": START}]
    limit = P * (1 + z / 100) if mode == "ladder" else None
    stop_px = P * (1 + stop / 100) if stop else None
    tgt_px = P * (1 - target / 100) if target else None
    exit_px, why, exit_day = None, "time", end
    for d in range(START, end):
        o, h, l, c = b[d]
        if d > START:
            if stop_px and o >= stop_px:
                exit_px, why, exit_day = o, "stop", d
                break
            if tgt_px and o <= tgt_px:
                exit_px, why, exit_day = o, "target", d
                break
        if limit and len(legs) == 1 and d <= -1 and h >= limit:
            legs.append({"w": 0.5, "px": max(o, limit), "day": d})
        if stop_px and h >= stop_px:
            exit_px, why, exit_day = stop_px * (1 + SLIP / 100), "stop", d
            break
        if tgt_px and l <= tgt_px:
            exit_px, why, exit_day = tgt_px, "target", d
            break
    if exit_px is None:
        exit_px = b[end][0]
    pnl, worst = 0.0, 0.0
    for g in legs:
        held = max(1, exit_day - g["day"])
        pnl += g["w"] * ((g["px"] - exit_px) / g["px"] * 100 - FEES - FUNDING_DAY * held)
        hi = max(b[d][1] for d in range(g["day"], exit_day + 1))
        worst = max(worst, g["w"] * (hi / g["px"] - 1) * 100)
    out = {"pnl": round(pnl, 2), "why": why, "filled": round(sum(g["w"] for g in legs), 2),
           "exitDay": exit_day, "worstAgainst": round(worst, 2)}
    if stop:
        out["r"] = round(pnl / risk(stop), 2)
    return out


def stats(rows, notional=1000):
    v = [r["pnl"] for r in rows]
    if not v:
        return None
    wins, losses = [x for x in v if x > 0], [x for x in v if x <= 0]
    s = {"n": len(v), "tokens": len({r["token"] for r in rows}),
         "win": round(100 * len(wins) / len(v)), "median": round(statistics.median(v), 2),
         "worst": round(min(v), 2), "best": round(max(v), 2),
         "profitFactor": round(sum(wins) / abs(sum(losses)), 2) if losses and sum(losses) else None,
         "totalUsd": round(sum(v) / 100 * notional),
         "stops": sum(1 for r in rows if r["why"] == "stop"), "targets": sum(1 for r in rows if r["why"] == "target")}
    rs = [r["r"] for r in rows if r.get("r") is not None]
    if rs:
        srt = sorted(rs)
        s.update(rTotal=round(sum(rs), 1), rMean=round(statistics.mean(rs), 2),
                 rWithoutBest3=round(sum(srt[:-3]), 1) if len(srt) > 3 else None,
                 avgWinR=round(statistics.mean([x for x in rs if x > 0]), 2) if any(x > 0 for x in rs) else None)
    return s


def run(trades, mode, z, s, t, cover):
    rows = []
    for tr in trades:
        r = sim(bars(tr["ohlc"]), mode, z, s, t, cover)
        if r:
            rows.append(dict(r, token=tr["token"], unlockDate=tr["unlockDate"]))
    return rows


def cell(rows, split, **k):
    return dict(k, rr=rr(k["stop"], k["target"]), all=stats(rows),
                first=stats([r for r in rows if r["unlockDate"] < split]),
                second=stats([r for r in rows if r["unlockDate"] >= split]))


def grid(trades, split):
    """Market entry: every stop x target x cover day. Entry modes are compared at the chosen plan."""
    out = []
    for cover in COVERS:
        for s in STOPS:
            for t in TARGETS:
                rows = run(trades, "market", 0.0, s, t, cover)
                if rows:
                    out.append(cell(rows, split, mode="market", zone=0.0, stop=s, target=t, cover=cover))
    return out


def modes(trades, split, plan):
    return [cell(run(trades, m, z, plan["stop"], plan["target"], plan["cover"]), split,
                 mode=m, zone=z, stop=plan["stop"], target=plan["target"], cover=plan["cover"]) for m, z in MODES]


def pick(cells):
    """The plan: a stop is required and the target must be at least MIN_RR times the stop.
    Among those, the setting whose WEAKER half of the year made the most R, averaged with its
    neighbouring stop and target settings so one lucky cell cannot win."""
    idx = {(c["cover"], c["stop"], c["target"]): c for c in cells}

    def worst_half(c):
        if not c or not c["first"] or not c["second"] or c["stop"] is None:
            return None
        return min(c["first"]["rTotal"], c["second"]["rTotal"])

    best, best_score = None, None
    for c in cells:
        if c["stop"] is None or c["target"] is None or c["target"] < MIN_RR * c["stop"]:
            continue
        if (worst_half(c) or 0) <= 0:
            continue
        si, ti = STOPS.index(c["stop"]), TARGETS.index(c["target"])
        near = [idx.get((c["cover"], STOPS[i], TARGETS[j]))
                for i in (si - 1, si, si + 1) for j in (ti - 1, ti, ti + 1)
                if 0 <= i < len(STOPS) and 0 <= j < len(TARGETS) and STOPS[i] is not None and TARGETS[j] is not None]
        vals = [worst_half(n) for n in near if worst_half(n) is not None]
        score = statistics.mean(vals) if vals else None
        if score is not None and (best_score is None or score > best_score):
            best, best_score = c, score
    return best, best_score
