#!/usr/bin/env python3
"""The picks: the only unlock shorts the desk takes (rules frozen in data/strategy_v4.json;
v4 = v3 plus trading on OKX/Bitget/Gate/Hyperliquid when Binance has no perp).

  Take:  an unlock that adds 25%+ of circulating supply, or a first insider unlock whose
         futures open interest fell 10%+ from day -15 to day -8.
  Skip:  price up 30%+ from day -30 to entry, no USDT perpetual on Binance or on another exchange
         whose price confirms it is the same token (scripts/venues.py), or not confirmed.
  Trade: short at the day -7 00:00 UTC open, stop 12% above, target 35% below, cover day +14.

Each call is made once, on entry day, from data known before entry, and written to
data/picks_log.json, which is never rewritten afterwards: that file is the live test.
Prices, open interest: Binance's free files (data.binance.vision); off Binance, the exchange's free API.
Writes data/picks.json.
"""
import csv, io, json, sys, urllib.error, urllib.request, zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import candles, levels, venues  # noqa: E402

RULES = json.loads((ROOT / "data" / ("strategy_v4.json" if (ROOT / "data" / "strategy_v4.json").exists() else "strategy_v3.json")).read_text())
T = RULES["trade"]
STOP, TGT, COVER = T["stopPct"], T["targetPct"], T["coverDay"]
BIG, PUMP, OI_DROP = 25, 30, -10
LOG = ROOT / "data" / "picks_log.json"
OUT = ROOT / "data" / "picks.json"
CACHE = ROOT / "data" / "cache" / "bn"
UM = "https://data.binance.vision/data/futures/um"


def pct_circ(r):
    p = r.get("pctCirculating")
    if p is None and r.get("pctBasis") == "of circulating":
        p = r.get("pct")
    return p


def metrics_oi(sym, d):
    """Open interest (contracts) at the last 5-minute mark of day d, or None if not published."""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"metrics-{sym}-{d}.zip"
    if f.exists() and f.stat().st_size:
        b = f.read_bytes()
    else:
        try:
            req = urllib.request.Request(f"{UM}/daily/metrics/{sym}/{sym}-metrics-{d}.zip",
                                         headers={"User-Agent": "coachk-crypto-desk/1.0"})
            with urllib.request.urlopen(req, timeout=40) as r:
                b = r.read()
            f.write_bytes(b)
        except urllib.error.HTTPError:
            return None
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        rows = [r for n in z.namelist() for r in csv.reader(io.TextIOWrapper(z.open(n))) if r and r[0][:2] == "20"]
    vals = [float(r[2]) for r in rows if r[2]]
    return vals[-1] if vals else None


def oi_change(sym, d0, today):
    """% change in open interest from day -15 to day -8 (or the latest published day, if -8 is not out yet)."""
    for late in (-8, -9, -10):
        dl = d0 + timedelta(days=late)
        if dl >= today:
            continue
        b = metrics_oi(sym, dl)
        a = metrics_oi(sym, dl - timedelta(days=7))
        if a and b:
            return round((b / a - 1) * 100, 1), dl.isoformat()
    return None, None


def oi_change_venue(v, sym, d0, today):
    """Same as oi_change, on another exchange's open-interest history (OKX, Gate)."""
    for late in (-8, -9, -10):
        dl = d0 + timedelta(days=late)
        if dl >= today:
            continue
        b, a = venues.oi_day(v, sym, dl), venues.oi_day(v, sym, dl - timedelta(days=7))
        if a and b:
            return round((b / a - 1) * 100, 1), dl.isoformat()
    return None, None


def bars_for(p, start, end):
    """Daily candles for a pick, from the exchange it is traded on (Binance unless the pick says otherwise)."""
    v = p.get("venue") or "binance"
    if v == "binance":
        return candles.token_days(p["token"], start, end)[2]
    return venues.days(v, p["token"], start, end)[1]


