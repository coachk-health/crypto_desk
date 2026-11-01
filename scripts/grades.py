#!/usr/bin/env python3
"""Setup grades (A, AA, AAA): which unlock shorts have the best past record, re-learned every day.

The loop. Every daily run (after backtest.py and signals.py):
  1. Take every past unlock that has exchange candles and passed the pump check, and replay the
     current playbook on it (short 7 days before, stop and target from signals.json, cover after).
  2. Test each candidate condition ("edge") on its own: average R of trades that have it, minus
     trades that do not. A condition is CONFIRMED only if it helps in both halves of the record,
     by at least MIN_LIFT, with at least MIN_N trades on MIN_TOKENS different tokens. One lucky
     token or one good month cannot confirm it. Conditions that help overall but fail one half
     are WATCHING; conditions that cost money are HURTS.
  3. Grades, in two layers so stacked conditions are not double counted:
       A   = has at least one confirmed base edge (the setups that made money at all);
       AA  = an A setup with one confirmed BOOSTER; AAA = an A setup with two or more.
     A booster is tested only inside the A setups (A trades with it vs A trades without it),
     with the same both-halves rule, because conditions overlap: most first unlocks are also
     big ones, so counting both would grade the same thing twice. If no booster has enough
     evidence yet, AA and AAA stay empty and the page says so.
  4. Honest test (walk-forward): month by month, choose the edges using only trades that had
     already closed, then grade the next month's trades with them. Those trades were never used
     to pick the edges, so this is the closest thing to live results the past can give.
  5. Grade the upcoming unlocks the same way, and save a dated snapshot so the page can show
     how the edges change as more unlocks are added.

"Holders in profit" uses the price on the check day against the token's first Binance price.
Most private investors bought well below that, so above it means early holders are almost
certainly in profit. Researched investor round prices (data/investor_entry.json) are kept for a
later, stricter test once enough tokens have a confirmed price.

Input:  data/backtest.json, data/signals.json, data/past_unlocks.json, data/unlocks.json
Output: data/grades.json
Network: data.binance.vision only (cached in data/cache/bn). Standard library only.
"""
import json, re, statistics, sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import candles  # noqa: E402
import levels  # noqa: E402

OUT = ROOT / "data" / "grades.json"
NOW = datetime.now(timezone.utc)
TODAY = NOW.date()
ENTRY = -7
PUMP = 30.0
MIN_N, MIN_TOKENS, MIN_LIFT = 10, 4, 0.10      # base edges, tested on every trade
MIN_WITH_R = 0.15                               # a base edge's own trades must average at least this
B_MIN_N, B_MIN_TOKENS, B_MIN_LIFT = 8, 5, 0.15  # boosters, tested inside the A setups only
WF_MIN_HISTORY = 60          # closed trades needed before the walk-forward starts grading
HISTORY_KEEP = 180

EDGES = {
    "first":     {"label": "First insider unlock", "plain": "The first time the team or investors can sell."},
    "investors": {"label": "Investors get 30%+", "plain": "At least 30% of the unlock goes to private investors."},
    "team":      {"label": "Team gets 30%+", "plain": "At least 30% of the unlock goes to the team and advisors."},
    "big":       {"label": "10%+ of supply", "plain": "The unlock adds 10% or more to the tokens already trading."},
    "cliff":     {"label": "One-day cliff", "plain": "Released in one go, not drip-fed monthly."},
    "liquid":    {"label": "1+ day of volume", "plain": "The unlock is worth at least one full day of trading volume."},
    "inProfit":  {"label": "Holders in profit", "plain": "Price on the check day is above the token's first Binance price, so early holders can sell at a profit."},
    "waited":    {"label": "Waited 12+ months", "plain": "The token has been trading for a year or more, so insiders have waited out a cliff."},
    "thinFloat": {"label": "Under 30% circulating", "plain": "Less than 30% of the max supply is trading, so a lot more is still to come."},
    "falling":   {"label": "Already falling", "plain": "The price fell over the 3 weeks before entry."},
}


