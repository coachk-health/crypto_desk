# Crypto desk — working notes for Claude

## Keep the running record
- After every working session that changes the desk (code, data, rules, research, decisions), add ONE entry
  at the TOP of `entries` in `data/journal.json`: date, title, did, found, decided, files. Never edit or
  delete earlier entries. The dashboard's History tab shows it ("What we've done").
- `data/archive.json` (scripts/archive.py) keeps every unlock the desk has shown; never prune it.
- `data/picks_log.json` holds the live v3 calls; a logged call is never rewritten.
- The rules under live test are frozen in `data/strategy_v3.json`. Any change becomes v4 with a new date,
  and needs Coach K's yes.
