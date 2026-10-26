# Unlock research brief

You are researching upcoming crypto token unlocks for a public dashboard that scores
(1) how confident we are each unlock is real and correctly sized, and
(2) how much sell pressure it may bring, based on who receives the tokens.

Use today's real date. Your input file lists unlock rows that a previous
pass collected. Treat them as leads, NOT facts: every field must be re-confirmed from
sources you open now. Use WebSearch and WebFetch. Never fill a value from memory.
If you cannot confirm a value, set it to null and say why in `gaps`.

## For each row, find

1. **Date and time (UTC)** of the unlock, and whether it is still upcoming.
   If the real date differs from the input, use the real one and say so in `gaps`.
2. **Amount** in tokens (a number), and its USD value at today's price.
3. **Sources**: at least 2 independent ones where possible. Classify each:
   - `primary`: the project's own docs/tokenomics page/blog/announcement, an official
     X post, or an on-chain vesting contract explorer page.
   - `aggregator`: Tokenomist, DefiLlama unlocks, CryptoRank, tokenomics.com,
     Messari, CoinMarketCap/CoinGecko unlock pages.
   - `news`: CoinDesk, The Block, PANews, KuCoin/Bitget news, CryptoTimes, etc.
   For each source list which facts it confirms: any of "date", "amount", "recipients", "time".
   Two aggregators that clearly copy the same feed count as one; note it.
4. **Recipients mix** for THIS tranche as fractions summing to 1.0, using these buckets:
   `team` (team, core contributors, advisors, founders),
   `investors` (seed/private/strategic/VC backers),
   `community` (airdrops, community/public sale, user rewards, staking rewards),
   `ecosystem` (ecosystem/development fund, foundation treasury, grants, protocol reserve),
   `other`. Only fill it if a source states the split for this tranche or the
   schedule makes it unambiguous; otherwise null.
5. **Market data** (CoinGecko or CoinMarketCap page, note time read):
   price USD, market cap USD (millions), 24h volume is NOT enough: find the
   **30-day average daily volume** if any source shows it; otherwise give the 24h
   volume and say so. Circulating supply and max/total supply, so we can compute
   circulating as % of max. Listing / TGE month (YYYY-MM).
6. **Investor entry price** if the tranche includes investors: the best public
   figure for what seed/private investors paid per token (e.g. CryptoRank fundraising
   page, project announcement), with the round name and source. null if not public.
7. **Seller notes**: 1-3 plain sentences on who gets the tokens and any SOURCED
   evidence of how they behaved at previous unlocks (sold OTC, moved to exchanges,
   restaked, hedged, bought back). Each claim needs its source URL in `sellerSources`.

8. **CoinGecko id**: the id in the token's CoinGecko URL (coingecko.com/en/coins/<id>).

## Output

Write a JSON array to the output path you were given, one object per input row:

```json
{
  "token": "ARB", "name": "Arbitrum", "coingeckoId": "arbitrum",
  "date": "2026-11-16", "timeUTC": "13:00" or null,
  "stillUpcoming": true,
  "amountTokens": 92650000, "amountText": "92.65M ARB",
  "usdM": 17.9,
  "type": "cliff" | "linear",
  "pctCirculating": 1.34,
  "sources": [{"label": "...", "url": "https://...", "kind": "primary|aggregator|news", "confirms": ["date","amount"]}],
  "sourceDisagreements": "plain text, or null",
  "recipients": "plain-language description",
  "recipientsMix": {"team": 0.6, "investors": 0.4, "community": 0, "ecosystem": 0, "other": 0} or null,
  "market": {"priceUsd": 0.19, "mcapUsdM": 1100, "advUsdM": 210, "advBasis": "30d avg" | "24h", "circPctOfMax": 55, "listed": "2023-03", "asOf": "2026-10-21 CoinGecko", "source": "https://..."},
  "investorEntry": {"priceUsd": 0.05, "round": "Series B", "source": "https://..."} or null,
  "sellerNotes": "plain text or null",
  "sellerSources": ["https://..."],
  "gaps": "what you could not confirm, or null"
}
```

Rules: plain English, no predictions, no advice. Prefer fewer, confirmed values over
more, guessed ones. Keep working until every row has been attempted; budget roughly
equal effort per row. When finished, reply with one line per token: what you
confirmed and what is still a gap.

Note: CoinGecko's token-unlock widget shows Tokenomist data, so it is not independent of Tokenomist. Count them as one source.
