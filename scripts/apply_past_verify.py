#!/usr/bin/env python3
"""Applies independent re-check results to a past-unlocks file.

  python3 scripts/apply_past_verify.py <past_unlocks.json> <check1.json> [check2.json ...]

Each check row: {"token","status","notes","eventFixes":[{"date","action":"remove|fix","fields":{},"why"}]}
Tokens marked "contradicted" are dropped. Every kept token gets "verify": {status, notes, checkedAt}.
"""
import json, sys
from datetime import datetime, timezone

path, checks = sys.argv[1], sys.argv[2:]
d = json.load(open(path))
now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
res = {}
for c in checks:
    for r in json.load(open(c)):
        res[r["token"]] = r
kept, dropped, removed, fixed = [], [], 0, 0
for t in d["tokens"]:
    r = res.get(t["token"])
    if r and r.get("status") == "contradicted":
        dropped.append(t["token"])
        continue
    if r:
        for fx in r.get("eventFixes") or []:
            for e in list(t["events"]):
                if e["date"] != fx.get("date"):
                    continue
                if fx.get("action") == "remove":
                    t["events"].remove(e); removed += 1
                elif fx.get("action") == "fix":
                    e.update(fx.get("fields") or {}); e["fixNote"] = fx.get("why"); fixed += 1
        t["verify"] = {"status": r.get("status"), "notes": r.get("notes"), "checkedAt": now}
    kept.append(t)
d["tokens"] = kept
d["dropped"] = [{"token": x, "why": (res[x].get("notes") or "")} for x in dropped]
json.dump(d, open(path, "w"), indent=1, ensure_ascii=False)
print(f"kept {len(kept)} tokens, dropped {len(dropped)} {dropped}, removed {removed} events, fixed {fixed}")
