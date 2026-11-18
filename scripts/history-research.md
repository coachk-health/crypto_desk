# Research brief: big and first insider unlocks, 2021 to 2025

Purpose: a frozen short-selling rule (data/strategy_v3.json) is being tested on unlocks it has never
seen, back to 2021. Only two kinds of unlock matter. Never fill a value from memory; if a value cannot
be confirmed from a page you fetched, set it to null and explain in `gap`.

Window: each input token has its own "window": [start, end] (UTC, inclusive). Only list events inside it.

For each token, find:

A. **The first insider unlock**: the first day that ANY insider group (team / core contributors,
   investors / VCs, advisors) received transferable tokens. Strict: if investors or advisors got even
   1% at the token launch (TGE), the launch day is the first insider unlock. Give its date even if it is
   outside the window (with inWindow false). If it is the launch day itself, set "atLaunch": true.
B. **Every single-day unlock of 25% or more of the circulating supply at the time**, inside the window
   (big cliffs, quarterly mega-tranches, anniversary unlocks). Monthly tranches of a few percent do NOT
   matter; skip them.

For each event (A inside the window and not at launch, and every B):
- date (YYYY-MM-DD, UTC). Prefer the project's own announcement, docs or vesting contract. If sources
  disagree by more than 2 days and there is no project statement, say so in gap and set dateConflict true.
- amountTokens, circulatingBefore (tokens just before the unlock, with source), pctCirculating
- shape: "lump" (most released that day) / "stream" (only a linear vesting STARTED that day) / "unknown"
- recipients in words, and recipientsMix fractions (team, investors, community, ecosystem, other) or null
- firstInsiderUnlock: true for A, false for B
- flags (list, may be empty): "migration" (old token swapped for new), "relocked" (holders re-locked or
  the unlock was postponed/cancelled), "launch" (no market before), "communityFund" (goes to a
  foundation/ecosystem/treasury, not to people who sell), "delayed" (date moved from the original plan)
- priceUsd on or near that date from a source (used only to check the ticker), with priceSource
- sources: at least 2 where possible, each {label, url, kind: primary|aggregator|news, confirms: [...]}

Do NOT research what the price did after the unlock.

Older unlocks (2021-2022) were covered less by news. Good sources: project blogs, docs and Medium
posts; governance forums; CoinDesk, The Block, Cointelegraph, Decrypt, Messari, Delphi, Bankless
coverage; Token Unlocks / Tokenomist round-ups; CryptoRank, DropsTab, tokenomics.com, DefiLlama
unlocks; Binance Research token reports (they list vesting schedules); archived web pages (web.archive.org).

Output: a JSON array, one object per token, in input order:
[{"token": "ARB", "name": "Arbitrum", "binanceFuturesSymbol": "ARBUSDT",
  "firstInsiderUnlock": {"date": "2024-03-16", "inWindow": true, "atLaunch": false},
  "events": [{"date": "...", "amountTokens": 0, "circulatingBefore": 0, "pctCirculating": 0, "shape": "lump",
              "recipients": "...", "recipientsMix": {...}, "firstInsiderUnlock": true, "flags": [],
              "dateConflict": false, "priceUsd": 0, "priceSource": "https://...",
              "sources": [...], "gap": null}],
  "gap": "token-level gaps or null"}]

A token with no qualifying event is a valid answer: "events": [] and the reason in gap.
Write the file after each token so nothing is lost. When finished, reply with one line per token.
