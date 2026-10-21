#!/usr/bin/env python3
"""Scores every token unlock in data/unlocks.json. Deterministic: the same facts
always give the same scores, so nothing here is an opinion typed in by hand.

  Confidence (0-100): how sure we are the unlock is real and correctly sized,
                      from how many independent sources confirm it, and how recently.
  Sell pressure:      Low / Moderate / High / Very high, from the unlock's features
                      that published studies link to bigger price drops.

Run:  python3 scripts/score.py          rewrite the scores in data/unlocks.json
      python3 scripts/score.py --check  exit 1 if any stored score is out of date
"""
import json, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

VERSION = 1
DATA = Path(__file__).resolve().parent.parent / "data" / "unlocks.json"

EVIDENCE = {
    "keyrock": {
        "label": "Keyrock: 16,000+ unlocks across 40 tokens",
        "url": "https://keyrock.com/from-locked-to-liquidity-what-16000-token-unlocks-teach-us/",
        "finding": "About 90% of unlocks were followed by price pressure, starting about 30 days before. "
                   "Team unlocks were worst (about -25%), investor and community unlocks moderate, "
                   "ecosystem-development unlocks averaged +1.18%. Bigger unlocks hit harder; linear "
                   "releases disrupt less than cliffs. Keyrock is a market maker and has not published its data.",
    },
    "thetie": {
        "label": "The Tie: 12,350 unlocks in 2026",
        "url": "https://www.thetie.io/insights/venture-cliffs-token-unlocks-2026",
        "finding": "The median unlock was 0.2% of a day's trading volume and 95.6% were under one day's volume. "
                   "Their screen for unlocks that can move a market: more than a quarter of a day's volume.",
    },
    "tokenomist": {
        "label": "Tokenomist: 236 unlocks",
        "url": "https://tokenomist.ai/research/do-token-unlocks-crash-prices",
        "finding": "Drops are real but conditional: concentrated in early-stage tokens with a thin float, "
                   "and mostly priced in before the unlock date.",
    },
    "kim": {
        "label": "Kim (SSRN): 52 Binance unlocks, 2023-2025",
        "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6632838",
        "finding": "46 of 52 major unlocks (88.5%) fell within 72 hours, mean -16.97%, in every Bitcoin market "
                   "regime. Small, preliminary sample.",
    },
    "reasoning": {
        "label": "Reasoning, not a study",
        "url": None,
        "finding": "Holders sitting on large gains have more reason to take profit; holders below their entry "
                   "price have less. No study above measures this directly, so it carries a small weight.",
    },
}

AGGREGATOR_HOSTS = ("tokenomist", "defillama", "cryptorank", "tokenomics.com", "messari",
                    "coingecko", "coinmarketcap", "tokenunlocks", "dropstab")


def host(url):
    try:
        h = urlparse(url).hostname or ""
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def sources_of(u):
    """The row's sources, upgrading the old single `source` field if that is all it has."""
    src = u.get("sources")
    if src:
        return src
    url = u.get("source")
    if not url:
        return []
    kind = "aggregator" if any(a in url for a in AGGREGATOR_HOSTS) else "news"
    return [{"url": url, "label": host(url), "kind": kind, "confirms": ["date", "amount"]}]


def parse_ts(v):
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


