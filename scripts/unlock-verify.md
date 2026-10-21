# Unlock re-check brief (independent checker)

You did NOT write these rows. Your job is to catch mistakes before they go on a public
page. Re-open sources yourself with WebFetch/WebSearch; never rely on memory; never
assume a field is right because it looks plausible.

For each row in your input file check, against the row's own cited sources and at
least one source you find independently where possible:

1. date (and timeUTC if given) of the unlock, and that it is still upcoming
2. amountTokens and usdM (usdM should be close to amountTokens x current price)
3. pctCirculating (amount / circulating supply)
4. recipientsMix (does a source actually state this split for THIS tranche?)
5. market: priceUsd, advUsdM (and advBasis), circPctOfMax, listed month
6. investorEntry: is it a disclosed per-token price, or worked out from a valuation?
   If worked out, set "implied": true in your correction. If unsupported, set it to null.
7. sellerNotes: is every claim backed by one of sellerSources? Remove anything that is not.

Output a JSON array to the path you were given, one object per row:
{"token": "...", "date": "YYYY-MM-DD",
 "status": "confirmed" | "partial" | "contradicted",
 "notes": "one or two plain sentences: what you confirmed, what you could not",
 "corrections": {"field": correctedValue, ...}}

- "confirmed": date and amount independently confirmed, nothing material wrong.
- "partial": core facts hold but something could not be confirmed (say what in notes).
- "contradicted": a source you opened shows the date, amount or recipients are wrong
  and you could not resolve it. Put the correct value in corrections when you can.
Corrections may replace whole objects (e.g. "market", "recipientsMix", "investorEntry",
"sellerNotes", "date", "usdM", "pctCirculating", "sources"). Keep notes short and plain.
