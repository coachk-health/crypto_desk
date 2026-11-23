#!/usr/bin/env python3
"""Permanent log of every unlock the desk has ever shown, so nothing disappears once its date passes.

For each (token, unlock date) it keeps: when the desk first and last showed it, the size and details
as first shown and as last shown, the setup grade and pump flag (Trade signals), the v3 Picks call,
and, after the unlock, what the price did (day -7 open to the +1/+3/+7/+14 closes, the biggest rise
and drop, and the result of the standard plan: short the day -7 open, stop 12%, target 35%, out day +14).
Entries are only ever added or filled in, never removed. Writes data/archive.json.

  python3 scripts/archive.py            # update from the current files
  python3 scripts/archive.py --backfill # also replay the git history of the data files first
"""
import json, subprocess, sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import candles, levels  # noqa: E402

OUT = ROOT / "data" / "archive.json"
STOP, TGT, COVER = 12, 35, 14


def pct_circ(r):
    p = r.get("pctCirculating")
    if p is None and r.get("pctBasis") == "of circulating":
        p = r.get("pct")
    return p


def entry_for(E, tok, dt):
    k = f"{tok}|{dt}"
    if k not in E:
        E[k] = {"token": tok, "unlockDate": dt, "firstSeen": None, "lastSeen": None}
    return E[k]


def seen(e, when):
    if not e["firstSeen"] or when < e["firstSeen"]:
        e["firstSeen"] = when
    if not e["lastSeen"] or when > e["lastSeen"]:
        e["lastSeen"] = when


def absorb(E, when, unlocks=None, grades=None, picks=None, log=None):
    for r in (unlocks or {}).get("upcoming", []):
        if not r.get("token") or not r.get("date"):
            continue
        e = entry_for(E, r["token"], r["date"])
        snap = {"pct": pct_circ(r), "usdM": r.get("usdM"), "firstInsider": r.get("firstInsiderUnlock"),
                "confidence": r.get("confidence"), "recipients": r.get("recipients")}
        if not e["firstSeen"] or when <= e["firstSeen"]:
            e["asFirstShown"] = snap
        if not e["lastSeen"] or when >= e["lastSeen"]:
            e["asLastShown"] = snap
            e["name"] = r.get("name") or e.get("name")
        seen(e, when)
    for g in (grades or {}).get("upcoming", []):
        if not g.get("token") or not g.get("date"):
            continue
        e = entry_for(E, g["token"], g["date"])
        if not e.get("gradeAt") or when >= e["gradeAt"]:
            e.update(grade=g.get("grade"), gradeHas=g.get("has"), gradeMissing=g.get("missing"), pumped=g.get("pumped"),
                     momentum=g.get("momentum"), gradeEntry=g.get("entry"), gradeAt=when)
        if not e.get("bestGrade") or (g.get("grade") or "") > (e["bestGrade"] or ""):
            e["bestGrade"] = g.get("grade")
        seen(e, when)
    for p in (picks or {}).get("picks", []):
        e = entry_for(E, p["token"], p["unlockDate"])
        if not e.get("v3At") or when >= e["v3At"]:
            e.update(v3Call=p.get("call"), v3Why=p.get("why"), v3At=when)
        seen(e, when)
    for c in (log or {}).get("calls", []):
        e = entry_for(E, c["token"], c["unlockDate"])
        e.update(v3Call=c.get("call"), v3Why=c.get("why"), v3Final=True, v3LateCall=bool(c.get("lateCall")),
                 v3Result=(c.get("result") or {}))


def git_versions(path):
    out = subprocess.run(["git", "log", "--format=%H %cI", "--", path], cwd=ROOT, capture_output=True, text=True).stdout.split("\n")
    for line in reversed([l for l in out if l.strip()]):
        h, when = line.split()
        try:
            yield when[:16].replace("T", " "), json.loads(subprocess.run(["git", "show", f"{h}:{path}"], cwd=ROOT,
                                                                       capture_output=True, text=True).stdout)
        except Exception:
            continue


def outcome(e, today):
    d0 = date.fromisoformat(e["unlockDate"])
    if today <= d0 + timedelta(days=-6):
        return None
    src, sym, days = candles.token_days(e["token"], d0 - timedelta(days=40), min(today - timedelta(days=1), d0 + timedelta(days=COVER)))
    if not src:
        return {"status": "no prices", "note": "no Binance or CoinGecko daily prices found"}
    b = {(date.fromisoformat(k) - d0).days: v for k, v in days.items()}
    if -7 not in b:
        return {"status": "no prices", "note": "no price on day -7"}
    P = b[-7]["o"]
    f = lambda v: float(f"{v:.6g}")
    mv = lambda x: round((b[x]["c"] / P - 1) * 100, 1) if x in b else None
    upto = [d for d in sorted(b) if -7 <= d <= COVER]
    o = {"source": src, "symbol": sym, "entryOpen": f(P),
         "pump30": round((P / b[-30]["o"] - 1) * 100, 1) if -30 in b else None,
         "move": {"+1": mv(1), "+3": mv(3), "+7": mv(7), "+14": mv(14)},
         "maxRise": round((max(b[d]["h"] for d in upto) / P - 1) * 100, 1),
         "maxDrop": round((min(b[d]["l"] for d in upto) / P - 1) * 100, 1),
         "lastClose": f(b[max(b)]["c"]), "asOf": (d0 + timedelta(days=max(b))).isoformat()}
    bars = {d: (v["o"], v["h"], v["l"], v["c"]) for d, v in b.items()}
    if all(d in bars for d in range(-7, COVER + 1)):
        s = levels.sim(bars, "market", 0, STOP, TGT, COVER)
        o.update(status="closed", planR=s["r"], planExit=s["why"], planExitDay=s["exitDay"])
    else:
        have = max(d for d in bars if d >= -7)
        s = levels.sim({**bars, have + 1: bars[have]}, "market", 0, STOP, TGT, have + 1) if all(d in bars for d in range(-7, have + 1)) else None
        if s and s["why"] in ("stop", "target"):
            o.update(status="closed", planR=s["r"], planExit=s["why"], planExitDay=s["exitDay"])
        else:
            o.update(status="open")
    return o


def main():
    A = json.loads(OUT.read_text()) if OUT.exists() else {"entries": {}}
    E = A["entries"]
    if "--backfill" in sys.argv:
        for path, kw in (("data/unlocks.json", "unlocks"), ("data/grades.json", "grades"), ("data/picks.json", "picks")):
            n = 0
            for when, data in git_versions(path):
                absorb(E, when, **{kw: data}); n += 1
            print(f"replayed {n} versions of {path}")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    rd = lambda p: json.loads((ROOT / p).read_text()) if (ROOT / p).exists() else None
    absorb(E, now, unlocks=rd("data/unlocks.json"), grades=rd("data/grades.json"), picks=rd("data/picks.json"), log=rd("data/picks_log.json"))
    today = datetime.now(timezone.utc).date()
    for e in E.values():
        if (e.get("result") or {}).get("status") in ("closed", "no prices") and e["result"].get("asOf", "9999") >= e["unlockDate"]:
            continue
        try:
            r = outcome(e, today)
            if r:
                e["result"] = r
        except Exception as ex:
            print(f"{e['token']} {e['unlockDate']}: {ex}")
    A.update(generatedAt=now, about="Every unlock the desk has shown, kept after its date passes. Never pruned.")
    OUT.write_text(json.dumps(A, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(E)} unlocks in the log; {sum(1 for e in E.values() if (e.get('result') or {}).get('status') == 'closed')} with a finished result")


if __name__ == "__main__":
    main()
