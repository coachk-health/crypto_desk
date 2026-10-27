#!/usr/bin/env python3
"""Live trade log: every unlock short the page calls from now on, with the levels it showed
and what actually happened. Nothing in it is rewritten later: a call's decision, entry price,
stop and target are frozen when they are made, and only its result is filled in afterwards.

Life of a call (days are relative to the unlock date):
  watching  the unlock matches the playbook; its check day has not come yet. Not frozen.
  check day (day -8): the decision is frozen with the unlock data as it stood then:
              confidence under 60  -> skipped ("data not confirmed")
              otherwise            -> called, waiting for the entry price
  entry (day -7): R = the 00:00 UTC price that day (Binance daily open; CoinGecko if the token is
              not on Binance). Pump check: up 30%+ from day -30 to R -> skipped ("pumped").
              Otherwise open, with zone R to R x 1.03, stop R x (1 + stop%), target R x (1 - target%),
              using the stop and target the page showed on the check day.
  open      checked against each completed day's high and low (same rules as the backtest:
              a day that reaches the stop counts as stopped first; stops fill 0.5% worse).
  closed    stop, target, or covered at 00:00 UTC on day +7. Result after 0.10% fees and
              0.03% funding a day.
A call whose check day passed before this script saw it (for example a missed run) is logged as
"missed" and not counted, so a late entry can never use hindsight.

Runs on GitHub Actions twice a day. Needs api.coingecko.com and data.binance.vision.
Output: data/trade_log.json
"""
import json, sys, time, urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import candles  # noqa: E402
import signals  # noqa: E402

LOG = ROOT / "data" / "trade_log.json"
UNLOCKS = ROOT / "data" / "unlocks.json"
SIGNALS = ROOT / "data" / "signals.json"
START_DATE = "2026-10-28"     # first check day the log covers
CHECK, ENTRY, COVER, PRE = -8, -7, 7, -30
ZONE = 3.0
MIN_CONF = 60
FEES, FUNDING_DAY, SLIP = 0.10, 0.03, 0.5
NOW = datetime.now(timezone.utc)
TODAY = NOW.date()


def iso(d):
    return d.isoformat()


