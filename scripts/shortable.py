#!/usr/bin/env python3
"""Can we short it? Checks every unlock on the list (data/unlocks.json "upcoming", plus the last 14 days)
for a USDT perpetual on an allowed exchange whose price confirms it is the same token.

Rules v5 (Coach K, 25 Nov 2026): only unlocks we can short are worth focusing on. Allowed exchanges:
Binance, Bybit (via CoinGecko), OKX, Bitget, Gate, Hyperliquid, KuCoin. MEXC is never used.

  shortable "yes"     = at least one allowed exchange lists the real token
  shortable "no"      = every allowed exchange answered and none does (a fact, with the time it was checked)
  shortable "unknown" = an exchange couldn't be reached and none confirmed it yet; rechecked next run

Writes data/shortable.json. Run on GitHub (Live trade log + Morning brief workflows): from the Claude
container only Binance's files and OKX are reachable, so a local run marks most tokens "unknown".
"""
import json, sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import venues  # noqa: E402

OUT = ROOT / "data" / "shortable.json"


def main():
    today = datetime.now(timezone.utc).date()
    up = json.loads((ROOT / "data" / "unlocks.json").read_text()).get("upcoming", [])
    old = json.loads(OUT.read_text()).get("unlocks", {}) if OUT.exists() else {}
    res, cache = {}, {}
    for r in up:
        if date.fromisoformat(r["date"]) < today - timedelta(days=14):
            continue
        key = f"{r['token']}|{r['date']}"
        if r["token"] not in cache:
            try:
                cache[r["token"]] = venues.shortable(r["token"], r, today)
            except Exception as e:  # one token failing must not stop the rest
                cache[r["token"]] = {"shortable": "unknown", "where": [], "notes": [f"check failed: {str(e)[:80]}"], "unreachable": []}
        x = dict(cache[r["token"]])
        x["checkedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        prev = old.get(key)
        if x["shortable"] == "unknown" and prev and prev.get("shortable") in ("yes", "no"):
            x["lastKnown"] = {"shortable": prev["shortable"], "where": prev.get("where"), "checkedAt": prev.get("checkedAt")}
        res[key] = x
    n = {s: sum(1 for v in res.values() if v["shortable"] == s) for s in ("yes", "no", "unknown")}
    OUT.write_text(json.dumps({"generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                               "rule": "v5: only unlocks with a USDT perp we can short (Binance, Bybit, OKX, Bitget, Gate, Hyperliquid, KuCoin; never MEXC) are focused on",
                               "avoid": venues.AVOID, "checked": venues.checked(), "counts": n, "unlocks": res},
                              indent=1, ensure_ascii=False) + "\n")
    print(f"shortable: {n}")


if __name__ == "__main__":
    main()
