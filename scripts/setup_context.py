#!/usr/bin/env python3
"""Reference context for each upcoming signal, shown beside the setup on the page:

  1. Last distribution: what the token's price did around its previous unlock, on the same
     scale as the track record: % change from 30, 14 and 7 days before up to the unlock day,
     and from the unlock day to 7 and 14 days after (00:00 UTC daily opens, Binance where the
     token trades there, else CoinGecko). Flags: pumped into it (+20% or more over the 30 days
     before) and what followed (+/-15% over the 14 days after).
  2. Chart levels: the nearest swing highs above the price (resistance) and swing lows below
     it (support) over the last 120 days. A swing high is a daily high that is the highest of
     the 3 days either side; a swing low the same for lows.

Neither changes the plan. Tested on 41 past signal trades: stops placed above resistance and
targets at support made less than the fixed 12% stop / 35% target (best chart-based version
+18.7R against +20.8R), and a pump at a token's previous unlock did not predict the next one
(+0.00R across 47 such past unlocks). They are shown so the trader can see the chart, not as rules.
"""
import json, time, urllib.request
from datetime import datetime, timedelta, timezone

import candles

LOOKBACK = 120
W = 3


def _cg(cg_id, days):
    url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart?vs_currency=usd&days={days}&interval=daily"
    req = urllib.request.Request(url, headers={"User-Agent": "coachk-crypto-desk/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as f:
        j = json.load(f)
    time.sleep(13)
    return {datetime.fromtimestamp(t / 1000, timezone.utc).date().isoformat(): {"price": p, "o": p, "h": None, "l": None, "c": p}
            for t, p in j.get("prices") or []}


def candles_for(token, cg_id, start, end, cg_days=None):
    """(source, {date: {o,h,l,c}}): Binance when the ticker is confirmed to be this token, else CoinGecko."""
    src, sym, days = candles.token_days(token, start, end, cg_days)
    if src:
        return f"{src} {sym}", {d: x for d, x in days.items() if start.isoformat() <= d <= end.isoformat()}
    return ("coingecko", {d: x for d, x in (cg_days or {}).items() if start.isoformat() <= d <= end.isoformat()}) if cg_days else (None, {})


def levels_from(days, ref):
    ds = sorted(days)
    hi, lo = [], []
    for i in range(W, len(ds) - W):
        win = [days[ds[j]] for j in range(i - W, i + W + 1)]
        x = days[ds[i]]
        if x.get("h") is not None and x["h"] == max(w["h"] for w in win if w.get("h") is not None):
            hi.append((ds[i], x["h"]))
        if x.get("l") is not None and x["l"] == min(w["l"] for w in win if w.get("l") is not None):
            lo.append((ds[i], x["l"]))
    above = sorted([(p, d) for d, p in hi if p > ref * 1.01])[:2]
    below = sorted([(p, d) for d, p in lo if p < ref * 0.99], reverse=True)[:2]
    f = lambda p: float(f"{p:.6g}")
    highs = [x["h"] for x in days.values() if x.get("h") is not None]
    lows = [x["l"] for x in days.values() if x.get("l") is not None]
    return {"resistance": [{"price": f(p), "pct": round((p / ref - 1) * 100, 1), "date": d} for p, d in above],
            "support": [{"price": f(p), "pct": round((p / ref - 1) * 100, 1), "date": d} for p, d in below],
            "high": f(max(highs)) if highs else None, "low": f(min(lows)) if lows else None}


def moves_around(days, date):
    d0 = datetime.strptime(date, "%Y-%m-%d").date()
    at = lambda k: (days.get((d0 + timedelta(days=k)).isoformat()) or {}).get("o")
    p0 = at(0)
    if not p0:
        return None
    out = {}
    for k in (-30, -14, -7):
        p = at(k)
        out[f"pre{-k}"] = round((p0 / p - 1) * 100, 1) if p else None
    for k in (7, 14):
        p = at(k)
        out[f"post{k}"] = round((p / p0 - 1) * 100, 1) if p else None
    out["pumpedInto"] = out["pre30"] is not None and out["pre30"] >= 20
    out["after"] = ("pumped" if out["post14"] is not None and out["post14"] >= 15 else
                    "dumped" if out["post14"] is not None and out["post14"] <= -15 else
                    "flat" if out["post14"] is not None else None)
    return out


def context(rows, past_dates):
    """rows: upcoming signal rows (dicts from unlocks.json). past_dates: {token: [dates]} of past events on file."""
    today = datetime.now(timezone.utc).date()
    out = {}
    # one context per token: its next unlock still ahead (or the latest one if all have passed)
    rows = sorted(rows, key=lambda r: (r["date"] < today.isoformat(), r["date"]))
    for r in rows:
        tok, cg_id = r["token"], r.get("coingeckoId")
        if tok in out or not cg_id:
            continue
        try:
            cg = _cg(cg_id, 365)
        except Exception as e:
            print(f"context {tok}: CoinGecko failed: {e}")
            continue
        item = {"asOf": today.isoformat()}
        try:
            src, days = candles_for(tok, cg_id, today - timedelta(days=LOOKBACK), today, cg)
            if days:
                ref = days[max(days)]["c"] or days[max(days)]["o"]
                item.update(levels_from(days, ref), ref=float(f"{ref:.6g}"), source=src)
        except Exception as e:
            print(f"context {tok}: levels failed: {e}")
        last = (r.get("lastDistribution") or {}).get("date")
        last_src = "researched"
        if not last:
            prior = [d for d in past_dates.get(tok, []) if d < r["date"]]
            last, last_src = (max(prior), "track record") if prior else (None, None)
        if last:
            try:
                d = datetime.strptime(last, "%Y-%m-%d").date()
                s2, days2 = candles_for(tok, cg_id, d - timedelta(days=31), min(today, d + timedelta(days=15)), cg)
                mv = moves_around(days2, last) if days2 else None
                item["last"] = dict(mv or {}, date=last, basis=last_src, source=s2,
                                    what=(r.get("lastDistribution") or {}).get("recipients"),
                                    kind=(r.get("lastDistribution") or {}).get("kind"))
            except Exception as e:
                print(f"context {tok}: last distribution failed: {e}")
        elif r.get("lastDistributionNote"):
            item["last"] = {"date": None, "note": r["lastDistributionNote"]}
        out[tok] = item
    return out