def D(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "coachk-crypto-desk/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode())


def cg_daily(cg_id):
    """CoinGecko 00:00 UTC prices for the last 60 days, {date: price}."""
    j = get(f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart?vs_currency=usd&days=60&interval=daily")
    time.sleep(13)
    return {datetime.fromtimestamp(t / 1000, timezone.utc).date().isoformat(): {"price": p} for t, p in j.get("prices") or []}


def cg_candles(cg_id):
    """CoinGecko 4-hour candles for the last 30 days, merged into UTC days {date: {o,h,l,c}}."""
    j = get(f"https://api.coingecko.com/api/v3/coins/{cg_id}/ohlc?vs_currency=usd&days=30")
    time.sleep(13)
    out = {}
    for t, o, h, l, c in j:
        # a candle's timestamp is its close; the 00:00 candle closes the previous day
        start = datetime.fromtimestamp(t / 1000, timezone.utc) - timedelta(hours=4)
        d = start.date().isoformat()
        x = out.setdefault(d, {"o": o, "h": h, "l": l, "c": c, "n": 0})
        x["h"], x["l"], x["c"], x["n"] = max(x["h"], h), min(x["l"], l), c, x["n"] + 1
    last = max(out) if out else None
    return {d: x for d, x in out.items() if x["n"] == 6 or d != last}  # drop today's unfinished day


def prices(call):
    """Daily candles for the call's token, the same source the backtest would use."""
    cg = None
    try:
        cg = cg_daily(call["coingeckoId"]) if call.get("coingeckoId") else None
    except Exception as e:
        print(f"  CoinGecko daily failed for {call['token']}: {e}")
    if cg is None and call.get("coingeckoId"):
        return None, {}  # cannot confirm the Binance ticker is the same token; try again next run
    src, sym, days = candles.token_days(call["token"], D(call["unlockDate"]) + timedelta(days=PRE - 2), TODAY, cg)
    if src:
        return f"{src} {sym}", days
    if call.get("coingeckoId"):
        try:
            c = cg_candles(call["coingeckoId"])
            for d, x in (cg or {}).items():  # older days: daily price only, for the pump check
                c.setdefault(d, {"o": x["price"], "h": None, "l": None, "c": None})
            return "coingecko", c
        except Exception as e:
            print(f"  CoinGecko candles failed for {call['token']}: {e}")
    return None, {}


def walk(call, days):
    """Apply the stop, target and day +7 cover to completed days from the entry day on."""
    R, lv = call["ref"], call["levels"]
    entry = D(call["entryDate"])
    cover = D(call["coverDate"])
    worst, last = 0.0, None
    d = entry
    while d < cover:
        x = days.get(iso(d))
        if not x or x.get("h") is None:
            break
        o, h, l, c = x["o"], x["h"], x["l"], x["c"]
        exit_px = why = None
        if d > entry and o >= lv["stop"]:
            exit_px, why = o, "stop"
        elif d > entry and lv.get("target") and o <= lv["target"]:
            exit_px, why = o, "target"
        elif h >= lv["stop"]:
            exit_px, why = lv["stop"] * (1 + SLIP / 100), "stop"
        elif lv.get("target") and l <= lv["target"]:
            exit_px, why = lv["target"], "target"
        worst = max(worst, (h / R - 1) * 100)
        if exit_px is not None:
            return close(call, d, exit_px, why, worst)
        last = (d, c)
        d += timedelta(days=1)
    if d == cover and days.get(iso(cover)):
        return close(call, cover, days[iso(cover)]["o"], "time", worst)
    if last:
        held = max(1, (last[0] - entry).days + 1)
        call["mark"] = {"date": iso(last[0]), "price": last[1],
                        "pnl": round((R - last[1]) / R * 100 - FEES - FUNDING_DAY * held, 2)}
    call["worstAgainst"] = round(worst, 2)
    return call


def close(call, d, px, why, worst):
    held = max(1, (d - D(call["entryDate"])).days)
    call.update(status="closed", exit={"date": iso(d), "price": float(f"{px:.6g}"), "why": why},
                pnl=round((call["ref"] - px) / call["ref"] * 100 - FEES - FUNDING_DAY * held, 2),
                worstAgainst=round(worst, 2))
    call.pop("mark", None)
    call["history"].append({"at": NOW.isoformat(timespec="seconds"), "event": f"closed: {why} on {iso(d)} at {px:.6g}, {call['pnl']:+.2f}%"})
    return call


def main():
    log = json.loads(LOG.read_text()) if LOG.exists() else {"startedAt": START_DATE, "calls": []}
    up = json.loads(UNLOCKS.read_text()).get("upcoming") or []
    sig = json.loads(SIGNALS.read_text()) if SIGNALS.exists() else {}
    plan = ((sig.get("levels") or {}).get("plan")) or {"mode": "market", "zone": 0.0, "stop": 35, "target": 30}
    pump = (sig.get("playbook") or {}).get("pumpPct", 30)
    calls = {c["id"]: c for c in log["calls"]}

    # 1) watching: current matches whose check day is still ahead (rebuilt every run, not frozen)
    for cid in [k for k, c in calls.items() if c["status"] == "watching"]:
        del calls[cid]
    for r in up:
        pc = r.get("pctCirculating")
        if pc is None and r.get("pctBasis") == "of circulating":
            pc = r.get("pct")
        facts = {"pctCirculating": pc, "investorsShare": signals.investors_share(r.get("recipientsMix")),
                 "firstInsiderUnlock": r.get("firstInsiderUnlock") is True}
        hits = signals.matched(facts)
        if not hits:
            continue
        u = D(r["date"])
        cid = f"{r['token']}-{r['date']}"
        check = u + timedelta(days=CHECK)
        if iso(check) < log["startedAt"] or cid in calls:
            continue
        base = {"id": cid, "token": r["token"], "name": r.get("name"), "coingeckoId": r.get("coingeckoId"),
                "unlockDate": r["date"], "checkDate": iso(check), "entryDate": iso(u + timedelta(days=ENTRY)),
                "coverDate": iso(u + timedelta(days=COVER)), "rules": hits, "history": []}
        if check > TODAY:
            calls[cid] = dict(base, status="watching")
            continue
        # 2) check day reached: freeze the decision now (or mark it missed if the entry day has passed)
        conf = r.get("confidenceScore") or 0
        base["decision"] = {"confidence": conf, "pctCirculating": pc, "investorsShare": facts["investorsShare"],
                            "firstInsiderUnlock": facts["firstInsiderUnlock"], "usdM": r.get("usdM"),
                            "amount": r.get("amount"), "frozenAt": NOW.isoformat(timespec="seconds")}
        base["plan"] = {"stop": plan["stop"], "target": plan.get("target"), "zone": ZONE, "pumpPct": pump,
                        "fromSignals": sig.get("generatedAt")}
        if TODAY > u + timedelta(days=ENTRY):
            base.update(status="missed", skipReason="not logged before its entry day, so not counted")
        elif conf < MIN_CONF:
            base.update(status="skipped", skipReason=f"unlock data not confirmed (confidence {conf})")
        else:
            base.update(status="called")
        base["history"].append({"at": NOW.isoformat(timespec="seconds"), "event": f"check day: {base['status']}"
                                + (f" ({base.get('skipReason')})" if base.get("skipReason") else "")})
        calls[cid] = base

    # 3) entry and results
    for c in calls.values():
        if c["status"] not in ("called", "open"):
            continue
        if D(c["entryDate"]) > TODAY:
            continue
        print(f"{c['token']} {c['unlockDate']}: {c['status']}")
        src, days = prices(c)
        if not src:
            c.setdefault("note", "no price data yet")
            continue
        if c["status"] == "called":
            e, p0 = days.get(c["entryDate"]), days.get(iso(D(c["unlockDate"]) + timedelta(days=PRE)))
            if not e:
                continue  # entry day's candle not published yet
            R = e["o"]
            c["ref"], c["refSource"] = float(f"{R:.6g}"), src
            c["pump"] = round((R / p0["o"] - 1) * 100, 1) if p0 else None
            if c["pump"] is not None and c["pump"] >= c["plan"]["pumpPct"]:
                c.update(status="skipped", skipReason=f"pumped {c['pump']:.0f}% in the 3 weeks before entry")
                c["history"].append({"at": NOW.isoformat(timespec="seconds"), "event": "entry day: skipped, " + c["skipReason"]})
                continue
            pl = c["plan"]
            c["levels"] = {"zoneLow": c["ref"], "zoneHigh": float(f"{R * (1 + pl['zone'] / 100):.6g}"),
                           "stop": float(f"{R * (1 + pl['stop'] / 100):.6g}"),
                           "target": float(f"{R * (1 - pl['target'] / 100):.6g}") if pl.get("target") else None}
            c["status"] = "open"
            c["history"].append({"at": NOW.isoformat(timespec="seconds"), "event": f"entry: short at {c['ref']:.6g} ({src})"})
        walk(c, days)

    out = sorted(calls.values(), key=lambda c: (c["checkDate"], c["token"]))
    closed = [c for c in out if c["status"] == "closed"]
    v = [c["pnl"] for c in closed]
    log.update(calls=out, updatedAt=NOW.isoformat(timespec="seconds").replace("+00:00", "Z"),
               summary={"closed": len(v), "won": sum(1 for x in v if x > 0),
                        "totalUsd": round(sum(v) * 10) if v else 0,
                        "open": sum(1 for c in out if c["status"] == "open"),
                        "skipped": sum(1 for c in out if c["status"] == "skipped"),
                        "watching": sum(1 for c in out if c["status"] == "watching")},
               method=__doc__.strip())
    LOG.write_text(json.dumps(log, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(log["summary"]))


if __name__ == "__main__":
    main()
