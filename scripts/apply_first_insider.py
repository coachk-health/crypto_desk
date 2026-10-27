#!/usr/bin/env python3
"""Adds researched first-insider-unlock answers to data/unlocks.json.

  python3 scripts/apply_first_insider.py out0.json [out1.json ...]

Each item: {"token", "date", "firstInsiderUnlock": true|false|null, "groups", "sources", "gap"}.
Only rows with the same token and date are touched; null answers leave the row unchanged.
After running, run scripts/score.py and scripts/verify.py.
"""
import json, sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "unlocks.json"


def main():
    data = json.loads(DATA.read_text())
    rows = {(r["token"], r["date"]): r for r in data["upcoming"]}
    set_, skipped = 0, []
    for path in sys.argv[1:]:
        for a in json.loads(Path(path).read_text()):
            r = rows.get((a["token"], a["date"]))
            if r is None:
                skipped.append(f"{a['token']} {a['date']} (no such row)")
                continue
            if a.get("firstInsiderUnlock") is None or not a.get("sources"):
                skipped.append(f"{a['token']} {a['date']} (unconfirmed: {a.get('gap')})")
                continue
            r["firstInsiderUnlock"] = bool(a["firstInsiderUnlock"])
            r["firstInsiderNote"] = a.get("groups")
            r["firstInsiderSources"] = a.get("sources")[:3]
            set_ += 1
    DATA.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(f"set {set_}; left unchanged {len(skipped)}")
    for s in skipped:
        print("  ", s)


if __name__ == "__main__":
    main()
