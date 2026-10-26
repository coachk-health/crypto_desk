# Past unlock re-check brief (independent checker)

You did NOT research these. Catch mistakes before they are published as a track record.
Open sources yourself (WebFetch the cited URLs first; WebSearch only when needed, the
search budget is shared and small). Never rely on memory.

For each token in your input file:
1. Pattern: confirm the unlock rhythm (e.g. monthly on the 16th) and the per-tranche
   amount from at least one source, ideally one the researcher did not cite.
2. Spot-check the earliest event, the latest event, and every event marked
   firstInsiderUnlock. Confirm it happened on that date with roughly that amount.
3. Recipients: does a source support the recipientsMix split?
4. Anything that did not happen (postponed, cancelled, relocked, a tracker model with
   no real transfer) must be removed.

Output a JSON array to your output path:
[{"token": "ARB", "status": "confirmed" | "partial" | "contradicted",
  "notes": "one or two plain sentences",
  "eventFixes": [{"date": "YYYY-MM-DD", "action": "remove" | "fix",
                  "fields": {"date": "...", "amountTokens": 123, "recipientsMix": {...}},
                  "why": "short reason"}]}]
"confirmed": pattern, amounts and spot-checks hold. "partial": core facts hold but
something is unconfirmed (say what). "contradicted": the pattern or amounts are wrong
and could not be fixed; the token will be left out of the track record.
Note: CoinGecko's unlock widget shows Tokenomist data, so it is not independent of Tokenomist.
When done, reply with one line per token.
