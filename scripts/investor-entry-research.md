# Investor entry price research

Goal: for each token in the input file, find the price per token that its private investors paid
(seed, private, strategic, Series A/B, token warrants). The desk uses it to test one idea: do
unlock shorts work better when the investors receiving tokens are sitting on a profit?

Tools: load WebSearch and WebFetch with ToolSearch ("select:WebSearch,WebFetch").

## Rules

- Only report a number you saw on a page you opened during this run. Never use memory to fill a
  gap. If nothing can be found, return null for that token. A null is a good answer; a guess is not.
- Best sources: the project's own docs or token blog, regulatory filings, Blockworks token
  transparency filings, The Block / CoinDesk / Messari deal coverage, CryptoRank or ICO Drops
  funding-round pages, Tokenomist allocation pages.
- A disclosed per-token price ("private round at $0.05") is best. If the source gives only a token
  valuation (for example "$200M fully diluted token valuation"), work out the price as valuation ÷
  max (or total) supply, set "implied": true, and say how you did it.
- An equity-only round with no token price or token valuation does not count. Return null for it.
- If there are several rounds, list each one. Mark the round whose investors hold the most tokens
  as "main" (usually the largest private or strategic round). If you cannot tell which is largest,
  pick the latest round before the token launched.
- If two sources disagree, list both values and name each source.

## Output

Write a JSON array to the output file, one object per input token, in this shape:

```
{"token": "XYZ",
 "rounds": [{"name": "Seed", "date": "2023-05", "priceUsd": 0.02, "implied": false,
             "how": "disclosed in the project's tokenomics docs",
             "source": "https://..."}],
 "main": "Seed",
 "notes": "anything a checker should know, e.g. disagreements",
 "searched": ["the queries or pages you tried, if you found nothing"]}
```

Use `"rounds": []` and `"main": null` when nothing usable was found. Keep each object short.
Your final message is just the output path and a one-line count: how many tokens were found and
how many came back null.
