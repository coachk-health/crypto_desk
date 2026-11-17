#!/usr/bin/env python3
"""Adds newly researched tokens (the format in scripts/past-unlock-research.md) to
data/past_unlocks.json and records every token that was checked in data/past_queue.json,
so the same token is not researched twice.

  python3 scripts/merge_past_research.py out0.json [out1.json ...] [--from 2025-11-17] [--to 2026-11-02]

Rules:
  - a token already in the track record is left alone (its events come from the daily harvest);
  - only dated, discrete events inside the window are kept (no continuous releases);
  - a token with no such event is recorded in the queue as "no_events" with the researcher's reason;
  - new tokens are marked verify.status = "unchecked" until scripts/apply_past_verify.py has run.
Run the independent re-check (scripts/past-unlock-verify.md) before publishing.
"""
import json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAST = ROOT / "data" / "past_unlocks.json"
QUEUE = ROOT / "data" / "past_queue.json"


def main():
    args = sys.argv[1:]
    lo, hi = "2025-11-17", "2026-11-02"
    for flag in ("--from", "--to"):
        if flag in args:
            i = args.index(flag)
            if flag == "--from":
                lo = args[i + 1]
            else:
                hi = args[i + 1]
            args = args[:i] + args[i + 2:]
    past = json.loads(PAST.read_text())
    queue = json.loads(QUEUE.read_text()) if QUEUE.exists() else {"tokens": {}}
    have = {t["token"] for t in past["tokens"]}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    added = empty = 0
    for path in args:
        for t in json.loads(Path(path).read_text()):
            tok = t.get("token")
            if not tok or tok in have:
                continue
            ev = [e for e in (t.get("events") or [])
                  if e.get("date") and lo <= e["date"] <= hi and e.get("type") != "continuous" and e.get("amountTokens")]
            seen, uniq = set(), []
            for e in sorted(ev, key=lambda e: e["date"]):
                if e["date"] not in seen:
                    seen.add(e["date"]); uniq.append(e)
            if not uniq:
                queue["tokens"][tok] = {"status": "no_events", "checkedAt": now, "why": (t.get("gaps") or "no discrete unlock in the window")[:400]}
                empty += 1
                continue
            v = t.pop("_verify", None)
            verify = dict(v, checkedAt=now) if v else {"status": "unchecked", "checkedAt": now,
                                                        "notes": "Routine tranche dates come from tracker schedules and were not independently re-checked."}
            t = dict(t, events=uniq, verify=verify, addedAt=now)
            past["tokens"].append(t)
            have.add(tok)
            queue["tokens"][tok] = {"status": "added", "checkedAt": now, "events": len(uniq)}
            added += 1
    past["tokens"].sort(key=lambda t: t["token"])
    w = past.setdefault("window", {})
    w["from"] = min(w.get("from", lo), lo)
    PAST.write_text(json.dumps(past, indent=1, ensure_ascii=False) + "\n")
    QUEUE.write_text(json.dumps(queue, indent=1, ensure_ascii=False) + "\n")
    print(f"added {added} tokens, {empty} had no discrete unlock; track record now {len(past['tokens'])} tokens, "
          f"{sum(len(t.get('events', [])) for t in past['tokens'])} events")


if __name__ == "__main__":
    main()