def check(r, today):
    """Return the pick (dict) for one upcoming unlock, or None if it is not a candidate."""
    pc, first = pct_circ(r), r.get("firstInsiderUnlock") is True
    big = (pc or 0) >= BIG
    if not (big or first):
        return None
    d0 = date.fromisoformat(r["date"])
    entry, cover = d0 + timedelta(days=-7), d0 + timedelta(days=COVER)
    if (entry - today).days > 21 or today > cover + timedelta(days=2):
        return None
    p = {"token": r["token"], "name": r.get("name"), "unlockDate": r["date"], "entryDate": entry.isoformat(),
         "coverDate": cover.isoformat(), "pctCirculating": pc, "firstInsider": first,
         "setup": "Big unlock" if big else "First insider unlock", "recipients": r.get("recipients"),
         "confidence": r.get("confidence"), "source": r.get("source")}
    if r.get("confidence") != "confirmed":
        p.update(call="SKIP", why="unlock not confirmed")
        return p
    start, end = d0 - timedelta(days=45), min(today, cover + timedelta(days=1))
    src, sym, days = candles.token_days(r["token"], start, end)
    rows, best = venues.survey(r["token"], r, start, end, days if src else None)
    p["where"] = (["Binance"] if src == "binance-futures" else []) + [x["venue"] for x in rows if x.get("match") is True]
    p["alsoListed"] = [x["venue"] for x in rows if x.get("listed") and x.get("match") is not True and not x.get("note", "").startswith("different")]
    p["venueNotes"] = [f"{x['venue']}: {x['note']}" for x in rows if x.get("note") and x.get("match") is not True]
    if src == "binance-futures":
        p["venue"] = "binance"
    elif best:
        v, sym, days = best
        p.update(venue=v, tradeLink=venues.trade_link(v, sym))
    else:
        wrong = [x["venue"] for x in rows if x.get("match") is False]
        unsure = [x["venue"] for x in rows if x.get("match") is None and x.get("listed")]
        down = [x["venue"] for x in rows if x.get("listed") is None]
        p["venueCheck"] = venues.checked()
        if down and not unsure:
            # a "can't short it" skip needs every exchange checked; until then it stays on watch
            p.update(call="WATCH", why="no Binance perp, and couldn't reach " + ", ".join(down) + " to check; will retry")
            return p
        why = ("can't short it: no USDT perp on Binance, Bybit, OKX, Bitget, Gate, Hyperliquid, KuCoin or MEXC (all checked "
               + p["venueCheck"]["at"] + ")")
        if any(x["venue"] == "Bybit" and x.get("match") is True for x in rows):
            why = ("only Bybit has a perp, and the server can't get Bybit's candles to run the rules (Bybit refuses GitHub's servers), "
                   "so no call; check it by hand if you want it")
        elif unsure:
            why = ("can't short it safely: no Binance perp, and the " + " / ".join(unsure) + " perp can't be confirmed as the same token "
                   "(its price doesn't match CoinGecko's, or there's too little price history)")
        elif wrong:
            why = ("can't short it: no Binance perp, and " + " / ".join(wrong) + f"'s {r['token']} is a different asset (price doesn't match); "
                   "no other exchange lists the real token (all 8 checked " + p["venueCheck"]["at"] + ")")
        p.update(call="SKIP", why=why)
        return p
    p["symbol"] = sym
    bars = {(date.fromisoformat(k) - d0).days: v for k, v in days.items()}
    last = max(bars) if bars else None
    # pump: day -30 open to entry open (or to the latest open before entry)
    ref_day = -7 if -7 in bars else (last if last is not None and last < -7 else None)
    if -30 in bars and ref_day is not None:
        p["pump"] = round((bars[ref_day]["o"] / bars[-30]["o"] - 1) * 100, 1)
        p["pumpTo"] = (d0 + timedelta(days=ref_day)).isoformat()
    if not big:
        p["oiChange"], p["oiTo"] = oi_change(sym, d0, today) if p["venue"] == "binance" else oi_change_venue(p["venue"], sym, d0, today)
    entered = today >= entry
    reasons = []
    if p.get("pump") is not None and p["pump"] >= PUMP:
        reasons.append(f"pumped {p['pump']:+.0f}% into the unlock")
    if not big:
        if p.get("oiChange") is None:
            if p["venue"] in ("bitget", "hyperliquid", "kucoin", "mexc"):
                reasons.append(f"no open-interest history on {venues.NAMES[p['venue']]}")
            else:
                reasons.append("open interest not available yet" if not entered else "no open-interest data")
        elif p["oiChange"] > OI_DROP:
            reasons.append(f"open interest {p['oiChange']:+.0f}% (needs to fall 10%+)")
    if not entered:
        p.update(call="WATCH", why="; ".join(reasons) or "passes so far")
        return p
    if p.get("pump") is None:
        reasons.append("no price history for the pump check")
    p.update(call="SKIP" if reasons else "TAKE", why="; ".join(reasons) or "passes every rule")
    if p["call"] == "TAKE" and -7 in bars:
        P = bars[-7]["o"]
        p["entry"] = float(f"{P:.6g}")
        p["stop"] = float(f"{P * (1 + STOP / 100):.6g}")
        p["target"] = float(f"{P * (1 - TGT / 100):.6g}")
    return p


