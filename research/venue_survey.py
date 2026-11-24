"""Where each upcoming candidate unlock (25%+ or first insider) has a USDT perp, checked from GitHub.
Writes data/venue_survey.json. Run by .github/workflows/venue-probe.yml."""
import json, sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import candles, venues  # noqa: E402

up = json.loads((ROOT / "data" / "unlocks.json").read_text()).get("upcoming", [])
today = datetime.now(timezone.utc).date()
out = []
for r in up:
    pc = r.get("pctCirculating")
    if not ((pc or 0) >= 25 or r.get("firstInsiderUnlock") is True):
        continue
    d0 = date.fromisoformat(r["date"])
    if d0 < today - timedelta(days=14):
        continue
    start, end = today - timedelta(days=45), today
    src, sym, days = candles.token_days(r["token"], start, end)
    rows, best = venues.survey(r["token"], r, start, end, days if src else None)
    out.append({"token": r["token"], "unlock": r["date"], "pct": pc, "firstInsider": r.get("firstInsiderUnlock"),
                "binance": src, "venues": rows, "best": best and [best[0], best[1], len(best[2])]})
    out[-1]["cgPrice"] = venues.cg_price(r.get("coingeckoId"))
    print(r["token"], src, best and best[:2], [(x["venue"], x.get("match"), x.get("note")) for x in rows])
Path(ROOT / "data" / "venue_survey.json").write_text(json.dumps({"ran": venues.checked(), "errors": venues.errors(), "tokens": out}, indent=1) + "\n")
