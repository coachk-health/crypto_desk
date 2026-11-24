#!/usr/bin/env python3
"""Data for the morning brief artifact: what to short today, what is open, what is coming up.

Read-only: it uses the frozen v3 rules (data/strategy_v3.json) through scripts/picks.py's own checks,
with fresh Binance daily prices and open interest, and the live call log (data/picks_log.json).
It never writes the desk's files. Run it shortly before 00:00 UTC (07:00 Bangkok), when entries open.

  python3 scripts/morning_brief.py OUTDIR   -> OUTDIR/setups.json, OUTDIR/record.json (for the artifact)
  python3 scripts/morning_brief.py --site [--snapshot]
        -> data/brief.json for the brief page (brief.html); with --snapshot also
           data/briefs/<Bangkok date>.json and data/briefs/index.json (one kept per morning, never deleted)
"""
import json, sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import picks  # noqa: E402

BKK = timezone(timedelta(hours=7))
CODE_NOTE = "Built by scripts/morning_brief.py in coachk-health/crypto_desk from the frozen v3 rules (data/strategy_v3.json)."


def tv(sym):
    return f"https://www.tradingview.com/chart/?symbol=BINANCE:{sym}.P" if sym else None


def row(p, section, action, **extra):
    d0 = date.fromisoformat(p["unlockDate"])
    r = {"id": f"{p['token']}|{p['unlockDate']}", "section": section, "token": p["token"], "name": p.get("name") or p["token"],
         "setup": p.get("setup"), "unlockDate": p["unlockDate"], "entryDate": p.get("entryDate") or (d0 - timedelta(days=7)).isoformat(),
         "coverDate": p.get("coverDate") or (d0 + timedelta(days=14)).isoformat(),
         "sizePct": round(p["pctCirculating"], 1) if p.get("pctCirculating") is not None else None,
         "firstInsider": bool(p.get("firstInsider")), "pumpPct": p.get("pump"), "oiChangePct": p.get("oiChange"),
         "call": p.get("call"), "why": p.get("why"), "action": action,
         "entry": p.get("entry"), "stop": p.get("stop"), "target": p.get("target"),
         "chart": tv(p.get("symbol") or (p["token"] + "USDT")), "lateCall": bool(p.get("lateCall"))}
    r.update(extra)
    return r


