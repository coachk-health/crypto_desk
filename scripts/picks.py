#!/usr/bin/env python3
"""The v3 picks: the only unlock shorts the desk takes (rules frozen in data/strategy_v3.json).

  Take:  an unlock that adds 25%+ of circulating supply, or a first insider unlock whose
         Binance futures open interest fell 10%+ from day -15 to day -8.
  Skip:  price up 30%+ from day -30 to entry, no Binance USDT perpetual, or not confirmed.
  Trade: short at the day -7 00:00 UTC open, stop 12% above, target 35% below, cover day +14.

Each call is made once, on entry day, from data known before entry, and written to
data/picks_log.json, which is never rewritten afterwards: that file is the live test.
Prices, open interest: Binance's free files (data.binance.vision). Writes data/picks.json.
"""
import csv, io, json, sys, urllib.error, urllib.request, zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import candles, levels  # noqa: E402

RULES = json.loads((ROOT / "data" / "strategy_v3.json").read_text())
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
    src, sym, days = candles.token_days(r["token"], d0 - timedelta(days=45), min(today, cover + timedelta(days=1)))
    if src != "binance-futures":
        p.update(call="SKIP", why="no Binance USDT perpetual")
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
        p["oiChange"], p["oiTo"] = oi_change(sym, d0, today)
    entered = today >= entry
    reasons = []
    if p.get("pump") is not None and p["pump"] >= PUMP:
        reasons.append(f"pumped {p['pump']:+.0f}% into the unlock")
    if not big:
        if p.get("oiChange") is None:
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
    _, _, days = candles.token_days(p["token"], d0 - timedelta(days=45), min(today - timedelta(days=1), d0 + timedelta(days=COVER)))
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
        if p["call"] in ("TAKE", "SKIP") and today >= date.fromisoformat(p["entryDate"]) and key not in logged \
                and p.get("why") != "unlock not confirmed":
            # frozen once, on entry day; later runs only follow the result
            log["calls"].append({**p, "calledAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                                 "lateCall": today > date.fromisoformat(p["entryDate"])})
            logged.add(key)
        picks.append(p)
    for c in log["calls"]:
        if c["call"] == "TAKE" and (c.get("result") or {}).get("status") != "closed":
            try:
                c["result"] = follow(c, today)
            except Exception as e:
                print(f"follow {c['token']}: {e}")
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
