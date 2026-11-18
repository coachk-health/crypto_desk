#!/usr/bin/env python3
"""Test the frozen v3 rules (data/strategy_v3.json) on the 2021-2025 unlock history
researched with scripts/history-research.md.

  python3 research/hist_test.py out0.json out1.json ...

Data rules, fixed before any price is looked at:
- drop events flagged migration, relocked or launch, events with dateConflict, events whose
  first insider unlock was at launch, and events with no date
- the token must have a Binance USDT perpetual with daily candles from day -30 (so the pump check
  and the trade are possible); the ticker check (35%) uses the researched priceUsd
- a big unlock is pctCirculating >= 25; a first insider unlock is firstInsiderUnlock true
Writes research/hist_test.json.
"""
import csv, io, json, random, statistics as st, sys, urllib.error, urllib.request, zipfile, collections
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import candles, levels  # noqa: E402

R3 = json.loads((ROOT / "data" / "strategy_v3.json").read_text())
STOP, TGT, COVER = R3["trade"]["stopPct"], R3["trade"]["targetPct"], R3["trade"]["coverDay"]
CACHE = Path("/home/claude/work/dl")
CACHE.mkdir(parents=True, exist_ok=True)
UM = "https://data.binance.vision/data/futures/um"


def metrics_oi(sym, d):
    f = CACHE / f"m-{sym}-{d}.zip"
    if f.exists():
        b = f.read_bytes()
    else:
        try:
            with urllib.request.urlopen(urllib.request.Request(f"{UM}/daily/metrics/{sym}/{sym}-metrics-{d}.zip",
                                        headers={"User-Agent": "desk"}), timeout=40) as r:
                b = r.read()
        except urllib.error.HTTPError:
            b = b""
        f.write_bytes(b)
    if not b:
        return None
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        rows = [r for n in z.namelist() for r in csv.reader(io.TextIOWrapper(z.open(n))) if r and r[0][:2] == "20"]
    v = [float(r[2]) for r in rows if r[2]]
    return v[-1] if v else None


BTC = {}


def btc_move(d0):
    if not BTC:
        _, _, days = candles.token_days("BTC", date(2020, 10, 1), date(2025, 12, 31))
        BTC.update({date.fromisoformat(k): v for k, v in days.items()})
    a, b = BTC.get(d0 - timedelta(days=37)), BTC.get(d0 - timedelta(days=7))
    return round((b["o"] / a["o"] - 1) * 100, 1) if a and b else None


def boot(rows, n=3000):
    by = collections.defaultdict(list)
    for r in rows:
        by[r["token"]].append(r["R"])
    g = list(by.values())
    rng = random.Random(3)
    m = sorted(st.mean([v for x in rng.choices(g, k=len(g)) for v in x]) for _ in range(n))
    return round(m[int(n * .05)], 2), round(m[int(n * .95)], 2)


def S(rows):
    if not rows:
        return "—"
    v = [r["R"] for r in rows]
    s = f"n={len(v):>3} won {round(100 * sum(x > 0 for x in v) / len(v)):>3}% avg {st.mean(v):+.2f}R total {sum(v):+6.1f}R"
    return s + (f" range {boot(rows)}" if len(rows) >= 5 else "")


def main(paths):
    ev, dropped = [], []
    for p in paths:
        for t in json.loads(Path(p).read_text()):
            fiu = t.get("firstInsiderUnlock") or {}
            for e in t.get("events") or []:
                e = dict(e, token=t["token"])
                why = None
                if not e.get("date"):
                    why = "no date"
                elif set(e.get("flags") or []) & {"migration", "relocked", "launch"}:
                    why = "flag " + ",".join(sorted(set(e["flags"]) & {"migration", "relocked", "launch"}))
                elif e.get("dateConflict"):
                    why = "date conflict"
                elif e.get("firstInsiderUnlock") and fiu.get("atLaunch"):
                    why = "first insider unlock was at launch"
                (dropped.append((t["token"], e.get("date"), why)) if why else ev.append(e))
    rows, seen = [], set()
    for e in sorted(ev, key=lambda e: (e["token"], e["date"])):
        k = (e["token"], e["date"])
        if k in seen:
            continue
        seen.add(k)
        d0 = date.fromisoformat(e["date"])
        src, sym, days = candles.token_days(e["token"], d0 - timedelta(days=40), d0 + timedelta(days=COVER + 1))
        if src != "binance-futures":
            dropped.append((*k, "no Binance perpetual")); continue
        b = {(date.fromisoformat(x) - d0).days: (v["o"], v["h"], v["l"], v["c"]) for x, v in days.items()}
        if any(x not in b for x in (-30, -14, -7, 0)) or any(x not in b for x in range(-7, COVER + 1)):
            dropped.append((*k, "perpetual not trading for the whole trade")); continue
        p = e.get("priceUsd")
        if p and abs(b[0][0] / p - 1) > 0.35:
            dropped.append((*k, f"ticker check: Binance {b[0][0]:.4g} vs {p}")); continue
        s = levels.sim(b, "market", 0, STOP, TGT, COVER)
        pct = e.get("pctCirculating")
        big = (pct or 0) >= 25
        first = bool(e.get("firstInsiderUnlock"))
        oa, ob = metrics_oi(sym, d0 - timedelta(days=15)), metrics_oi(sym, d0 - timedelta(days=8))
        r = {"token": e["token"], "date": e["date"], "year": e["date"][:4], "pct": pct, "first": first, "big": big,
             "shape": e.get("shape"), "flags": e.get("flags") or [], "mix": e.get("recipientsMix"),
             "pump": round((b[-7][0] / b[-30][0] - 1) * 100, 1), "week": round((b[-7][0] / b[-14][0] - 1) * 100, 1),
             "oiChg": round((ob / oa - 1) * 100, 1) if oa and ob else None, "btc30": btc_move(d0),
             "after": round((b[COVER][3] / b[-7][0] - 1) * 100, 1), "R": s["r"], "why": s["why"], "exitDay": s["exitDay"]}
        if r["pump"] >= 30:
            r["call"] = "SKIP pumped"
        elif big:
            r["call"] = "TAKE big"
        elif first and r["oiChg"] is not None and r["oiChg"] <= -10:
            r["call"] = "TAKE first+OI"
        elif first:
            r["call"] = "SKIP first, OI not falling" if r["oiChg"] is not None else "SKIP first, no OI data"
        else:
            r["call"] = "not a setup"
        rows.append(r)
    out = {"rules": "data/strategy_v3.json", "rows": rows, "dropped": dropped}
    (ROOT / "research" / "hist_test.json").write_text(json.dumps(out, indent=1) + "\n")
    T = [r for r in rows if r["call"].startswith("TAKE")]
    print("V3 TAKE (all years)   ", S(T))
    for c in sorted({r["call"] for r in rows}):
        print(f"  {c:<28}", S([r for r in rows if r["call"] == c]))
    for y in sorted({r["year"] for r in rows}):
        print(f"  {y} TAKE", S([r for r in T if r["year"] == y]))
    print("dropped", len(dropped), collections.Counter(d[2].split(":")[0] for d in dropped).most_common())


if __name__ == "__main__":
    main(sys.argv[1:])