# ---------------------------------------------------------------- confidence
def confidence(u, now):
    src = sources_of(u)
    parts = []

    def tier(fact, primary_pts, two_pts, one_pts, label):
        hits = [s for s in src if fact in (s.get("confirms") or [])]
        if any(s.get("kind") == "primary" for s in hits):
            pts, why = primary_pts, "confirmed by the project itself"
        else:
            n = len({host(s.get("url", "")) for s in hits})
            if n >= 2:
                pts, why = two_pts, f"confirmed by {n} independent sources"
            elif n == 1:
                pts, why = one_pts, "one source only"
            else:
                pts, why = 0, "not confirmed"
        parts.append({"label": label, "points": pts, "max": primary_pts, "detail": why})
        return pts

    total = 0
    total += tier("date", 35, 25, 12, "Date")
    amount = tier("amount", 30, 22, 10, "Amount")
    total += amount
    if u.get("sourceDisagreements") and amount:
        cut = min(10, amount)
        total -= cut
        parts.append({"label": "Sources disagree on size", "points": -cut, "max": 0, "detail": u["sourceDisagreements"]})
    total += tier("recipients", 15, 10, 6, "Who receives it")
    if u.get("timeUTC") and any("time" in (s.get("confirms") or []) for s in src):
        total += 5
        parts.append({"label": "Exact time", "points": 5, "max": 5, "detail": "unlock time published"})
    else:
        parts.append({"label": "Exact time", "points": 0, "max": 5, "detail": "day known, time not published"})

    checked = parse_ts((u.get("verify") or {}).get("checkedAt"))
    age = (now - checked).days if checked else None
    fresh = 15 if age is not None and age <= 3 else 10 if age is not None and age <= 7 else 5 if age is not None and age <= 14 else 0
    total += fresh
    parts.append({"label": "Recently re-checked", "points": fresh, "max": 15,
                  "detail": f"independently re-checked {age} days ago" if age is not None else "not independently re-checked"})

    status = (u.get("verify") or {}).get("status")
    if status == "contradicted":
        total = min(total, 30)
        parts.append({"label": "Re-check found a conflict", "points": 0, "max": 0, "detail": (u.get("verify") or {}).get("notes") or ""})
    elif status == "partial":
        total = min(total, 70)

    total = max(0, min(100, total))
    label = "High" if total >= 80 else "Good" if total >= 60 else "Low" if total >= 40 else "Unverified"
    return total, label, parts


