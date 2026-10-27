#!/usr/bin/env python3
"""Merges researched unlock rows (the format in scripts/unlock-research.md) into
data/unlocks.json, then applies an independent re-check file if given.

  python3 scripts/merge_unlock_research.py research1.json [research2.json ...] [--verify verify.json]

Research rows replace the matching row (same token, date within 10 days).
Rows marked stillUpcoming=false are removed. New tokens are added.
Verify file: [{"token","date","status":"confirmed|partial|contradicted","notes","corrections":{field:value}}]
After merging, run scripts/score.py.
"""
import json, sys
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "unlocks.json"
FIELDS = ["date", "timeUTC", "token", "name", "coingeckoId", "amountTokens", "amountText", "usdM", "type", "pctCirculating",
          "sources", "sourceDisagreements", "recipients", "recipientsMix", "market", "investorEntry",
          "sellerNotes", "sellerSources", "gaps", "firstInsiderUnlock"]


def d(s):
    return datetime.strptime(s, "%Y-%m-%d")


def find(rows, token, date):
    best = None
    for i, r in enumerate(rows):
        if r.get("token") != token:
            continue
        gap = abs((d(r["date"]) - d(date)).days)
        if gap <= 10 and (best is None or gap < best[1]):
            best = (i, gap)
    return best[0] if best else None


def main():
    args = sys.argv[1:]
    verify = None
    if "--verify" in args:
        i = args.index("--verify")
        verify = args[i + 1]
        args = args[:i] + args[i + 2:]
    data = json.loads(DATA.read_text())
    rows = data["upcoming"]
    added = replaced = removed = 0
    for path in args:
        for r in json.loads(Path(path).read_text()):
            i = find(rows, r["token"], r["date"])
            if r.get("stillUpcoming") is False:
                if i is not None:
                    rows.pop(i); removed += 1
                continue
            new = {k: r.get(k) for k in FIELDS}
            new["amount"] = r.get("amountText") or "unconfirmed"
            new["source"] = (r.get("sources") or [{}])[0].get("url")
            new["pct"] = r.get("pctCirculating")
            new["pctBasis"] = "of circulating" if r.get("pctCirculating") is not None else None
            new["note"] = r.get("sourceDisagreements") or ""
            prim = any(s.get("kind") == "primary" for s in r.get("sources") or [])
            n = len(r.get("sources") or [])
            new["confidence"] = "confirmed" if prim or n >= 2 else "reported" if n == 1 else "estimated"
            if i is None:
                rows.append(new); added += 1
            else:
                rows[i] = new; replaced += 1
    if verify:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        for v in json.loads(Path(verify).read_text()):
            i = find(rows, v["token"], v["date"])
            if i is None:
                continue
            for k, val in (v.get("corrections") or {}).items():
                rows[i][k] = val
            rows[i]["verify"] = {"checkedAt": now, "status": v.get("status"), "notes": v.get("notes")}
    rows.sort(key=lambda r: (r["date"], r.get("timeUTC") or "99"))
    data["checkedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    data["updated"] = data["checkedAt"][:10]
    DATA.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(f"replaced {replaced}, added {added}, removed {removed}; {len(rows)} unlocks")


if __name__ == "__main__":
    main()