def main(outdir, site=False, snapshot=False):
    out = Path(outdir); out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    today = (now + timedelta(hours=7)).date()      # the day whose 00:00 UTC open is the next entry
    ups = json.loads((ROOT / "data" / "unlocks.json").read_text()).get("upcoming", [])
    log = json.loads((ROOT / "data" / "picks_log.json").read_text()) if (ROOT / "data" / "picks_log.json").exists() else {"calls": []}
    logged = {(c["token"], c["unlockDate"]): c for c in log["calls"]}
    rows, seen = [], set()
    for r in ups:
        try:
            p = picks.check(r, today)
        except Exception as e:
            print(f"{r.get('token')}: {e}")
            continue
        if not p:
            continue
        key = (p["token"], p["unlockDate"])
        if key in logged:
            continue                                   # already called; shown from the log below
        seen.add(key)
        e = date.fromisoformat(p["entryDate"])
        days = (e - today).days
        if days == 0 and p["call"] == "TAKE":
            rows.append(row(p, "today", "Short at the 00:00 UTC open (07:00 Bangkok) today. Stop 12% above the entry, target 35% below, out by "
                            + date.fromisoformat(p["coverDate"]).strftime("%-d %b") + ".", daysToEntry=0))
        elif days == 0:
            rows.append(row(p, "skipped", "Skip: " + p["why"] + ".", daysToEntry=0))
        elif days > 0 and p["call"] == "WATCH":
            need = ["price not up 30%+ since 30 days before the unlock"]
            if not ((p.get("pctCirculating") or 0) >= picks.BIG):
                need.append("open interest down 10%+ in the week before entry")
            rows.append(row(p, "coming", ("Decided at the " + e.strftime("%-d %b") + " open. Needs: " + "; ".join(need)
                                          + ". Now: " + p["why"] + "."), daysToEntry=days))
        elif p["call"] == "SKIP":
            rows.append(row(p, "skipped", "Skip: " + p["why"] + ".", daysToEntry=days))
    for c in log["calls"]:
        if c["call"] != "TAKE":
            continue
        res = c.get("result") or {}
        try:
            res = picks.follow(c, now.date()) if res.get("status") != "closed" else res
        except Exception as ex:
            print(f"follow {c['token']}: {ex}")
        d0 = date.fromisoformat(c["unlockDate"])
        if res.get("status") == "closed":
            if (now.date() - d0).days <= 30:
                rows.append(row(c, "closed", ("Closed: " + {"stop": "stopped", "target": "target hit", "time": "out on day +14"}.get(res.get("exit"), res.get("exit") or "")
                                              + (" (called late, not counted)" if c.get("lateCall") else "") + "."),
                                resultR=res.get("R")))
        else:
            rows.append(row(c, "open", ("Open short. Out by " + date.fromisoformat(c["coverDate"]).strftime("%-d %b") + " unless the stop or target hits first."
                                        + (" Called late, not counted." if c.get("lateCall") else "")),
                            lastClose=res.get("lastClose"), shortPct=res.get("openPct"), asOf=res.get("asOf")))
    order = {"today": 0, "open": 1, "coming": 2, "closed": 3, "skipped": 4}
    rows.sort(key=lambda r: (order[r["section"]], r["entryDate"]))
    meta = [{"label": "Rules", "value": "v3, frozen 19 Nov 2026: short 25%+ unlocks, or first insider unlocks with open interest down 10%+; skip anything up 30%+ going in. Short the day -7 open, stop 12%, target 35%, out day +14."},
            {"label": "Prices", "value": "Binance USDT perpetual daily candles and open interest (data.binance.vision)."},
            {"label": "Made", "value": now.strftime("%Y-%m-%d %H:%M UTC")}, {"label": "Code", "value": CODE_NOTE}]
    (out / "setups.json").write_text(json.dumps({"rows": rows, "meta": meta}, indent=1, ensure_ascii=False))
    calls = [c for c in log["calls"] if c["call"] == "TAKE"]
    counted = [c for c in calls if not c.get("lateCall") and (c.get("result") or {}).get("status") == "closed"]
    bt = picks.RULES["backtest"]
    rec = [{"id": "live", "label": "Live record (counted)", "trades": len(counted), "won": sum((c["result"]["R"] or 0) > 0 for c in counted),
            "totalR": round(sum(c["result"]["R"] for c in counted), 2), "avgR": round(sum(c["result"]["R"] for c in counted) / len(counted), 2) if counted else None},
           {"id": "backtest", "label": "Backtest (56 trades, 2023-2026)", "trades": bt["trades"], "won": round(bt["trades"] * bt["wonPct"] / 100),
            "totalR": bt["totalR"], "avgR": bt["avgR"]}]
    (out / "record.json").write_text(json.dumps({"rows": rec, "meta": [{"label": "Live calls", "value": "data/picks_log.json: called once on entry day, never rewritten; late calls not counted."},
                                                                      {"label": "Backtest", "value": "data/strategy_v3.json"}, {"label": "Made", "value": now.strftime("%Y-%m-%d %H:%M UTC")}]}, indent=1))
    if site:
        keep = ("token", "name", "setup", "unlockDate", "entryDate", "coverDate", "pctCirculating", "firstInsider", "pump", "oiChange",
                "call", "why", "lateCall", "entry", "stop", "target", "calledAt")
        calls = []
        for c in log["calls"]:
            x = {k: c.get(k) for k in keep}
            x["result"] = c.get("result")
            calls.append(x)
        calls.sort(key=lambda c: c["entryDate"], reverse=True)
        brief = {"made": now.strftime("%Y-%m-%d %H:%M UTC"), "day": today.isoformat(), "rules": meta[0]["value"],
                 "setups": rows, "record": rec, "calls": calls}
        data = ROOT / "data"
        (data / "brief.json").write_text(json.dumps(brief, indent=1, ensure_ascii=False) + "\n")
        if snapshot:
            d = data / "briefs"; d.mkdir(exist_ok=True)
            (d / f"{today.isoformat()}.json").write_text(json.dumps(brief, indent=1, ensure_ascii=False) + "\n")
            days = sorted((f.stem for f in d.glob("20*.json")), reverse=True)
            (d / "index.json").write_text(json.dumps({"days": days}, indent=1) + "\n")
    print(f"{today}: " + ", ".join(f"{r['section']}:{r['token']}" for r in rows))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0] if args else "/tmp/brief", site="--site" in sys.argv, snapshot="--snapshot" in sys.argv)