def share(mix, key):
    if not isinstance(mix, dict):
        return None
    tot = sum(v or 0 for v in mix.values())
    return (mix.get(key) or 0) / tot if tot else None


def months_between(listed, d):
    try:
        y, m = map(int, listed.split("-")[:2])
    except Exception:
        return None
    return (d.year - y) * 12 + d.month - m


_launch = {}


def launch_price(token, listed):
    """First daily open on Binance (futures, else spot) for the token: (price, date) or (None, None)."""
    if token in _launch:
        return _launch[token]
    out = (None, None)
    try:
        y, m = map(int, (listed or "2019-09").split("-")[:2])
        start = date(y, m, 1) - timedelta(days=62)
    except Exception:
        start = date(2019, 9, 1)
    for _, path in candles.MARKETS:
        for sym, scale in ((f"{token}USDT", 1.0), (f"1000{token}USDT", 1000.0)):
            # walk months forward from a little before the listing month to the first file that exists
            for yy, mm in candles._months(start, TODAY):
                if (yy, mm) >= (TODAY.year, TODAY.month):
                    break
                tag = f"{yy}-{mm:02d}"
                b = candles._fetch(f"{candles.BASE}/{path}/monthly/klines/{sym}/1d/{sym}-1d-{tag}.zip",
                                   f"{path.replace('/', '_')}-{sym}-{tag}.zip")
                if b:
                    rows = candles._rows(b)
                    if rows:
                        d0 = min(rows)
                        out = (rows[d0]["o"] / scale, d0)
                    break
            if out[0]:
                break
        if out[0]:
            break
    _launch[token] = out
    return out


_days = {}


def token_series(token):
    """All Binance daily candles for a token from 2025-09 to today, fetched once."""
    if token not in _days:
        try:
            _, _, _days[token] = candles.token_days(token, date(2025, 9, 1), TODAY)
        except Exception:
            _days[token] = {}
    return _days[token]


def day_open(token, d):
    """Binance daily open on date d (the price a short placed at 00:00 UTC would get)."""
    days = token_series(token)
    x = days.get(d.isoformat())
    return (x["o"] if x else None), days


def float_pct(e):
    for f in e.get("factors") or []:
        if f.get("key") == "float":
            m = re.search(r"([\d.]+)% of max supply", f.get("detail") or "")
            if m:
                return float(m.group(1))
    return None


def facts_past(e, listed):
    d0 = datetime.strptime(e["date"], "%Y-%m-%d").date()
    entry = d0 + timedelta(days=ENTRY)
    p = e.get("path") or {}
    p30, pen = p.get("-30"), p.get(str(ENTRY))
    mom = ((1 + pen / 100) / (1 + p30 / 100) - 1) * 100 if p30 is not None and pen is not None else None
    inv, team = share(e.get("recipientsMix"), "investors"), share(e.get("recipientsMix"), "team")
    lp, _ = launch_price(e["token"], listed) if e.get("priceSource", "").startswith("binance") else (None, None)
    px, _ = day_open(e["token"], entry - timedelta(days=1)) if lp else (None, None)
    age = months_between(listed, d0) if listed else None
    fl = float_pct(e)
    f = {
        "first": bool(e.get("firstInsiderUnlock")),
        "investors": inv is not None and inv >= 0.3,
        "team": team is not None and team >= 0.3,
        "big": (e.get("pctCirculating") or 0) >= 10,
        "cliff": e.get("type") == "cliff",
        "liquid": (e.get("advDays") or 0) >= 1,
        "inProfit": (px / lp >= 1) if (px and lp) else None,
        "waited": (age >= 12) if age is not None else None,
        "thinFloat": (fl < 30) if fl is not None else None,
        "falling": (mom < 0) if mom is not None else None,
    }
    extra = {"momentum": round(mom, 1) if mom is not None else None, "vsLaunch": round((px / lp - 1) * 100, 1) if px and lp else None,
             "monthsListed": age, "floatPct": fl}
    return f, extra


