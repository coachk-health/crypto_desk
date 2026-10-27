#!/usr/bin/env python3
"""Entry zone, stop-loss and take-profit tests for the unlock short, on daily exchange
candles (open, high, low, close) from scripts/candles.py.

The trade, as a trader would place it:
  Check day   day -8: the unlock data is confirmed and the token has not pumped. R = the price
              at 00:00 UTC on day -7 (the daily open), which sets every level.
  Entry zone  'market': all at R.
              'ladder z': half at R, half as a sell limit at R x (1 + z%) that only fills if the
              price trades up there before the unlock (day -7 to day -1). Unfilled = smaller trade.
  Stop        buy-stop at R x (1 + stop%), fixed when the trade is planned.
  Target      buy-limit at R x (1 - target%).
  Time exit   whatever is still open is covered at 00:00 UTC on day +7.

Daily candles do not show the order of moves inside a day, so every guess is the cautious one:
  - a day whose high reaches the stop counts as stopped, even if it also hit the target;
  - a limit sell that fills on a day is exposed to that whole day's high;
  - a stop fills 0.5% worse than its price (slippage), or at the open if the price gapped through.
Costs: 0.10% exchange fees on what was traded, funding 0.03% a day on what was held.
Results are % of the planned position (a half-filled ladder risks and earns on half).
"""
import statistics

FEES = 0.10
FUNDING_DAY = 0.03
SLIP = 0.5
START, END = -7, 7

MODES = [("market", 0.0), ("ladder", 3.0), ("ladder", 5.0), ("ladder", 8.0)]
STOPS = [None, 10, 15, 20, 25, 30, 35, 40, 50]
TARGETS = [None, 10, 15, 20, 25, 30, 40, 50]


def bars(ohlc):
    """{day: (open, high, low, close)} as multiples of the unlock-day open."""
    return {int(d): tuple(1 + x / 100 for x in v) for d, v in ohlc.items()}


def sim(b, mode="market", z=0.0, stop=None, target=None):
    if any(d not in b for d in range(START, END + 1)):
        return None
    R = b[START][0]
    legs = [{"w": 0.5 if mode == "ladder" else 1.0, "px": R, "day": START}]
    limit = R * (1 + z / 100) if mode == "ladder" else None
    stop_px = R * (1 + stop / 100) if stop else None
    tgt_px = R * (1 - target / 100) if target else None
    exit_px, why, exit_day = None, "time", END
    for d in range(START, END):
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
        exit_px = b[END][0]
    pnl, worst = 0.0, 0.0
    for g in legs:
        held = max(1, exit_day - g["day"])
        pnl += g["w"] * ((g["px"] - exit_px) / g["px"] * 100 - FEES - FUNDING_DAY * held)
        hi = max(b[d][1] for d in range(g["day"], exit_day + 1))
        worst = max(worst, g["w"] * (hi / g["px"] - 1) * 100)
    return {"pnl": round(pnl, 2), "why": why, "filled": round(sum(g["w"] for g in legs), 2),
            "exitDay": exit_day, "worstAgainst": round(worst, 2)}


def stats(rows, notional=1000):
    v = [r["pnl"] for r in rows]
    if not v:
        return None
    wins, losses = [x for x in v if x > 0], [x for x in v if x <= 0]
    return {"n": len(v), "tokens": len({r["token"] for r in rows}),
            "win": round(100 * len(wins) / len(v)), "median": round(statistics.median(v), 2),
            "worst": round(min(v), 2), "best": round(max(v), 2),
            "profitFactor": round(sum(wins) / abs(sum(losses)), 2) if losses and sum(losses) else None,
            "totalUsd": round(sum(v) / 100 * notional),
            "stops": sum(1 for r in rows if r["why"] == "stop"), "targets": sum(1 for r in rows if r["why"] == "target")}


def grid(trades, split):
    """trades: [{token, unlockDate, ohlc}]. Every mode x stop x target, with half-year totals."""
    out = []
    for mode, z in MODES:
        for s in STOPS:
            for t in TARGETS:
                rows = []
                for tr in trades:
                    r = sim(bars(tr["ohlc"]), mode, z, s, t)
                    if r:
                        rows.append(dict(r, token=tr["token"], unlockDate=tr["unlockDate"]))
                if not rows:
                    continue
                a = stats([r for r in rows if r["unlockDate"] < split])
                bb = stats([r for r in rows if r["unlockDate"] >= split])
                out.append({"mode": mode, "zone": z, "stop": s, "target": t, "all": stats(rows),
                            "first": a, "second": bb})
    return out


def pick(cells):
    """Choose the plan that held up in BOTH halves of the year, smoothed over neighbouring stop and
    target settings so a lucky single cell does not win. Plans without a stop are not eligible:
    one squeeze can cost more than 100%."""
    idx = {(c["mode"], c["zone"], c["stop"], c["target"]): c for c in cells}

    def worst_half(c):
        if not c["first"] or not c["second"]:
            return None
        return min(c["first"]["totalUsd"], c["second"]["totalUsd"])

    best, best_score = None, None
    for c in cells:
        if c["stop"] is None:
            continue
        si, ti = STOPS.index(c["stop"]), TARGETS.index(c["target"])
        near = [idx.get((c["mode"], c["zone"], STOPS[i], TARGETS[j]))
                for i in (si - 1, si, si + 1) for j in (ti - 1, ti, ti + 1)
                if 0 <= i < len(STOPS) and 0 <= j < len(TARGETS) and STOPS[i] is not None]
        vals = [worst_half(n) for n in near if n and worst_half(n) is not None]
        if not vals:
            continue
        score = statistics.mean(vals)
        if best_score is None or score > best_score:
            best, best_score = c, score
    return best, best_score
