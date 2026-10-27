#!/usr/bin/env python3
"""Past-unlock track record: grades every past unlock with the same rules as the live
page (scripts/score.py), then measures what the price actually did around it.

Prices are measured against Bitcoin, so a move counts only if the token did worse
(or better) than the market. Day 0 is the unlock date; P(d) is the price at 00:00 UTC on
day 0+d (the Binance daily open; CoinGecko only if the token is not on Binance), which is
before the unlock on its own day.

Inputs:  data/past_unlocks.json (researched past events)
         data/unlocks.json      (upcoming rows; any that have now happened are
                                  harvested into past_unlocks.json with their
                                  original prediction attached)
Output:  data/backtest.json
Runs on GitHub Actions (free). Needs network access to api.coingecko.com, data.binance.vision and
coins.llama.fi. Standard library only.
"""
import json, sys, time, statistics, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import score  # noqa: E402
import candles  # noqa: E402

PAST = ROOT / "data" / "past_unlocks.json"
UPCOMING = ROOT / "data" / "unlocks.json"
OUT = ROOT / "data" / "backtest.json"
CACHE = ROOT / "data" / "cache"
NOW = datetime.now(timezone.utc)
PRE, POST = 30, 14
MIN_GROUP = 10   # groups smaller than this are flagged as small samples
ENTRIES = [-30, -14, -7, -3, -1, 0]   # days relative to the unlock to open a short
EXITS = [0, 3, 7, 14]                 # days relative to the unlock to close it
USD_KEYS = ("uPre30", "uPre14", "uPre7", "uPre3", "uPost3", "uPost7", "uPost14", "uAround")
LOG = []


def log(*a):
    s = " ".join(str(x) for x in a)
    LOG.append(s)
    print(s, flush=True)


def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "coachk-crypto-desk/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < tries - 1:
                wait = 30 * (i + 1)
                log(f"  rate limited, waiting {wait}s")
                time.sleep(wait)
                continue
            raise
        except Exception:
            if i < tries - 1:
                time.sleep(5)
                continue
            raise


def day(ts_ms):
    return datetime.fromtimestamp(ts_ms / 1000, timezone.utc).strftime("%Y-%m-%d")


