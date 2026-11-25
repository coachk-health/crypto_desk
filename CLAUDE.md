# Crypto desk — working notes for Claude

## Keep the running record
- After every working session that changes the desk (code, data, rules, research, decisions), add ONE entry
  at the TOP of `entries` in `data/journal.json`: date, title, did, found, decided, files. Never edit or
  delete earlier entries. The dashboard's History tab shows it ("What we've done").
- `data/archive.json` (scripts/archive.py) keeps every unlock the desk has shown; never prune it.
- `data/picks_log.json` holds the live calls (v3 until 24 Nov 2026, v4/v5 from 25 Nov); a logged call is never rewritten.
- The rules under live test are frozen in `data/strategy_v5.json` (25 Nov 2026; v3 setups, other exchanges,
  never MEXC, only unlocks we can short). Any change becomes v6 with a new date, and needs Coach K's yes.
- Only unlocks we can short are worth research time: `data/shortable.json` (scripts/shortable.py, run on GitHub)
  marks each unlock yes / no / unknown. Never use MEXC (FinCEN order, 6 Nov 2026).
- Before trading a token off Binance, `scripts/venues.py` must confirm by price that it is the same token
  (tickers collide with stock perps, e.g. ADI). A "can't short it" skip needs every exchange checked.