def rstats(rows):
    rs = [r["r"] for r in rows if r.get("r") is not None]
    if not rs:
        return None
    return {"n": len(rs), "tokens": len({r["token"] for r in rows}), "win": round(100 * sum(1 for x in rs if x > 0) / len(rs)),
            "meanR": round(statistics.mean(rs), 2), "totalR": round(sum(rs), 1),
            "medianR": round(statistics.median(rs), 2)}


def judge(trades, split, min_n=MIN_N, min_tok=MIN_TOKENS, min_lift=MIN_LIFT, min_with=None):
    """Per-edge verdict on a set of trades. Returns {edge: {...}} and the confirmed list."""
    out, confirmed = {}, []
    for k in EDGES:
        known = [t for t in trades if t["facts"].get(k) is not None]
        w = [t for t in known if t["facts"][k]]
        wo = [t for t in known if not t["facts"][k]]
        sw, swo = rstats(w), rstats(wo)
        if not sw or not swo:
            out[k] = {"with": sw, "without": swo, "lift": None, "status": "not enough data"}
            continue
        lift = sw["meanR"] - swo["meanR"]
        halves = []
        for part in ([t for t in known if t["unlockDate"] < split], [t for t in known if t["unlockDate"] >= split]):
            a, b = rstats([t for t in part if t["facts"][k]]), rstats([t for t in part if not t["facts"][k]])
            halves.append(round(a["meanR"] - b["meanR"], 2) if a and b else None)
        enough = sw["n"] >= min_n and sw["tokens"] >= min_tok
        both = all(h is not None and h > 0 for h in halves)
        if enough and both and lift >= min_lift and (min_with is None or sw["meanR"] >= min_with):
            status = "confirmed"
            confirmed.append(k)
        elif lift > 0 and enough:
            status = "watching"
        elif lift > 0:
            status = "too few trades"
        else:
            status = "hurts"
        out[k] = {"with": sw, "without": swo, "lift": round(lift, 2), "halves": halves, "status": status}
    return out, confirmed


