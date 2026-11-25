# Unlock short strategy (updated 25 Nov 2026, v5: only unlocks we can short, never MEXC — live test running)

Short only. 1R = the loss when the stop is hit (about 12.7% of the position). Not trading advice.

Trade plan for every setup: short at 00:00 UTC 7 days before the unlock, stop 12% above entry, target 35% below, close whatever is open 14 days after the unlock. Risk 1% of the account per trade.

## v5 (frozen 25 Nov 2026): focus only on unlocks we can short; never MEXC
- Coach K's rule (25 Nov 10:08): check that every token has a perp/futures market we can short, and focus only on those; avoid MEXC because of sanctions. Rules file: data/strategy_v5.json. The setups and trade plan are unchanged.
- **MEXC:** never used for trading, prices or counting as shortable. On 6 Nov 2026, FinCEN (US Treasury) issued an order cutting MEXC off from the US financial system over at least $16B of transactions tied to sanctions evasion and cybercrime (https://www.fincen.gov/system/files/2026-11/MEXC-Section-9714.pdf). Strictly it's a FinCEN order rather than OFAC sanctions.
- **Allowed exchanges:** Binance, Bybit (checked via CoinGecko, listing only), OKX, Bitget, Gate, Hyperliquid, KuCoin.
- **Shortable check:** scripts/shortable.py runs twice a day on GitHub (Live trade log and Morning brief workflows) and writes data/shortable.json. Each unlock on the list is yes / no / unknown, with where it trades and when it was checked. "No" is recorded only when every allowed exchange answered; if any couldn't be reached it's "unknown" and stays on the list.
- **What changes on screen:** the brief, the Picks tab and the Unlocks tab list only shortable unlocks. Can't-short ones sit behind a click with the reason. The 4-hourly research task skips deep research for can't-short unlocks, and adds new unlocks only if it can confirm a perp on an allowed exchange.
- **First run (25 Nov 03:17 UTC):** 66 unlocks checked, 57 shortable, 9 not: ADI (the "ADI" listed elsewhere is a stock perp), KNTQ (only on MEXC), WPAY, RAIN, YZY (×2), KUB, MBG, RYO.

## v4 (frozen 25 Nov 2026): short on other exchanges when Binance has no perp
- Coach K's call (25 Nov): always check where a token trades and short it elsewhere rather than skip; skip only once it's confirmed as fact that it can't be shorted. Rules file: data/strategy_v4.json. The setups, entry, stop, target, exit and size are unchanged from v3.
- **Where:** Binance first. If Binance has no USDT perp, use OKX, Bitget, Gate, Hyperliquid, KuCoin or MEXC, whichever confirmed exchange has the most dollar volume over 7 days. Bybit is checked through CoinGecko's Bybit derivatives page (listing and last price only), because Bybit and Binance's live API refuse GitHub's servers (tested 24 Nov, data/venue_probe.json). Code: scripts/venues.py.
- **Same-token check (required):** the exchange's price must be within 15% of CoinGecko's price for the token, or within 5% of Binance or another exchange. More than 10x off means a different asset. Why: "ADI" on OKX, Bitget, Gate and Bybit is a ~$300+ stock perp (most likely Analog Devices; OKX files it under stocks), while ADI Chain is ~$7. Those exchanges agreed with each other, so for stock tickers, agreement between exchanges doesn't count.
- **Can't-short skip:** made only when all 8 exchanges answered and none lists the real token. If any exchange can't be reached, the token stays on watch and is rechecked. Bybit-only tokens get no call (no Bybit candles from the server).
- **Open-interest rule off Binance:** uses OKX or Gate open-interest history. A first insider unlock that trades only on Bitget, Hyperliquid, KuCoin or MEXC is skipped.
- **Survey 24 Nov** (data/venue_survey.json): ADI (9 Dec) can't be shorted anywhere, confirmed on all 8. KNTQ (27 Dec) is only on MEXC, price confirmed, but there's no open-interest history there, so it will be skipped. Every other candidate trades on Binance plus 4–6 other exchanges.
- **Honest limit:** the off-Binance evidence is 4 historic trades (+5.5R). Smaller exchanges may slip more than the 0.5% assumed.
- **Brief page** (https://coachk-health.github.io/crypto_desk/brief.html, since 25 Nov): what to short today, open shorts, coming up, the record, and every call with its result. It shows where each token has perps and which exchange to short on. It's rebuilt every morning at 06:41 Bangkok and keeps one snapshot per morning in data/briefs/. The Claude artifact version of the brief still exists and is optional.

## Live test (started 19 Nov 2026)
- Rules frozen in data/strategy_v3.json (19 Nov 2026), succeeded by v4 on 25 Nov (above). Any further change becomes v5 with a new date.
- Dashboard: the **Picks** tab (first tab, default) at https://coachk-health.github.io/crypto_desk/ shows only the setups the rules take: open shorts with entry/stop/target, coming-up setups (WATCH), closed trades, and skipped ones with the reason behind a click. Since 22 Nov each card has "Compare entries and exits": short profit from the day −14/−7/−3 opens to the +1/+3/+7/+14 closes, a "now" column from the live Binance price, and a shadow result for "60% off at −35%, rest trails 10%".
- **History tab (since 23 Nov):** data/archive.json, built by scripts/archive.py, keeps every unlock the desk has ever shown (upcoming list, setup grades on Trade signals, Picks), backfilled from the repo's git history (104 unlocks on 23 Nov), never pruned, searchable by token. Each entry shows the size as first/last shown, the best setup grade, the Picks call, when it was shown, a flag if it dropped off the list before its date, and after the unlock what the price did (day −7 open to +1/+3/+7/+14 closes, biggest rise/drop, standard-plan R). Runs twice a day in the Live trade log workflow. Asked for after ARIA vanished from Trade signals once its unlock passed.
- ARIA (21 Nov, 8.3% of circulating, not a first insider unlock) was graded AA on Trade signals but flagged pumped (+210% in 30 days). It was never a pick. The standard short was stopped on entry day (14 Nov); ARIA was +38% from the day −7 open by the day after the unlock.
- scripts/picks.py runs twice a day (Live trade log workflow). Each call is made once, on entry day, from data known before entry, and appended to data/picks_log.json, which is never rewritten; later data never changes a logged call on the page. Calls made after entry day (KITE, MON, JCT, PIEVERSE on day one) are flagged lateCall and not counted in the live record.
- Pass mark: after 30 live trades, average above +0.25R.
- Live record so far (25 Nov): HUMA taken 19 Nov, stopped on entry day (−1.0R), the only counted trade. Note: the desk's unlock data later revised HUMA from 26.5% to 13.0% of circulating (circulating basis corrected), so with today's data it would not have qualified. Late calls (not counted): KITE −1.04R, IRYS −1.0R, MON and GRVT open. Next: WET (entry 2 Dec), CYS (4 Dec, needs open interest to fall 10%+).

Shareable journal (19 Nov v2 calls; not yet updated for the open-interest rule): https://claude.ai/artifact/ShUA8ksjPAokad8wH3XaXT

## The calls (v3, unchanged in v4)
- **TAKE:** the unlock adds 25%+ of circulating supply, and the price is not up 30%+ from 30 days before the unlock to the entry day.
- **TAKE:** the token's first-ever insider unlock under 25%, not pumped 30%+, **and futures open interest fell 10%+ in the week before entry** (day −15 to day −8).
- **SKIP:** everything else — pumped 30%+; first insider unlocks under 25% with flat or rising open interest; routine unlocks; no confirmed USDT perpetual on any exchange (v4); any unlock not confirmed.

## Results (v3 backtest)
| | Trades | Won | Avg a trade | Total |
|---|---|---|---|---|
| Build year (Nov 2025 – Nov 2026) | 38 | 61% | +0.66R | +25.2R |
| Unseen test (Nov 2023 – Nov 2025) | 18 | 67% | +0.93R | +16.7R |
| Both | 56 | 62% | +0.75R (90% range +0.42 to +1.08) | +42.0R |

- Account, both sets in date order: risk 0.5% → ×1.23 (worst drawdown −2.0%); 1% → ×1.51 (−3.9%); 2% → ×2.24 (−7.7%). Longest losing run: 3.
- About 3 setups a month (38 in the build year).

## Entry timing and exits (tested 22 Nov 2026; research/entry_exit.py, research/entry_fair.py)
- **Entry day, fair test** (the call made only with what was known on that day; 52–54 trades each, build + unseen + 2021–25): day −14 → +0.28R a trade, 40% won (range −0.06 to +0.61); **day −7 → +0.74R, 59% won (range +0.38 to +1.08)**; day −3 → +0.42R, 54% won. Day −7 is best in every data set.
- A first naive version showed day −14 as best (+0.78R) only because it picked trades with information from day −7 (look-ahead). Lesson: an earlier entry means deciding with less information.
- Without a stop, earlier is "better" on paper (day −14 → +13.5% average to day +14, day −7 → +8.4%, day −3 → +3.4%) but that ignores the squeezes the stop protects against and uses the day −7 selection.
- **Entry zone** (thirds at −14/−7/−3, each with its own stop): +0.64R at day +14 on the same trades: more winners (64%) but less profit than a single day −7 entry. Not adopted.
- **Exit day with the stop, entry −7:** out +1 → +0.57R, +3 → +0.59R, +7 → +0.61R, +14 → +0.70R. Holding to +14 is best; the 35% target lifts it to +0.81R.
- **60% off at the 35% target, rest trailing** (59 trades with prices to +30): current exit +0.81R; 60% at target + 40% trailing 10% (out by +30) +0.86R; trailing 15% or 20% +0.85R; all out at target but holding up to day +30 for it +0.89R. The differences (≤ 0.08R a trade) are well inside the noise (ranges overlap almost entirely). Shown as a shadow column on the dashboard, not adopted.

## Further tests on data the rules never saw (19 Nov 2026, rules unchanged)
Every unlock re-checked by independent agents before pricing; all data decisions logged before results in research/hist_decisions.md.
- **2021–2025 history, Binance perps** (122 tokens researched): only 12 of 47 big/first unlocks were tradeable on a Binance perp; 9 survived the re-check. v3 took 5: 3 won, +5.5R (+1.10R a trade). Wins: OP May 2023, BLUR Jun 2023, SAND Aug 2022. Losses: SOL Jan 2021 and HFT Nov 2023, both with BTC up 28–47% in the month before entry. The pump filter correctly skipped APT and SRM (both rallied). research/hist_test.json.
- **Bybit / Gate.io perps** (55 new tokens; listing map research/exchange_listings.json): 4 more v3 trades, 3 won, +5.5R (+1.37R a trade): DBR Apr 2025 (target), FLOW Oct 2021 (target, Gate), BOBA Sep 2022 (first insider + OI fell 19%), TAIKO Jun 2025 (stopped day −6, then fell 43%). research/exchange_test.json.
- **Combined new data: 9 trades, 6 won, +11.0R, +1.22R a trade.**
- **Watch item, not a rule:** on the new data the open-interest rule skipped three first-insider unlocks that all won (RAY Feb 2022 +2.2R, ATH Jun 2025 +2.7R, HAEDAL Oct 2025 +1.7R) and took one (BOBA +1.0R). Too few to overturn the 818-unlock evidence; keep the frozen rule and track it live.
- **Watch item:** losses cluster when BTC rallied 20%+ in the month before entry (2 of 3 such trades lost). Not testable on the build year yet (BTC data in research ends 2025).

## Structural trends found in the history
- Big one-day cliff unlocks are mostly a 2023+ phenomenon. Most 2021–22 projects (DeFi, games, L1s) vested team/investor tokens daily or monthly.
- Many big 2021–22 unlocks (FLOW, LQTY, JOE, MAGIC, GLMR, HIGH) happened before Binance or Bybit listed a perp; Gate.io often listed perps first.
- About a third of researched "unlocks" were misleading: token migrations, re-locks (IMX 2022), postponed unlocks (DYDX 2023), launch days, community funds, disputed dates.

## The chart study (917 unlocks; Binance daily candles, funding-rate files and open-interest metrics from data.binance.vision)
- **Open interest is the real tell.** OI falling 10%+ in the week before entry means leverage is leaving and nobody is crowding in to squeeze shorts. First insider unlocks under 25%: OI fell 10%+ → 16 trades, 69% won, +0.78R; otherwise 32 trades, +0.07R (break-even).
- **Confirmed on data it was not found on:** across 818 routine unlocks, OI fell 10%+ → +0.11R a trade (251 trades) vs −0.13R otherwise; OI rising 10%+ → −0.18R.
- For 25%+ unlocks, open interest didn't matter: all of them worked.
- Also bad on routine unlocks: price 0–10% above its 50-day average (−0.18R), more accounts short than long (−0.11R), pumped 30%+ (−0.31R).
- No clean signal from funding rate, volume, daily range, biggest up day or red-day count.

## Earlier findings still standing
- Size matters most: 25%+ of circulating beat smaller unlocks in both sets.
- Routine unlocks lose (820 in the build year, −50.7R), including tokens that dumped at earlier unlocks.
- Who gets the tokens did not sort winners from losers on big/first unlocks.
- "Already falling the week before" did not hold on the unseen test; not a rule.

## Data access notes
- Binance free files (data.binance.vision) work from the cloud container and GitHub: candles, funding, open interest back to 2020.
- From GitHub's servers (where the daily jobs run), the free APIs of OKX, Bitget, Gate, Hyperliquid, KuCoin, MEXC and CoinGecko answer; Bybit and Binance's live API don't (data/venue_probe.json, 24 Nov). The Claude cloud container reaches only OKX of these.
- Bybit and Gate.io history also works from Coach K's built-in browser (used for the 19 Nov history test).
- Proposed (19 Nov, no answer yet): a small fetch script on Coach K's Mac mini for Bybit, plus TradingView links. Since v4 checks Bybit via CoinGecko and the cards carry TradingView or exchange links, this is now only needed for Bybit-only tokens.

## Honest limits
- Rules were refined after looking at the first two data sets; the 2021–25 and Bybit/Gate tests used them unchanged, but samples are small (9 new trades). The live record is the real test.
- Expect about 4 in 10 trades to lose 1R; winners pay (target = +2.7R).
- Live: the entry-day candle is published the day after entry, so the entry price fills in a day late; open interest uses day −9 if day −8 isn't published yet.

## Earlier versions
- v3 (19 Nov): the same rules, Binance perps only.
- v2 (19 Nov): 25%+ full size, first insider half size: 88 trades, +0.50R a trade.
- 18 Nov "strict" rule (falling 5%+ the week before): unseen 13 trades +0.53R after re-check, NOT PROVEN (data/frozen_test.json, data/strategy_frozen.json, data/frozen_test_decisions.md).
- Research scripts and data: research/ in the repo.