def follow(p, today):
    """Result of a TAKE so far, on completed daily candles (same rules as the backtest)."""
    d0 = date.fromisoformat(p["unlockDate"])
    days = bars_for(p, d0 - timedelta(days=45), min(today - timedelta(days=1), d0 + timedelta(days=COVER)))
    b = {(date.fromisoformat(k) - d0).days: (v["o"], v["h"], v["l"], v["c"]) for k, v in days.items() if (date.fromisoformat(k) - d0).days >= -7}
    have = max(b) if b else -99
    if -7 in b and not p.get("entry"):  # entry-day candle is published the day after entry
        P = b[-7][0]
        p.update(entry=float(f"{P:.6g}"), stop=float(f"{P * (1 + STOP / 100):.6g}"), target=float(f"{P * (1 - TGT / 100):.6g}"))
    if have >= COVER:
        s = levels.sim(b, "market", 0, STOP, TGT, COVER)
        return {"status": "closed", "R": s["r"], "exit": s["why"], "exitDay": s["exitDay"]} if s else {"status": "open"}
    if -7 in b and have >= -7:
        # still inside the holding period: has the stop or the target been touched yet?
        s = levels.sim({**b, have + 1: b[have]}, "market", 0, STOP, TGT, have + 1)
        if s and s["why"] in ("stop", "target"):
            return {"status": "closed", "R": s["r"], "exit": s["why"], "exitDay": s["exitDay"]}
        now = b[have][3]
        return {"status": "open", "lastClose": float(f"{now:.6g}"), "openPct": round((b[-7][0] - now) / b[-7][0] * 100, 1), "asOf": (d0 + timedelta(days=have)).isoformat()}
    return {"status": "open"}


ENTRY_DAYS, EXIT_DAYS = (-14, -7, -3), (1, 3, 7, 14)


def practice(p, today):
    """Practice comparison for any candidate: the open on days -14/-7/-3 (possible entries) and the
    close on days +1/+3/+7/+14 (possible exits), plus a shadow of the "60% off at the target, rest
    trails 10%" exit on the day -7 entry. Prices only; the page works out the % moves."""
    d0 = date.fromisoformat(p["unlockDate"])
    if today <= d0 + timedelta(days=-14):
        return None
    days = bars_for(p, d0 - timedelta(days=40), min(today - timedelta(days=1), d0 + timedelta(days=30)))
    b = {(date.fromisoformat(k) - d0).days: v for k, v in days.items()}
    if not b:
        return None
    f = lambda v: float(f"{v:.6g}")
    out = {"entries": {str(E): f(b[E]["o"]) for E in ENTRY_DAYS if E in b},
           "exits": {str(X): f(b[X]["c"]) for X in EXIT_DAYS if X in b},
           "lastClose": f(b[max(b)]["c"]), "asOf": (d0 + timedelta(days=max(b))).isoformat()}
    if -7 in b:  # shadow exit: 60% at the 35% target, the rest trails 10% above the lowest low, out by day +30
        P = b[-7]["o"]; sp, tp = P * (1 + STOP / 100), P * (1 - TGT / 100)
        hit, low, res = False, P, None
        for d in range(-7, 31):
            if d not in b:
                break
            o, h, l = b[d]["o"], b[d]["h"], b[d]["l"]
            if not hit:
                if h >= sp:
                    res = {"status": "closed", "pct": round(-STOP - 0.6, 1), "why": "stopped", "day": d}; break
                if l <= tp:
                    hit, low = True, l
                continue
            low = min(low, l); trail = low * 1.10
            if h >= trail:
                pct = 0.6 * TGT + 0.4 * (P - max(o, trail)) / P * 100
                res = {"status": "closed", "pct": round(pct, 1), "why": "target + trailing stop", "day": d}; break
        if res is None:
            last = max(k for k in b if k <= 30)
            now = b[last]["c"]
            pct = (0.6 * TGT + 0.4 * (P - now) / P * 100) if hit else (P - now) / P * 100
            res = {"status": "closed" if last >= 30 else "open", "pct": round(pct, 1),
                   "why": ("60% taken at target, 40% trailing" if hit else "no target yet"), "day": last}
        out["shadowPartial"] = res
    return out