def learn(trades):
    """Base edges on all trades, then boosters inside the A setups. Returns (base, boosters, verdicts)."""
    dates = sorted(t["unlockDate"] for t in trades)
    split = dates[len(dates) // 2]
    base_v, base = judge(trades, split, min_with=MIN_WITH_R)
    inside = [t for t in trades if any(t["facts"].get(k) for k in base)]
    boost_v, boosters = {}, []
    if len(inside) >= 2 * B_MIN_N:
        di = sorted(t["unlockDate"] for t in inside)
        boost_v, boosters = judge(inside, di[len(di) // 2], B_MIN_N, B_MIN_TOKENS, B_MIN_LIFT)
    return base, boosters, base_v, boost_v, split


def grade_of(facts, base, boosters):
    if not any(facts.get(k) for k in base):
        return None, 0
    n = sum(1 for k in boosters if facts.get(k))
    return ("A", "AA", "AAA")[min(n, 2)], n


def ladder(trades, key="grade"):
    g = {}
    for name in ("AAA", "AA", "A", None):
        g[name or "none"] = rstats([t for t in trades if t[key] == name])
    return g


def ladder_holds(g):
    seq = [g[k]["meanR"] for k in ("AAA", "AA", "A", "none") if g.get(k)]
    return all(a >= b for a, b in zip(seq, seq[1:])) if len(seq) >= 2 else None


def main():
    bt = json.loads((ROOT / "data" / "backtest.json").read_text())
    sg = json.loads((ROOT / "data" / "signals.json").read_text())
    past = json.loads((ROOT / "data" / "past_unlocks.json").read_text())
    upc = json.loads((ROOT / "data" / "unlocks.json").read_text())
    listed = {t["token"]: t.get("listed") for t in past.get("tokens", [])}
    linear_tokens = {e["token"] for e in bt["events"] if str(e.get("type", "")).startswith("linear")}
    P = sg["levels"]["plan"]

    trades = []
    for e in bt["events"]:
        if not e.get("ohlc"):
            continue
        sim = levels.sim(levels.bars(e["ohlc"]), P["mode"], P["zone"], P["stop"], P["target"], P["cover"])
        if not sim or sim.get("r") is None:
            continue
        f, x = facts_past(e, listed.get(e["token"]))
        if x["momentum"] is not None and x["momentum"] >= PUMP:
            continue  # the playbook would have skipped it
        d0 = datetime.strptime(e["date"], "%Y-%m-%d").date()
        trades.append({"token": e["token"], "unlockDate": e["date"], "entryDate": (d0 + timedelta(days=ENTRY)).isoformat(),
                       "exitDate": (d0 + timedelta(days=sim["exitDay"])).isoformat(), "r": sim["r"], "pnl": sim["pnl"],
                       "why": sim["why"], "facts": f, **x})
    trades.sort(key=lambda t: t["entryDate"])
    dates = sorted(t["unlockDate"] for t in trades)
    split = dates[len(dates) // 2]

    base, boosters, edges, boost_v, split = learn(trades)
    confirmed = base
    for t in trades:
        t["grade"], t["edgeCount"] = grade_of(t["facts"], base, boosters)

    # walk-forward: pick edges from closed trades only, grade the next month
    wf_rows, wf_log = [], []
    months = sorted({t["entryDate"][:7] for t in trades})
    for m in months:
        start = m + "-01"
        hist = [t for t in trades if t["exitDate"] < start]
        if len(hist) < WF_MIN_HISTORY:
            continue
        b_m, bo_m, _, _, _ = learn(hist)
        month_trades = [t for t in trades if t["entryDate"][:7] == m]
        for t in month_trades:
            g, _ = grade_of(t["facts"], b_m, bo_m)
            wf_rows.append(dict(t, wfGrade=g))
        wf_log.append({"month": m, "edges": b_m, "boosters": bo_m, "trades": len(month_trades)})

    # upcoming unlocks, graded with today's confirmed edges
    upcoming = []
    for u in upc.get("upcoming", []):
        try:
            d0 = datetime.strptime(u["date"], "%Y-%m-%d").date()
        except Exception:
            continue
        entry = d0 + timedelta(days=ENTRY)
        if d0 < TODAY or (d0 - TODAY).days > 45:
            continue
        m = u.get("market") or {}
        lst = m.get("listed") or listed.get(u["token"])
        inv, team = share(u.get("recipientsMix"), "investors"), share(u.get("recipientsMix"), "team")
        ref_day = min(entry, TODAY)
        lp, _ = launch_price(u["token"], lst)
        px, days = day_open(u["token"], ref_day) if lp else (None, {})
        if lp and not px and days:
            px = days[max(days)]["c"]  # today's open not published yet: latest close
        a = days.get((ref_day - timedelta(days=23)).isoformat()) if days else None
        mom = (px / a["o"] - 1) * 100 if (px and a) else None
        adv = u["usdM"] / m["advUsdM"] if u.get("usdM") and m.get("advUsdM") and m.get("advBasis") and "24h" not in m["advBasis"].lower() else None
        age = months_between(lst, d0) if lst else None
        cpm = m.get("circPctOfMax")
        f = {
            "first": u.get("firstInsiderUnlock") is True,
            "investors": inv is not None and inv >= 0.3,
            "team": team is not None and team >= 0.3,
            "big": (u.get("pctCirculating") or (u.get("pct") if u.get("pctBasis") == "of circulating" else 0) or 0) >= 10,
            # The live data calls each monthly step a "cliff"; the track record calls those linear.
            # Trust "cliff" only when the token has no monthly-release history in the track record.
            "cliff": (u.get("type") or "") == "cliff" and u["token"] not in linear_tokens,
            "liquid": adv >= 1 if adv is not None else None,
            "inProfit": (px / lp >= 1) if (px and lp) else None,
            "waited": (age >= 12) if age is not None else None,
            "thinFloat": (cpm < 30) if isinstance(cpm, (int, float)) else None,
            "falling": (mom < 0) if mom is not None else None,
        }
        g, n = grade_of(f, base, boosters)
        keys = base + [k for k in boosters if k not in base]
        upcoming.append({"token": u["token"], "name": u.get("name"), "date": u["date"], "usdM": u.get("usdM"),
                         "entry": entry.isoformat(), "grade": g, "edgeCount": n,
                         "has": [k for k in keys if f.get(k)], "missing": [k for k in keys if f.get(k) is False],
                         "unknown": [k for k in keys if f.get(k) is None],
                         "pumped": mom is not None and mom >= PUMP, "momentum": round(mom, 1) if mom is not None else None,
                         "vsLaunch": round((px / lp - 1) * 100, 1) if px and lp else None,
                         "priceAsOf": ref_day.isoformat() if px else None,
                         "confidenceScore": u.get("confidenceScore")})
    upcoming.sort(key=lambda x: (("AAA", "AA", "A", None).index(x["grade"]), x["date"]))

    full = ladder(trades)
    wf = ladder(wf_rows, "wfGrade")
    snap = {"date": TODAY.isoformat(), "trades": len(trades), "confirmed": confirmed, "boosters": boosters,
            "meanR": {k: (v["meanR"] if v else None) for k, v in full.items()},
            "wfMeanR": {k: (v["meanR"] if v else None) for k, v in wf.items()}}
    hist = []
    if OUT.exists():
        try:
            hist = json.loads(OUT.read_text()).get("history", [])
        except Exception:
            hist = []
    hist = [h for h in hist if h.get("date") != snap["date"]] + [snap]

    best = [t for t in reversed(trades) if t["grade"] == "AAA"][:12]
    out = {
        "generatedAt": NOW.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "plan": {k: P[k] for k in ("stop", "target", "cover", "riskPct")}, "riskUsd": sg["levels"].get("riskUsd", 100),
        "rules": {"minN": MIN_N, "minTokens": MIN_TOKENS, "minLift": MIN_LIFT, "minWithR": MIN_WITH_R, "pumpPct": PUMP, "split": split,
                  "wfMinHistory": WF_MIN_HISTORY},
        "sample": {"trades": len(trades), "tokens": len({t["token"] for t in trades}),
                   "from": trades[0]["entryDate"] if trades else None, "to": trades[-1]["entryDate"] if trades else None},
        "edges": [{"key": k, **EDGES[k], **edges[k]} for k in sorted(EDGES, key=lambda k: -(edges[k]["lift"] if edges[k]["lift"] is not None else -9))],
        "confirmed": confirmed, "boosters": boosters,
        "boosterTests": [{"key": k, **EDGES[k], **boost_v[k]} for k in sorted(boost_v, key=lambda k: -(boost_v[k]["lift"] if boost_v[k]["lift"] is not None else -9))],
        "boosterRules": {"minN": B_MIN_N, "minTokens": B_MIN_TOKENS, "minLift": B_MIN_LIFT},
        "ladder": full, "ladderHolds": ladder_holds(full),
        "walkForward": {"ladder": wf, "holds": ladder_holds(wf), "trades": len(wf_rows), "months": wf_log,
                        "from": wf_log[0]["month"] if wf_log else None},
        "upcoming": upcoming,
        "recentAAA": [{k: t[k] for k in ("token", "unlockDate", "r", "why", "vsLaunch")} for t in best],
        "history": hist[-HISTORY_KEEP:],
        "method": __doc__.strip(),
    }
    OUT.write_text(json.dumps(out, indent=1))
    print(f"grades: {len(trades)} trades, confirmed edges {confirmed}, ladder holds {out['ladderHolds']}, "
          f"walk-forward {len(wf_rows)} trades holds {out['walkForward']['holds']}, {len(upcoming)} upcoming graded")


if __name__ == "__main__":
    main()
