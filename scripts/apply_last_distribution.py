#!/usr/bin/env python3
"""Adds researched last-distribution facts to upcoming rows in data/unlocks.json.

  python3 scripts/apply_last_distribution.py research.json

Each item: {"token", "lastDistribution": {"date","amount","recipients","kind"} | null,
            "noUnlockSinceTGE": "YYYY-MM-DD" (optional), "sources": [...], "gap"}.
Applies to every upcoming row of that token whose date is after the last distribution.
"""
import json, sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "unlocks.json"


def main():
    data = json.loads(DATA.read_text())
    n = 0
    for a in json.loads(Path(sys.argv[1]).read_text()):
        for r in data["upcoming"]:
            if r["token"] != a["token"]:
                continue
            ld = a.get("lastDistribution")
            if ld and ld.get("date") and ld["date"] < r["date"]:
                r["lastDistribution"] = {k: ld.get(k) for k in ("date", "amount", "recipients", "kind")}
                r.pop("lastDistributionNote", None)
            elif a.get("noUnlockSinceTGE"):
                r.pop("lastDistribution", None)
                r["lastDistributionNote"] = f"no unlock since TGE ({a['noUnlockSinceTGE']})"
            else:
                continue
            r["lastDistributionSources"] = (a.get("sources") or [])[:3]
            if a.get("gap"):
                r["lastDistributionGap"] = a["gap"]
            n += 1
    DATA.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(f"updated {n} rows")


if __name__ == "__main__":
    main()
