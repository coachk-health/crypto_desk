# Coach K Crypto Desk

Live at https://coachk-health.github.io/crypto_desk/ (scenes: https://coachk-health.github.io/crypto_desk/obs.html)

A public follower dashboard plus four OBS scenes for live streams. Static files only: no keys, no fees, no build step.

## What's here

| File | What it is |
|---|---|
| `index.html` | Follower dashboard: today's news, token unlocks, the week ahead, supply and revenue |
| `obs.html` | Scene picker with copy-ready links |
| `obs.html?scene=unlocks` | Next 7 days of unlocks with live countdowns |
| `obs.html?scene=story` | Today's 3 lead stories, rotating (add `&i=0` to hold one; arrow keys switch when you use OBS "Interact") |
| `obs.html?scene=calendar` | The week's market-moving events, ET with Bangkok underneath |
| `obs.html?scene=ticker` | Transparent lower third: live BTC/ETH/SOL, scrolling headlines, next unlock |
| `data/news.json` | Public news, written daily by the Content Desk task |
| `data/unlocks.json` | Unlock snapshot (refresh when you re-research) |
| `data/site.json` | Brand name, tagline, time zone, disclaimer, story rotation seconds |

## OBS setup

1. Sources → **+** → **Browser**.
2. URL: one of the scene links (from the website, or `http://localhost:8787/obs.html?scene=…` when running locally).
3. Width **1920**, height **1080**. Leave "Shutdown source when not visible" off so countdowns keep running.
4. For the ticker, put it on top of your camera scene. Its background is transparent.

Scenes re-read the data every 5 minutes and prices every minute, so you never need to refresh mid-stream.

## Run it locally on the Mac

Double-click `serve.command`. It pulls the latest data from GitHub, then serves the site at `http://localhost:8787`. Keep the window open while streaming.

## Prices

Live prices load in the viewer's browser from CoinGecko's free public API, with Coinbase as backup. If both fail, the page shows the brief's snapshot and says so.

## Daily news update

The 17:30 Bangkok Content Desk task writes `data/news.json` here after it writes the private brief. Only public-safe fields go in: headline, stories (title, mood, summary, points, sources), short briefs and the calendar. Hooks, scripts, keywords, referral angles and compliance notes stay on the private Content Desk.

Not financial advice.
