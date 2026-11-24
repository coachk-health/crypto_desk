"""Which exchanges' free public APIs answer from where this runs (GitHub Actions). Writes data/venue_probe.json."""
import json, urllib.request, datetime
from pathlib import Path

T = [
    ("binance", "https://fapi.binance.com/fapi/v1/exchangeInfo", None, lambda d: sum(1 for s in d["symbols"] if s.get("contractType") == "PERPETUAL")),
    ("bybit", "https://api.bybit.com/v5/market/instruments-info?category=linear&limit=1000", None, lambda d: len(d["result"]["list"])),
    ("okx", "https://www.okx.com/api/v5/public/instruments?instType=SWAP", None, lambda d: len(d["data"])),
    ("gate", "https://api.gateio.ws/api/v4/futures/usdt/contracts", None, lambda d: len(d)),
    ("bitget", "https://api.bitget.com/api/v2/mix/market/contracts?productType=USDT-FUTURES", None, lambda d: len(d["data"])),
    ("hyperliquid", "https://api.hyperliquid.xyz/info", b'{"type":"meta"}', lambda d: len(d["universe"])),
    ("mexc", "https://contract.mexc.com/api/v1/contract/detail", None, lambda d: len(d["data"])),
    ("bybit-alt", "https://api.bytick.com/v5/market/instruments-info?category=linear&limit=1000", None, lambda d: len(d["result"]["list"])),
    ("coingecko-bybit", "https://api.coingecko.com/api/v3/derivatives/exchanges/bybit?include_tickers=unexpired", None, lambda d: len(d.get("tickers") or [])),
    ("kucoin", "https://api-futures.kucoin.com/api/v1/contracts/active", None, lambda d: len(d["data"])),
]
out = {"ran": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "venues": {}}
for name, url, body, count in T:
    try:
        req = urllib.request.Request(url, data=body, headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            out["venues"][name] = {"ok": True, "perps": count(json.load(r))}
    except Exception as e:
        out["venues"][name] = {"ok": False, "error": str(e)[:120]}
    print(name, out["venues"][name])
Path("data/venue_probe.json").write_text(json.dumps(out, indent=1) + "\n")
