# Independent re-check of researched unlocks

You are checking someone else's research. You are NOT told any price outcome and must not look up how the price moved after the unlock. Your only job: are the facts right?

For each item in your input file, using web sources you fetch now (never memory):
1. **date** — the exact UTC day the tokens became transferable/tradable. Prefer the project's own announcement, docs or vesting contract; then CoinDesk/The Block/Cointelegraph/Tokenomist/CryptoRank/DefiLlama. If sources disagree by more than 2 days and there is no project statement, say so.
2. **firstInsiderUnlock** — was this the FIRST time team/investors/advisors received transferable tokens? (true/false/unknown). Note if tokens were re-locked, migrated, or delayed.
3. **pctCirculating** — the unlock amount as a percent of circulating supply just before it. Give amount and circulating with sources.
4. **shape** — lump (most released in one day) or stream (spread daily/weekly).
5. **priceUsd** — the token's USD price on that date from a price source (CoinGecko/CoinMarketCap history page, or a news article quoting it), used only to make sure we price the right ticker. Do NOT report later price moves.

Output a JSON array to the output path, one object per input item, same order:
{"token","claimedDate","verdict": "confirmed"|"date_wrong"|"not_first_insider"|"not_a_real_unlock"|"unverifiable",
 "date","dateSources":[urls],"dateDisagreementDays", "firstInsiderUnlock","pctCirculating","amountTokens","circulatingBefore",
 "shape","priceUsd","priceSource","notes"}
Be strict: "confirmed" only if at least one primary or two independent secondary sources support the date within 1 day.
