# Research brief: large and first insider unlocks, Nov 2023 to Nov 2025

Purpose: a fixed trading rule is being tested on unlocks it has never seen. Only two kinds of
unlock matter, so research only those. Never fill a value from memory; if a value cannot be
confirmed, set it to null and explain in `gap`.

Window: unlock dates from 2023-11-15 to 2025-11-16 inclusive (UTC).

For each token, find:

A. **The first insider unlock**: the first day team / core-contributor or investor tokens were
   ever released (the end of their cliff). If it was before 2023-11-15 or after 2025-11-16,
   say so and give the date if known, but do not list it as an event.
B. **Every single-day unlock of 25% or more of the circulating supply at the time**, inside the
   window (a big cliff, a quarterly mega-tranche, a TGE-anniversary unlock). Monthly tranches of a
   few percent do NOT matter; skip them.

For each event (A inside the window, and every B):
- date (YYYY-MM-DD, UTC)
- amountTokens (number) and how you know it
- circulatingBefore: the circulating supply just before the unlock (tokens), with its source
  (a news report of the unlock often states "X% of circulating supply"; CoinMarketCap / CoinGecko
  historical snapshots; tokenomics trackers). pctCirculating = amountTokens / circulatingBefore x 100.
- shape: "lump" if a one-off block was released that day, "stream" if only a linear/daily vesting
  STARTED that day, "unknown" if no source says
- recipients: plain words, and recipientsMix as fractions (team, investors, community, ecosystem, other) or null
- firstInsiderUnlock: true for A, false for a B that was not the first insider unlock
- priceUsd: the token's USD price on or near that date as reported by a source (used only to check
  that the exchange ticker is the same token), with the source
- sources: at least 2 where possible, each with kind primary|aggregator|news and what it confirms

Good sources: the project's own tokenomics or vesting docs and announcements; news coverage of the
specific unlock (CoinDesk, The Block, Cointelegraph, Decrypt, Bloomberg, PANews, Wu Blockchain,
Binance/Bitget/KuCoin/MEXC news, Tokenomist and Token Unlocks weekly round-ups); tokenomist.ai,
tokenomics.com, cryptorank.io, dropstab.com, defillama.com/unlocks. Big 2024 unlocks were widely
reported, so news is often the best source for the date, the size and the % of circulating supply.

Output: a JSON array, one object per token, in input order:
[{"token": "ARB", "name": "Arbitrum", "binanceFuturesSymbol": "ARBUSDT",
  "firstInsiderUnlock": {"date": "2024-03-16", "inWindow": true},
  "events": [{"date": "2024-03-16", "amountTokens": 1110000000, "amountHow": "...",
              "circulatingBefore": 1275000000, "pctCirculating": 87.1, "shape": "lump",
              "recipients": "team and advisors 673.5M, investors 438.5M",
              "recipientsMix": {"team": 0.61, "investors": 0.39, "community": 0, "ecosystem": 0, "other": 0},
              "firstInsiderUnlock": true, "priceUsd": 1.85, "priceSource": "https://...",
              "sources": [{"label": "...", "url": "https://...", "kind": "news", "confirms": ["date", "amount", "pct"]}],
              "gap": null}],
  "gap": "token-level gaps or null"}]

A token with no qualifying event in the window is a valid answer: "events": [] and the reason in gap.
When finished, reply with one line per token: events found and the main gap.