def main():
    today = datetime.now(timezone.utc).date()
    up = json.loads((ROOT / "data" / "unlocks.json").read_text()).get("upcoming", [])
    log = json.loads(LOG.read_text()) if LOG.exists() else {"rules": "data/strategy_v3.json", "calls": []}
    logged = {(c["token"], c["unlockDate"]) for c in log["calls"]}
    picks = []
    for r in up:
        try:
            p = check(r, today)
        except Exception as e:  # one bad token must not stop the rest
            print(f"{r.get('token')}: {e}")
            continue
        if not p:
            continue
        key = (p["token"], p["unlockDate"])
        if key in logged:  # the call made on entry day is final; later data never changes it
            frozen = next(c for c in log["calls"] if (c["token"], c["unlockDate"]) == key)
            p.update({k: frozen[k] for k in ("call", "why", "entry", "stop", "target", "pump", "pumpTo", "oiChange", "oiTo", "lateCall") if k in frozen})
        if p["call"] in ("TAKE", "SKIP") and today >= date.fromisoformat(p["entryDate"]) and key not in logged \
                and p.get("why") != "unlock not confirmed":
            # frozen once, on entry day; later runs only follow the result
            log["calls"].append({**p, "rules": RULES["version"], "calledAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                                 "lateCall": today > date.fromisoformat(p["entryDate"])})
            logged.add(key)
        try:
            p["practice"] = practice(p, today)
        except Exception as e:
            print(f"practice {p['token']}: {e}")
        picks.append(p)
    for c in log["calls"]:
        if c["call"] == "TAKE" and (c.get("result") or {}).get("status") != "closed":
            try:
                c["result"] = follow(c, today)
            except Exception as e:
                print(f"follow {c['token']}: {e}")
    for c in log["calls"]:
        if not (c.get("practice") or {}).get("shadowPartial", {}).get("status") == "closed":
            try:
                c["practice"] = practice(c, today)
            except Exception as e:
                print(f"practice {c['token']}: {e}")
    LOG.write_text(json.dumps(log, indent=1, ensure_ascii=False) + "\n")
    taken = [c for c in log["calls"] if c["call"] == "TAKE" and not c.get("lateCall")]
    closed = [c for c in taken if (c.get("result") or {}).get("status") == "closed"]
    Rs = [c["result"]["R"] for c in closed]
    live = {"taken": len(taken), "closed": len(closed), "won": sum(x > 0 for x in Rs),
            "totalR": round(sum(Rs), 2), "avgR": round(sum(Rs) / len(Rs), 2) if Rs else None}
    order = {"TAKE": 0, "WATCH": 1, "SKIP": 2}
    picks.sort(key=lambda p: (order[p["call"]], p["entryDate"]))
    OUT.write_text(json.dumps({"generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                               "rules": RULES, "picks": picks, "live": live, "log": log["calls"]},
                              indent=1, ensure_ascii=False) + "\n")
    print(f"{len(picks)} candidates: " + ", ".join(f"{p['token']} {p['call']}" for p in picks))


if __name__ == "__main__":
    main()
