# Past unlock research brief

Goal: a list of token unlock events that ALREADY HAPPENED, so we can measure what each
token's price did before and after. Each event will be graded and compared with the
price, so the date, size and recipients must be right. Never fill a value from memory.
If a value cannot be confirmed, set it to null and explain in `gaps`.

Window: unlock dates from 2025-11-28 to 2026-10-11 inclusive (UTC).

For each token you are given, list EVERY discrete unlock in the window that released
at least 0.25% of circulating supply or at least $1M at the time. Monthly or quarterly
tranches each count as separate events. A continuous daily release (no single unlock
day) is not an event: list it once with "type": "continuous" and no date, so we can
exclude it.

Good sources: the project's own tokenomics/vesting docs (best: lets you derive every
tranche), Tokenomist, DefiLlama unlocks pages, CryptoRank, tokenomics.com, news
coverage of specific unlocks (PANews / KuCoin / Bitget weekly unlock round-ups,
CoinDesk, The Block). Note: CoinGecko's unlock widget shows Tokenomist data, so it is
not independent of Tokenomist.

For each event record:
- date (YYYY-MM-DD, UTC), timeUTC if published
- amountTokens (number) and how you got it (stated, or derived from vesting terms)
- type: "cliff" (released on one day) or "linear-monthly" (a monthly step of a vesting
  schedule)
- recipientsMix as fractions summing to 1 using buckets team (team, core contributors,
  advisors, founders), investors (seed/private/strategic/VC), community (airdrops,
  public sale, user and staking rewards), ecosystem (ecosystem/development funds,
  foundation treasury, grants, reserve), other. null if no source gives the split.
- whether this was the token's FIRST insider unlock (cliff end) or a routine tranche
- sources with kind primary|aggregator|news and what each confirms

Per token (once): coingeckoId (the id in a CoinGecko URL, e.g. "arbitrum"),
maxSupply (or total supply if uncapped, say which), listed (YYYY-MM).

Output JSON to the path you were given:
```json
[{"token": "ARB", "name": "Arbitrum", "coingeckoId": "arbitrum",
  "maxSupply": 10000000000, "maxSupplyBasis": "max",
  "listed": "2023-03",
  "events": [
    {"date": "2026-03-16", "timeUTC": null, "amountTokens": 92650000,
     "amountHow": "stated by Tokenomist; matches 36-month vesting in Foundation docs",
     "type": "linear-monthly", "firstInsiderUnlock": false,
     "recipientsMix": {"team": 0.606, "investors": 0.394, "community": 0, "ecosystem": 0, "other": 0},
     "sources": [{"label": "...", "url": "https://...", "kind": "primary", "confirms": ["date","amount","recipients"]}],
     "gaps": null}
  ],
  "continuous": null,
  "gaps": "token-level gaps or null"}]
```
Be exhaustive within the window but never invent a tranche: if a schedule says monthly
but you cannot confirm a given month happened, include it only if a source shows it or
the vesting terms make it certain, and say which in amountHow. When finished, reply
with one line per token: number of events found and the main gap.