# ---------------------------------------------------------------- sell pressure
def sell_pressure(u, now):
    f = []
    m = u.get("market") or {}

    # 1. Size against daily trading volume (The Tie)
    usd, adv = u.get("usdM"), m.get("advUsdM")
    if isinstance(usd, (int, float)) and isinstance(adv, (int, float)) and adv > 0:
        d = usd / adv
        pts = 0 if d < 0.25 else 1 if d < 1 else 2 if d < 3 else 3
        f.append({"key": "volume", "label": "Size vs. daily trading", "points": pts, "max": 3,
                  "detail": f"{d:.2f} days of trading volume" + (" (based on 24h volume)" if m.get("advBasis") == "24h" else ""),
                  "evidence": "thetie"})
    else:
        f.append({"key": "volume", "label": "Size vs. daily trading", "points": None, "max": 3,
                  "detail": "volume or USD size not confirmed", "evidence": "thetie"})

    # 2. Size against circulating supply (Keyrock size tiers)
    pct = u.get("pctCirculating")
    if pct is None and u.get("pctBasis") in ("of circulating", "of float"):
        pct = u.get("pct")
    if isinstance(pct, (int, float)):
        pts = 0 if pct < 1 else 1 if pct < 5 else 2 if pct < 10 else 3
        f.append({"key": "size", "label": "Size vs. circulating supply", "points": pts, "max": 3,
                  "detail": f"{pct:g}% of circulating supply", "evidence": "keyrock"})
    else:
        f.append({"key": "size", "label": "Size vs. circulating supply", "points": None, "max": 3,
                  "detail": "share of circulating supply not confirmed", "evidence": "keyrock"})

    # 3. Who receives it (Keyrock by recipient type)
    mix = u.get("recipientsMix")
    if isinstance(mix, dict) and sum(v or 0 for v in mix.values()) > 0:
        tot = sum(v or 0 for v in mix.values())
        s = {k: (mix.get(k) or 0) / tot for k in ("team", "investors", "community", "ecosystem", "other")}
        pts = round(2 * s["team"] + 1 * s["investors"] + 1 * s["community"] - 0.5 * s["ecosystem"] + 0.5 * s["other"], 2)
        top = ", ".join(f"{k} {round(v * 100)}%" for k, v in sorted(s.items(), key=lambda kv: -kv[1]) if v >= 0.05)
        f.append({"key": "recipients", "label": "Who receives it", "points": pts, "max": 2,
                  "detail": top, "evidence": "keyrock"})
    else:
        f.append({"key": "recipients", "label": "Who receives it", "points": None, "max": 2,
                  "detail": "split between team, investors and others not confirmed", "evidence": "keyrock"})
        s = None

    # 4. Early-stage, thin float (Tokenomist)
    circ = m.get("circPctOfMax")
    listed = m.get("listed")
    young = False
    if listed:
        try:
            y, mo = map(int, str(listed)[:7].split("-"))
            months = (now.year - y) * 12 + now.month - mo
            young = months < 12
        except Exception:
            pass
    if isinstance(circ, (int, float)) or listed:
        thin = isinstance(circ, (int, float)) and circ < 30
        pts = 1 if (thin or young) else 0
        why = []
        if isinstance(circ, (int, float)):
            why.append(f"{circ:g}% of max supply circulating")
        if listed:
            why.append(f"listed {listed}")
        f.append({"key": "float", "label": "Early-stage, thin float", "points": pts, "max": 1,
                  "detail": ", ".join(why), "evidence": "tokenomist"})

    # 5. Released gradually (Keyrock: linear disrupts less than a cliff)
    if u.get("type") == "linear":
        f.append({"key": "linear", "label": "Released gradually", "points": -0.5, "max": 0,
                  "detail": "linear release, not a one-day cliff", "evidence": "keyrock"})

    # 6. Investors in profit (reasoning)
    ie, price = u.get("investorEntry") or {}, m.get("priceUsd")
    if s and s["investors"] >= 0.2 and isinstance(ie.get("priceUsd"), (int, float)) and ie["priceUsd"] > 0 and isinstance(price, (int, float)):
        x = price / ie["priceUsd"]
        pts = 1 if x >= 5 else 0.5 if x >= 2 else -0.5 if x < 1 else 0
        f.append({"key": "profit", "label": "Investors' paper profit", "points": pts, "max": 1,
                  "detail": f"price is {x:.1f}x the {ie.get('round') or 'investor'} price", "evidence": "reasoning"})

    known = [x for x in f if x["points"] is not None]
    core = [x for x in f if x["key"] in ("volume", "size", "recipients") and x["points"] is not None]
    pts = round(sum(x["points"] for x in known), 2)
    if len(core) < 2:
        grade = "Not enough data"
    elif pts <= 0.5:
        grade = "Low"
    elif pts <= 2.5:
        grade = "Moderate"
    elif pts <= 4.5:
        grade = "High"
    else:
        grade = "Very high"
    return {"grade": grade, "points": pts, "maxPoints": 10, "factors": f}


def score_all(d, now=None):
    now = now or datetime.now(timezone.utc)
    for u in d.get("upcoming") or []:
        c, label, parts = confidence(u, now)
        u["confidenceScore"], u["confidenceLabel"], u["confidenceParts"] = c, label, parts
        u["impact"] = sell_pressure(u, now)
    d["scoring"] = {"version": VERSION, "evidence": EVIDENCE}
    return d


def main():
    d = json.loads(DATA.read_text())
    if "--check" in sys.argv:
        stamp = parse_ts(d.get("scoredAt")) or datetime.now(timezone.utc)
        before = json.dumps(d.get("upcoming"), sort_keys=True)
        after = json.dumps(score_all(json.loads(json.dumps(d)), stamp)["upcoming"], sort_keys=True)
        if before != after:
            print("FAIL  unlock scores are out of date: run python3 scripts/score.py")
            sys.exit(1)
        print("unlock scores match the data")
        return
    now = datetime.now(timezone.utc)
    d["scoredAt"] = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    score_all(d, now)
    DATA.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n")
    print(f"scored {len(d['upcoming'])} unlocks")


if __name__ == "__main__":
    main()