def series(cg_id):
    """Daily {date: {price, mcap, vol}} for the last 365 days. Cached for 20 hours."""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{cg_id}.json"
    if f.exists():
        c = json.loads(f.read_text())
        if (NOW - datetime.fromisoformat(c["fetchedAt"])).total_seconds() < 20 * 3600:
            return c["days"]
    days = {}
    try:
        j = get(f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart?vs_currency=usd&days=365&interval=daily")
        for k, field in (("prices", "price"), ("market_caps", "mcap"), ("total_volumes", "vol")):
            for ts, v in j.get(k) or []:
                days.setdefault(day(ts), {})[field] = v
        source = "coingecko"
        time.sleep(13)  # stay inside the free rate limit
    except Exception as e:
        log(f"  CoinGecko failed for {cg_id}: {e}; trying DefiLlama prices")
        start = int((NOW - timedelta(days=365)).timestamp())
        j = get(f"https://coins.llama.fi/chart/coingecko:{cg_id}?start={start}&span=366&period=1d")
        for p in (j.get("coins", {}).get(f"coingecko:{cg_id}", {}).get("prices") or []):
            days.setdefault(day(p["timestamp"] * 1000), {})["price"] = p["price"]
        source = "defillama"
    if not days:
        raise RuntimeError(f"no price data for {cg_id}")
    f.write_text(json.dumps({"fetchedAt": NOW.isoformat(), "source": source, "days": days}))
    return days


def exchange_series(token, cg):
    """Swap CoinGecko's price for Binance candles where the token trades there (CoinGecko's
    history is wrong for some tokens on some days). Market cap and volume stay CoinGecko's
    (all exchanges); cgPrice is kept so circulating supply = market cap / CoinGecko price.
    Only exchange days are kept, so a series never jumps between two sources."""
    start = (NOW - timedelta(days=366)).date()
    src, sym, bn = candles.token_days(token, start, NOW.date(), cg)
    if not src:
        return cg, {"source": "coingecko", "symbol": None, "cgGapMedianPct": None, "cgGapMaxPct": None}
    out, gaps = {}, []
    for d, x in bn.items():
        c = cg.get(d) or {}
        out[d] = {"price": x["o"], "h": x["h"], "l": x["l"], "c": x["c"], "mcap": c.get("mcap"), "vol": c.get("vol"), "cgPrice": c.get("price")}
        if c.get("price"):
            gaps.append(abs(c["price"] / x["o"] - 1) * 100)
    info = {"source": src, "symbol": sym,
            "cgGapMedianPct": round(statistics.median(gaps), 1) if gaps else None,
            "cgGapMaxPct": round(max(gaps), 1) if gaps else None}
    return out, info


def at(s, d0, off, field="price"):
    k = (d0 + timedelta(days=off)).strftime("%Y-%m-%d")
    v = s.get(k, {}).get(field)
    return v if isinstance(v, (int, float)) and v > 0 else None


def rel(s, b, d0, a, z):
    """Token return from day a to day z, relative to Bitcoin over the same days."""
    p1, p2, b1, b2 = at(s, d0, a), at(s, d0, z), at(b, d0, a), at(b, d0, z)
    if None in (p1, p2, b1, b2):
        return None
    return round(((p2 / p1) / (b2 / b1) - 1) * 100, 2)


def usd(s, d0, a, z):
    """Plain dollar price change from day a to day z, in %."""
    p1, p2 = at(s, d0, a), at(s, d0, z)
    return round((p2 / p1 - 1) * 100, 2) if p1 and p2 else None


def short_baseline(s):
    """For each holding length, the median result of shorting this token on EVERY day of
    the year: the 'random timing' a short around an unlock has to beat."""
    days = sorted(k for k in s if s[k].get("price"))
    px = [s[k]["price"] for k in days]
    out = {}
    for h in sorted({x - e for e in ENTRIES for x in EXITS if x > e}):
        r = [-(px[i + h] / px[i] - 1) * 100 for i in range(len(px) - h)]
        if len(r) >= 60:
            out[h] = statistics.median(r)
    return out


def harvest():
    """Move upcoming rows whose date has passed into past_unlocks.json, keeping the
    grade the live page showed before the unlock, so the system is tested forward."""
    past = json.loads(PAST.read_text()) if PAST.exists() else {"tokens": []}
    up = json.loads(UPCOMING.read_text())
    today = NOW.strftime("%Y-%m-%d")
    by = {t["token"]: t for t in past["tokens"]}
    added = 0
    for u in up.get("upcoming") or []:
        if u["date"] >= today or not u.get("sources"):
            continue
        t = by.get(u["token"])
        if t and not t.get("coingeckoId") and u.get("coingeckoId"):
            t["coingeckoId"] = u["coingeckoId"]
        if not t:
            t = {"token": u["token"], "name": u.get("name"), "coingeckoId": u.get("coingeckoId"), "events": [], "harvested": True}
            past["tokens"].append(t)
            by[u["token"]] = t
        if any(e["date"] == u["date"] for e in t["events"]):
            continue
        t["events"].append({
            "date": u["date"], "timeUTC": u.get("timeUTC"), "amountTokens": u.get("amountTokens"),
            "amountHow": "from the live page's researched row", "type": "cliff" if u.get("type") != "linear" else "linear-monthly",
            "recipientsMix": u.get("recipientsMix"), "sources": u.get("sources"),
            "predicted": {"grade": (u.get("impact") or {}).get("grade"), "points": (u.get("impact") or {}).get("points"),
                          "confidence": u.get("confidenceScore"), "scoredAt": up.get("scoredAt")},
        })
        added += 1
    if added:
        PAST.write_text(json.dumps(past, indent=1, ensure_ascii=False) + "\n")
    log(f"harvested {added} past rows from the live page")
    return past


def bucket_size(p):
    if p is None: return None
    return "under 1%" if p < 1 else "1-5%" if p < 5 else "5-10%" if p < 10 else "10% or more"


def bucket_vol(d):
    if d is None: return None
    return "under 0.25 days" if d < 0.25 else "0.25-1 day" if d < 1 else "1-3 days" if d < 3 else "3+ days"


def who(mix):
    if not isinstance(mix, dict) or not sum(v or 0 for v in mix.values()):
        return None
    tot = sum(v or 0 for v in mix.values())
    s = {k: (mix.get(k) or 0) / tot for k in ("team", "investors", "community", "ecosystem", "other")}
    top = max(s, key=s.get)
    if s[top] >= 0.6:
        return top
    if s["team"] + s["investors"] >= 0.6:
        return "team + investors"
    return "mixed"


def summarise(evs):
    def med(k):
        v = [e["moves"][k] for e in evs if e["moves"].get(k) is not None]
        return round(statistics.median(v), 2) if v else None

    def neg(k):
        v = [e["moves"][k] for e in evs if e["moves"].get(k) is not None]
        return round(100 * sum(1 for x in v if x < 0) / len(v)) if v else None
    lows = [e["lowDay"] for e in evs if e.get("lowDay") is not None]
    path = {}
    for d in range(-PRE, POST + 1):
        v = [e["path"][str(d)] for e in evs if e["path"].get(str(d)) is not None]
        if len(v) >= 3:
            path[str(d)] = round(statistics.median(v), 2)
    def band(k, reps=2000):
        """90% range for the median, resampling whole tokens rather than single unlocks:
        monthly tranches of one token move together, so treating them as independent
        would make the range look tighter than it is. A range that crosses 0 means the
        group's effect is not clear."""
        import random
        by_tok = {}
        for e in evs:
            if e["moves"].get(k) is not None:
                by_tok.setdefault(e["token"], []).append(e["moves"][k])
        toks = list(by_tok.values())
        if sum(len(t) for t in toks) < 5 or len(toks) < 3:
            return None
        rng = random.Random(7)
        meds = []
        for _ in range(reps):
            pick = [x for t in rng.choices(toks, k=len(toks)) for x in t]
            meds.append(statistics.median(pick))
        meds.sort()
        return [round(meds[int(0.05 * reps)], 2), round(meds[int(0.95 * reps) - 1], 2)]
    keys = ("pre30", "pre7", "post7", "post14", "around", "beyondNormal", "normal21") + USD_KEYS
    path_usd = {}
    for d in range(-PRE, POST + 1):
        v = [e["pathUsd"][str(d)] for e in evs if e.get("pathUsd", {}).get(str(d)) is not None]
        if len(v) >= 3:
            path_usd[str(d)] = round(statistics.median(v), 2)
    lows_usd = [e["lowDayUsd"] for e in evs if e.get("lowDayUsd") is not None]

    def grid_band(vals_by_tok, reps=600):
        import random
        toks = list(vals_by_tok.values())
        if sum(len(t) for t in toks) < 5 or len(toks) < 3:
            return None
        rng = random.Random(11)
        meds = sorted(statistics.median([x for t in rng.choices(toks, k=len(toks)) for x in t]) for _ in range(reps))
        return [round(meds[int(0.05 * reps)], 2), round(meds[int(0.95 * reps) - 1], 2)]
    grid = {}
    for a in ENTRIES:
        for z in EXITS:
            if z <= a:
                continue
            k = f"{a}:{z}"
            rows = [(e["token"], e["shorts"][k]) for e in evs if k in (e.get("shorts") or {})]
            if not rows:
                continue
            rets = [r["ret"] for _, r in rows]
            maes = sorted(r["mae"] for _, r in rows)
            edges = [r["edge"] for _, r in rows if r["edge"] is not None]
            by_tok_e = {}
            for t_, r in rows:
                if r["edge"] is not None:
                    by_tok_e.setdefault(t_, []).append(r["edge"])
            grid[k] = {
                "n": len(rows), "median": round(statistics.median(rets), 2), "mean": round(statistics.mean(rets), 2),
                "win": round(100 * sum(1 for x in rets if x > 0) / len(rets)),
                "maeMedian": round(statistics.median(maes), 2), "mae90": round(maes[min(len(maes) - 1, int(0.9 * len(maes)))], 2),
                "edge": round(statistics.median(edges), 2) if edges else None, "edgeRange": grid_band(by_tok_e),
            }
    return {
        "n": len(evs), "tokens": len({e["token"] for e in evs}), "small": len(evs) < MIN_GROUP or len({e["token"] for e in evs}) < 5,
        "median": {k: med(k) for k in keys},
        "pctDown": {k: neg(k) for k in keys},
        "range90": {k: band(k) for k in ("post14", "around", "beyondNormal", "uPre7", "uPost7", "uPost14", "uAround")},
        "pathUsd": path_usd, "grid": grid,
        "medianLowDayUsd": statistics.median(lows_usd) if lows_usd else None,
        "lowDayCountsUsd": {w: sum(1 for x in lows_usd if lo <= x <= hi) for w, lo, hi in
                            (("30-8 days before", -30, -8), ("final week before", -7, -1), ("unlock day", 0, 0),
                             ("days 1-7 after", 1, 7), ("days 8-14 after", 8, 14))},
        "medianLowDay": statistics.median(lows) if lows else None,
        "lowDayCounts": {w: sum(1 for x in lows if lo <= x <= hi) for w, lo, hi in
                         (("30-8 days before", -30, -8), ("final week before", -7, -1), ("unlock day", 0, 0),
                          ("days 1-7 after", 1, 7), ("days 8-14 after", 8, 14))},
        "path": path,
    }


def main():
    past = harvest()
    btc, _ = exchange_series("BTC", series("bitcoin"))
    events, skipped = [], []
    sources = {}
    for t in past["tokens"]:
        cg = t.get("coingeckoId")
        evs = [e for e in t.get("events") or [] if e.get("date") and e.get("type") != "continuous"]
        if not cg or not evs:
            if evs:
                skipped.append({"token": t["token"], "why": "no CoinGecko id"})
            continue
        log(f"{t['token']} ({cg}): {len(evs)} events")
        try:
            s, info = exchange_series(t["token"], series(cg))
        except Exception as e:
            log(f"  skipped: {e}")
            skipped.append({"token": t["token"], "why": f"price data unavailable ({e})"})
            continue
        sources[t["token"]] = info
        log(f"  prices: {info['source']} {info['symbol'] or ''} (CoinGecko differed by a median {info['cgGapMedianPct']}%, at most {info['cgGapMaxPct']}%)")
        # The token's normal 3-week drift against Bitcoin over the whole year, so an unlock is
        # only blamed for what it did beyond the token's usual trend.
        common = sorted(k for k in s if s[k].get("price") and btc.get(k, {}).get("price"))
        drift21 = None
        if len(common) >= 120:
            a, z = common[0], common[-1]
            span = (datetime.strptime(z, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days
            ratio = (s[z]["price"] / s[a]["price"]) / (btc[z]["price"] / btc[a]["price"])
            if span > 0 and ratio > 0:
                drift21 = ratio ** (21 / span) - 1
        base = short_baseline(s)
        for e in evs:
            d0 = datetime.strptime(e["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if d0 + timedelta(days=POST) > NOW:
                continue  # not enough days after yet; it will be measured later
            p0 = at(s, d0, 0)
            if p0 is None or at(s, d0, -7) is None or at(s, d0, POST) is None:
                skipped.append({"token": t["token"], "date": e["date"], "why": "no price around the date (outside the 365-day free history)"})
                continue
            vols = [at(s, d0, -i, "vol") for i in range(1, 31)]
            vols = [v for v in vols if v]
            mcap1 = at(s, d0, -1, "mcap")
            p1 = at(s, d0, -1, "cgPrice") or (at(s, d0, -1) if info["source"] == "coingecko" else None)
            circ = mcap1 / p1 if mcap1 and p1 else None
            amt = e.get("amountTokens")
            usdM = round(amt * p0 / 1e6, 3) if amt else None
            row = {
                "token": t["token"], "type": "linear" if e.get("type") == "linear" else "cliff",
                "usdM": usdM,
                "pctCirculating": round(100 * amt / circ, 3) if amt and circ else None,
                "recipientsMix": e.get("recipientsMix"),
                "market": {
                    "advUsdM": round(statistics.mean(vols) / 1e6, 3) if len(vols) >= 20 else None,
                    "advBasis": "30d avg",
                    "circPctOfMax": round(100 * circ / t["maxSupply"], 2) if circ and t.get("maxSupply") else None,
                    "listed": t.get("listed"),
                },
            }
            imp = score.sell_pressure(row, d0)
            moves = {
                "pre30": rel(s, btc, d0, -PRE, 0), "pre7": rel(s, btc, d0, -7, 0),
                "post7": rel(s, btc, d0, 0, 7), "post14": rel(s, btc, d0, 0, POST),
                "around": rel(s, btc, d0, -7, POST),
            }
            moves["normal21"] = round(drift21 * 100, 2) if drift21 is not None else None
            moves["beyondNormal"] = (round(((1 + moves["around"] / 100) / (1 + drift21) - 1) * 100, 2)
                                     if moves["around"] is not None and drift21 is not None else None)
            umoves = {"uPre30": usd(s, d0, -30, 0), "uPre14": usd(s, d0, -14, 0), "uPre7": usd(s, d0, -7, 0),
                      "uPre3": usd(s, d0, -3, 0), "uPost3": usd(s, d0, 0, 3), "uPost7": usd(s, d0, 0, 7),
                      "uPost14": usd(s, d0, 0, POST), "uAround": usd(s, d0, -7, POST)}
            moves.update(umoves)
            path_usd = {}
            for d in range(-PRE, POST + 1):
                r = usd(s, d0, 0, d) if d != 0 else 0.0
                if r is not None:
                    path_usd[str(d)] = r
            shorts = {}
            for a in ENTRIES:
                for z in EXITS:
                    if z <= a:
                        continue
                    pa, pz = at(s, d0, a), at(s, d0, z)
                    if not pa or not pz:
                        continue
                    hold = [at(s, d0, d) for d in range(a, z + 1)]
                    hold = [x for x in hold if x]
                    ret = round(-(pz / pa - 1) * 100, 2)
                    mae = round((max(hold) / pa - 1) * 100, 2)  # worst move against the short while held (daily closes)
                    b = base.get(z - a)
                    shorts[f"{a}:{z}"] = {"ret": ret, "mae": mae, "edge": round(ret - b, 2) if b is not None else None}
            path = {}
            for d in range(-PRE, POST + 1):
                r = rel(s, btc, d0, 0, d) if d != 0 else 0.0
                if r is not None:
                    path[str(d)] = r
            # Daily candles as % of the unlock-day open, for entry-zone, stop and target tests.
            ohlc = {}
            if info["source"] != "coingecko":
                for d in range(-8, POST + 1):
                    k = (d0 + timedelta(days=d)).strftime("%Y-%m-%d")
                    x = s.get(k)
                    if x and x.get("h"):
                        ohlc[str(d)] = [round((x[f] / p0 - 1) * 100, 3) for f in ("price", "h", "l", "c")]
            win = {d: v for d, v in path.items() if -PRE <= int(d) <= POST}
            low_day = int(min(win, key=win.get)) if win else None
            # biggest single-day drop vs Bitcoin, days -14..+14
            drops = {}
            for d in range(-14, POST + 1):
                r = rel(s, btc, d0, d - 1, d)
                if r is not None:
                    drops[d] = r
            worst = min(drops, key=drops.get) if drops else None
            events.append({
                "token": t["token"], "name": t.get("name"), "date": e["date"],
                "amountTokens": amt, "usdM": usdM, "pctCirculating": row["pctCirculating"],
                "advDays": round(usdM / row["market"]["advUsdM"], 3) if usdM and row["market"]["advUsdM"] else None,
                "type": e.get("type"), "firstInsiderUnlock": bool(e.get("firstInsiderUnlock")),
                "recipientsMix": e.get("recipientsMix"), "who": who(e.get("recipientsMix")),
                "grade": imp["grade"], "points": imp["points"], "factors": imp["factors"],
                "predicted": e.get("predicted"),
                "moves": moves, "path": path, "pathUsd": path_usd, "ohlc": ohlc, "priceSource": info["source"],
                "shorts": shorts, "lowDay": low_day,
                "lowDayUsd": int(min(path_usd, key=path_usd.get)) if path_usd else None,
                "worstDay": worst, "worstDayMove": drops.get(worst) if worst is not None else None,
                "sources": e.get("sources") or [],
                "check": (t.get("verify") or {}).get("status"),
                "checkNotes": (t.get("verify") or {}).get("notes"),
            })
    events.sort(key=lambda e: e["date"], reverse=True)
    log(f"measured {len(events)} events, skipped {len(skipped)}")

    groups = {"All unlocks": summarise(events)}
    def add(prefix, key):
        vals = sorted({key(e) for e in events if key(e) is not None})
        for v in vals:
            groups[f"{prefix}: {v}"] = summarise([e for e in events if key(e) == v])
    add("Grade", lambda e: e["grade"])
    add("Who receives", lambda e: e["who"])
    add("Size vs circulating", lambda e: bucket_size(e["pctCirculating"]))
    add("Size vs daily trading", lambda e: bucket_vol(e["advDays"]))
    add("Kind", lambda e: "first insider unlock" if e["firstInsiderUnlock"] else "routine tranche")
    def setup(e):
        hp = e["who"] == "investors" or (e["pctCirculating"] or 0) >= 10 or (e["advDays"] or 0) >= 3
        return "high pressure" if hp else "everything else"
    add("Setup", setup)
    pred = [e for e in events if e.get("predicted") and e["predicted"].get("grade")]
    if pred:
        add("Live-page prediction", lambda e: (e.get("predicted") or {}).get("grade"))

    per_token = {}
    for e in events:
        per_token.setdefault(e["token"], []).append(e)
    tok_stats = {}
    for t_, evs_ in per_token.items():
        def md(k):
            v = [x["moves"].get(k) for x in evs_ if x["moves"].get(k) is not None]
            return round(statistics.median(v), 2) if v else None
        sh = [x["shorts"].get("-7:7", {}).get("ret") for x in evs_ if x.get("shorts", {}).get("-7:7")]
        tok_stats[t_] = {"n": len(evs_), "last": max(x["date"] for x in evs_),
                         "uPre7": md("uPre7"), "uPost7": md("uPost7"), "uPost14": md("uPost14"), "uAround": md("uAround"),
                         "shortWin": round(100 * sum(1 for x in sh if x > 0) / len(sh)) if sh else None,
                         "shortMedian": round(statistics.median(sh), 2) if sh else None}
    bdays = sorted(k for k in btc if btc[k].get("price"))
    btc_year = round((btc[bdays[-1]]["price"] / btc[bdays[0]]["price"] - 1) * 100, 1) if bdays else None

    OUT.write_text(json.dumps({
        "btcYear": btc_year, "btcFrom": bdays[0] if bdays else None, "btcTo": bdays[-1] if bdays else None,
        "perToken": tok_stats, "priceSources": sources,
        "gridSpec": {"entries": ENTRIES, "exits": EXITS},
        "generatedAt": NOW.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "window": {"pre": PRE, "post": POST},
        "benchmark": "Bitcoin",
        "method": ("Each move is the token's price change relative to Bitcoin over the same days, from Binance "
                   "perpetual-futures daily candles where the token trades there (else Binance spot, else CoinGecko), "
                   "using the price at 00:00 UTC (day 0 is the unlock date, so its price is from before the unlock). "
                   "CoinGecko's own history was wrong for some tokens on some days, so it is only the last resort. "
                   "Grades use the same rules as the live page, with size, trading volume and circulating supply "
                   "taken from CoinGecko as they were the day before each unlock. Monthly tranches of the same token "
                   "overlap: the 30 days before one unlock include the 14 days after the previous one. "
                   "'Beyond normal' compares each unlock's three weeks (7 days before to 14 after) with the token's own "
                   "average three-week drift against Bitcoin over the whole year, so a token that slides all year is not "
                   "blamed on its unlock. For tokens that unlock every month that average already contains unlocks, so this "
                   "measure understates their effect. Dollar moves are plain USD price changes. Short results are the % gained by "
                   "shorting at the entry day's price and covering at the exit day's price, before fees and funding; 'worst "
                   "move against you' is the highest daily close while the short was open, so intraday spikes were worse. "
                   "'Edge over random timing' subtracts the median result of shorting the same token for the same number of "
                   "days starting on every day of the year. Ranges are 90% ranges for the median, found by resampling whole tokens (not single unlocks), because one token's monthly tranches move together."),
        "groups": groups, "events": events, "skipped": skipped,
    }, indent=1, ensure_ascii=False) + "\n")
    (ROOT / "data" / "backtest-log.txt").write_text("\n".join(LOG) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        log(traceback.format_exc())
        (ROOT / "data" / "backtest-log.txt").write_text("\n".join(LOG) + "\n")
        raise
