#!/usr/bin/env python3
"""Checks the desk's data before it goes live, and every hour after.

Fails (exit 1) when the data is stale, malformed, or cites a source that is gone.
Run locally:  python3 scripts/verify.py            (full check, including links)
              python3 scripts/verify.py --no-links  (structure and freshness only)
"""
import json, sys, re, urllib.request, urllib.error, ssl
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime.now(timezone.utc)
NEWS_MAX_AGE = timedelta(hours=26)       # the 11:00 run plus slack
UNLOCK_MAX_AGE = timedelta(days=8)       # weekly refresh plus slack
MOODS = {"bullish", "bearish", "volatile", "neutral"}
CONFIDENCE = {"confirmed", "reported", "estimated", "disputed"}

errors, warnings = [], []
def err(m): errors.append(m)
def warn(m): warnings.append(m)

def ts(v, where):
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        err(f"{where}: not a valid timestamp ({v!r})")
        return None

def url_ok(u, where):
    if not isinstance(u, str) or not re.match(r"^https://\S+$", u):
        err(f"{where}: missing or non-https source URL ({u!r})")
        return False
    return True

def load(name):
    try:
        return json.loads((ROOT / "data" / name).read_text())
    except Exception as e:
        err(f"data/{name}: cannot be read as JSON ({e})")
        return None

news, unlocks, site = load("news.json"), load("unlocks.json"), load("site.json")
urls = []

if news:
    up = ts(news.get("updated"), "news.updated")
    if up and NOW - up > NEWS_MAX_AGE:
        err(f"news is {(NOW - up).total_seconds() / 3600:.0f}h old (limit {NEWS_MAX_AGE.total_seconds() / 3600:.0f}h): the 11:00 update did not land")
    if up and up - NOW > timedelta(minutes=10):
        err("news.updated is in the future")
    if not news.get("headline"):
        err("news.headline is empty")
    v = news.get("verification")
    if not v:
        err("news.verification is missing: this edition was not source-checked")
    else:
        vt = ts(v.get("checkedAt"), "verification.checkedAt")
        if vt and up and vt < up - timedelta(minutes=5):
            err("verification is older than the data it claims to check")
        if not isinstance(v.get("claimsChecked"), int) or v["claimsChecked"] < 1:
            err("verification.claimsChecked must be a positive count")
    stories = news.get("stories") or []
    if not 1 <= len(stories) <= 5:
        err(f"news.stories should hold 1-5 stories, found {len(stories)}")
    for i, s in enumerate(stories):
        w = f"stories[{i}]"
        for k in ("title", "summary"):
            if not s.get(k):
                err(f"{w}.{k} is empty")
        if s.get("mood") not in MOODS:
            err(f"{w}.mood must be one of {sorted(MOODS)}")
        src = s.get("sources") or []
        if not src:
            err(f"{w} has no sources")
        for j, x in enumerate(src):
            if url_ok(x.get("url"), f"{w}.sources[{j}]"):
                urls.append((x["url"], f"{w}.sources[{j}]"))
    for i, b in enumerate(news.get("briefs") or []):
        if not b.get("title"):
            err(f"briefs[{i}].title is empty")
        if url_ok(b.get("url"), f"briefs[{i}]"):
            urls.append((b["url"], f"briefs[{i}]"))
    for i, b in enumerate(news.get("breaking") or []):
        ts(b.get("at"), f"breaking[{i}].at")
        if url_ok(b.get("url"), f"breaking[{i}]"):
            urls.append((b["url"], f"breaking[{i}]"))
    for i, c in enumerate(news.get("calendar") or []):
        if not c.get("event"):
            err(f"calendar[{i}].event is empty")

if unlocks:
    ck = ts(unlocks.get("checkedAt") or unlocks.get("updated"), "unlocks.checkedAt")
    if ck and NOW - ck > UNLOCK_MAX_AGE:
        err(f"unlock data last checked {(NOW - ck).days} days ago (limit {UNLOCK_MAX_AGE.days})")
    ahead = 0
    for i, u in enumerate(unlocks.get("upcoming") or []):
        w = f"upcoming[{i}] {u.get('token')}"
        try:
            d = datetime.strptime(u["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if d >= NOW - timedelta(days=1):
                ahead += 1
        except Exception:
            err(f"{w}: bad date {u.get('date')!r}")
        if u.get("confidence") not in CONFIDENCE:
            err(f"{w}: confidence must be one of {sorted(CONFIDENCE)}")
        if u.get("usdM") is not None and not isinstance(u["usdM"], (int, float)):
            err(f"{w}: usdM must be a number or null")
        if url_ok(u.get("source"), w):
            urls.append((u["source"], w))
    if ahead < 3:
        err(f"only {ahead} unlocks are still ahead: the unlock list needs a refresh")

if site and not site.get("disclaimer"):
    err("site.disclaimer is empty")

if "--no-links" not in sys.argv:
    ctx = ssl.create_default_context()
    seen = {}
    for u, where in urls:
        if u in seen:
            continue
        code = None
        for method in ("HEAD", "GET"):
            try:
                req = urllib.request.Request(u, method=method, headers={"User-Agent": "Mozilla/5.0 (desk link check)"})
                with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
                    code = r.status
                break
            except urllib.error.HTTPError as e:
                code = e.code
                if method == "HEAD" and code in (403, 405, 429, 400):
                    continue
                break
            except Exception as e:
                code = f"unreachable ({type(e).__name__})"
                break
        seen[u] = code
        if code in (404, 410):
            err(f"{where}: source is gone ({code}) {u}")
        elif not (isinstance(code, int) and code < 400):
            warn(f"{where}: could not confirm the link ({code}) {u}")

for w in warnings:
    print("WARN ", w)
for e in errors:
    print("FAIL ", e)
print(f"\n{len(errors)} problems, {len(warnings)} warnings, {len(urls)} source links")
sys.exit(1 if errors else 0)
