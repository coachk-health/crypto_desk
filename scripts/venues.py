#!/usr/bin/env python3
"""Where a token's USDT perpetual trades, and its daily candles / open interest off Binance.

Free public APIs only (no keys). From GitHub's servers these answer: OKX, Bitget, Gate, Hyperliquid,
KuCoin, MEXC and CoinGecko (tested 24 Nov 2026, data/venue_probe.json). Bybit and Binance's live API
refuse GitHub's servers: Binance is read from its free data files (candles.py), and Bybit's perp list
and last prices come from CoinGecko's derivatives page for Bybit (listing check only, no candles).

A ticker match is not proof it is the same token (OKX's "ADI" is a ~$300 asset; ADI Chain is ~$7).
So a venue is only used when its price agrees with Binance or another venue (within 5%), or with the
unlock record's implied price (usdM / amountTokens, within 2x; that price can be weeks old). More than
10x off the implied price = a different asset. Anything else = can't confirm, so not traded.

Candles: OKX, Bitget, Gate, Hyperliquid, KuCoin, MEXC (UTC daily bars only; a venue whose daily bar
doesn't start at 00:00 UTC is not used for pricing).
Open interest history: Binance (picks.py), OKX and Gate.
"""
import json, statistics, time, urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "venues"
CHECKED = ("okx", "bitget", "gate", "hyperliquid", "kucoin", "mexc", "bybit")
NAMES = {"binance": "Binance", "okx": "OKX", "bitget": "Bitget", "gate": "Gate", "hyperliquid": "Hyperliquid",
         "kucoin": "KuCoin", "mexc": "MEXC", "bybit": "Bybit"}
PRICED = ("okx", "bitget", "gate", "hyperliquid", "kucoin", "mexc")
_lists, _err = {}, {}


def _get(url, body=None):
    req = urllib.request.Request(url, data=body, headers={"User-Agent": "coachk-crypto-desk/1.0", "Content-Type": "application/json"})
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (403, 451) or i == 2:
                raise
        except Exception:
            if i == 2:
                raise
        time.sleep(1.5 * (i + 1))


def _ms(d):
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


def _day(ms):
    return datetime.fromtimestamp(int(ms) / 1000, timezone.utc).date().isoformat()


# ---------- which tickers have a USDT perp on each venue ----------
def _list(v):
    if v == "okx":
        d = _get("https://www.okx.com/api/v5/public/instruments?instType=SWAP")["data"]
        # instCategory 1 = crypto; 3 = stocks (AAPL, ADI = Analog Devices...), 4 = commodities. Crypto only.
        L = {i["instId"][:-10]: i["instId"] for i in d if i["instId"].endswith("-USDT-SWAP") and i.get("state") == "live" and i.get("instCategory", "1") == "1"}
        L["__tradfi__"] = sorted({i["instId"].split("-")[0] for i in d if i.get("instCategory") not in (None, "", "1")})
        return L
    if v == "bitget":
        d = _get("https://api.bitget.com/api/v2/mix/market/contracts?productType=USDT-FUTURES")["data"]
        return {i["baseCoin"]: i["symbol"] for i in d if i.get("symbolStatus") == "normal" and i.get("quoteCoin") == "USDT"}
    if v == "gate":
        d = _get("https://api.gateio.ws/api/v4/futures/usdt/contracts")
        return {i["name"][:-5]: i["name"] for i in d if i["name"].endswith("_USDT") and not i.get("in_delisting")}
    if v == "hyperliquid":
        d = _get("https://api.hyperliquid.xyz/info", b'{"type":"meta"}')["universe"]
        return {i["name"]: i["name"] for i in d if not i.get("isDelisted")}
    if v == "kucoin":
        d = _get("https://api-futures.kucoin.com/api/v1/contracts/active")["data"]
        return {("BTC" if i["baseCurrency"] == "XBT" else i["baseCurrency"]): i["symbol"] for i in d
                if i.get("quoteCurrency") == "USDT" and i.get("isInverse") is False and i["symbol"].endswith("USDTM")}
    if v == "mexc":
        d = _get("https://contract.mexc.com/api/v1/contract/detail")["data"]
        return {i["baseCoin"]: i["symbol"] for i in d if i.get("quoteCoin") == "USDT" and i.get("state") == 0}
    if v == "bybit":
        d = _get("https://api.coingecko.com/api/v3/derivatives/exchanges/bybit?include_tickers=unexpired").get("tickers") or []
        out = {}
        for t in d:
            if (t.get("contract_type") or "perpetual") != "perpetual" or (t.get("target") or "USDT") != "USDT":
                continue
            b = t.get("base") or (t.get("symbol") or "").replace("USDT", "")
            if b and t.get("last"):
                out[b] = t.get("symbol") or b + "USDT"
                out.setdefault("__last__", {})[b] = float(t["last"])
        return out
    raise ValueError(v)


def perp_list(v):
    """{TICKER: venue symbol}, cached for the day. None if the venue could not be reached."""
    if v in _lists:
        return _lists[v]
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{v}-list-{date.today().isoformat()}.json"
    try:
        if f.exists():
            out = json.loads(f.read_text())
        else:
            out = _list(v)
            f.write_text(json.dumps(out))
    except Exception as e:
        _err[v] = str(e)[:100]
        out = None
    _lists[v] = out
    return out


def tradfi():
    """Tickers OKX lists as stocks or commodities. Other exchanges may list the same stock under the
    same ticker, so for these a match between exchanges proves nothing."""
    L = perp_list("okx")
    return set(L.get("__tradfi__", [])) if L else set()


def symbol_for(v, token):
    L = perp_list(v)
    if not L:
        return None
    for t in (token, "1000" + token, "k" + token):
        if t in L and not t.startswith("__"):
            return L[t], (1000.0 if t != token else 1.0)
    return None


# ---------- daily candles ----------
def _candles(v, sym, start, end):
    out = {}
    if v == "okx":
        after = _ms(end + timedelta(days=1))
        while True:
            d = _get(f"https://www.okx.com/api/v5/market/history-candles?instId={sym}&bar=1Dutc&after={after}&limit=100")["data"]
            if not d:
                break
            for r in d:
                out[_day(r[0])] = {"o": float(r[1]), "h": float(r[2]), "l": float(r[3]), "c": float(r[4]), "qv": float(r[7]), "done": r[8] == "1"}
            after = int(d[-1][0])
            if after <= _ms(start) or len(d) < 100:
                break
    elif v == "bitget":
        d = _get(f"https://api.bitget.com/api/v2/mix/market/history-candles?symbol={sym}&productType=USDT-FUTURES&granularity=1Dutc"
                 f"&startTime={_ms(start)}&endTime={_ms(end + timedelta(days=1))}&limit=200")["data"]
        for r in d:
            out[_day(r[0])] = {"o": float(r[1]), "h": float(r[2]), "l": float(r[3]), "c": float(r[4]), "qv": float(r[6])}
    elif v == "gate":
        d = _get(f"https://api.gateio.ws/api/v4/futures/usdt/candlesticks?contract={sym}&interval=1d"
                 f"&from={_ms(start) // 1000}&to={_ms(end) // 1000}")
        for r in d:
            out[_day(int(r["t"]) * 1000)] = {"o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"]), "qv": float(r.get("sum") or 0)}
    elif v == "hyperliquid":
        body = json.dumps({"type": "candleSnapshot", "req": {"coin": sym, "interval": "1d", "startTime": _ms(start), "endTime": _ms(end + timedelta(days=1))}}).encode()
        for r in _get("https://api.hyperliquid.xyz/info", body):
            out[_day(r["t"])] = {"o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"]), "qv": float(r["v"]) * float(r["c"])}
    elif v == "kucoin":
        d = _get(f"https://api-futures.kucoin.com/api/v1/kline/query?symbol={sym}&granularity=1440&from={_ms(start)}&to={_ms(end + timedelta(days=1))}")["data"]
        for r in d:
            if int(r[0]) % 86400000 == 0:
                out[_day(r[0])] = {"o": float(r[1]), "h": float(r[2]), "l": float(r[3]), "c": float(r[4]), "qv": float(r[6])}
    elif v == "mexc":
        d = _get(f"https://contract.mexc.com/api/v1/contract/kline/{sym}?interval=Day1&start={_ms(start) // 1000}&end={_ms(end + timedelta(days=1)) // 1000}")["data"]
        for i, t in enumerate(d.get("time") or []):
            if int(t) % 86400 == 0:
                out[_day(int(t) * 1000)] = {"o": float(d["open"][i]), "h": float(d["high"][i]), "l": float(d["low"][i]), "c": float(d["close"][i]), "qv": float(d["amount"][i])}
    today = datetime.now(timezone.utc).date().isoformat()
    # keep completed UTC days only (today's bar is still forming), inside the window
    return {k: {x: y for x, y in b.items() if x != "done"} for k, b in out.items()
            if start.isoformat() <= k <= end.isoformat() and k < today}


def days(v, token, start, end):
    """(venue symbol, {date: {o,h,l,c,qv}}) for a priced venue, or (None, {})."""
    s = symbol_for(v, token)
    if not s:
        return None, {}
    sym, scale = s
    try:
        d = _candles(v, sym, start, end)
    except Exception as e:
        _err[v] = str(e)[:100]
        return sym, {}
    if scale != 1.0:
        d = {k: {x: (y / scale if x != "qv" else y) for x, y in b.items()} for k, b in d.items()}
    return sym, d


# ---------- open interest history (token units) ----------
def oi_day(v, sym, d):
    """Open interest at the end of UTC day d, or None."""
    try:
        if v == "okx":
            rows = _get(f"https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-history?instId={sym}&period=1D&limit=100")["data"]
            # each row is stamped at the start of its day; the next day's stamp is the end of day d
            want = _ms(d + timedelta(days=1))
            for r in rows:
                if int(r[0]) == want:
                    return float(r[2])
        elif v == "gate":
            rows = _get(f"https://api.gateio.ws/api/v4/futures/usdt/contract_stats?contract={sym}&interval=1d&limit=100")
            want = _ms(d + timedelta(days=1)) // 1000
            for r in rows:
                if int(r["time"]) == want:
                    return float(r["open_interest"])
    except Exception as e:
        _err[v] = str(e)[:100]
    return None


# ---------- choose a venue ----------
_cg = {}


def cg_price(cid):
    """CoinGecko's current USD price for the token's own CoinGecko id: the best 'is it the same token' check."""
    if not cid:
        return None
    if not _cg:   # one request for every upcoming token (CoinGecko's free API allows only a few calls a minute)
        ids = {u.get("coingeckoId") for u in json.loads((ROOT / "data" / "unlocks.json").read_text()).get("upcoming", [])} | {cid}
        ids = sorted(i for i in ids if i)
        try:
            j = _get("https://api.coingecko.com/api/v3/simple/price?vs_currencies=usd&ids=" + ",".join(ids))
            _cg.update({i: float(j[i]["usd"]) for i in ids if (j.get(i) or {}).get("usd")})
        except Exception as e:
            _err["coingecko"] = str(e)[:100]
        _cg.setdefault("__tried__", True)
    return _cg.get(cid)


def implied_price(r):
    try:
        return r["usdM"] * 1e6 / r["amountTokens"] if r.get("usdM") and r.get("amountTokens") else None
    except Exception:
        return None


def _close(d):
    return d[max(d)]["c"] if d else None


def survey(token, r, start, end, binance_days=None):
    """Every venue: is there a USDT perp, is it the same token, recent daily volume.
    Returns (rows, best) where best = (venue, symbol, days) of the most liquid confirmed priced venue, or None."""
    cg = cg_price(r.get("coingeckoId"))
    ref = cg or implied_price(r)
    refname = "CoinGecko's price" if cg else "the unlock data"
    got = {}
    for v in PRICED:
        sym, d = days(v, token, start, end)
        if sym:
            got[v] = (sym, d)
    closes = {v: _close(d) for v, (s, d) in got.items() if d}
    if binance_days:
        closes["binance"] = _close(binance_days)
    rows = []
    for v in CHECKED:
        L = perp_list(v)
        if L is None:
            rows.append({"venue": NAMES[v], "listed": None, "note": "could not reach"})
            continue
        s = symbol_for(v, token)
        if not s:
            continue
        row = {"venue": NAMES[v], "symbol": s[0], "listed": True}
        if v in got or v == "bybit":
            sym, d = got.get(v) or (s[0], {})
            c = closes.get(v) if v != "bybit" else (L.get("__last__") or {}).get(token)
            if v == "bybit":
                d = {"last": {"c": c, "qv": 0}} if c else {}
            row["lastClose"] = c
            row["qv7"] = round(statistics.mean(b["qv"] for b in [d[k] for k in sorted(d)[-7:]])) if d and v != "bybit" else None
            # a stock ticker shared with the token: only Binance or the unlock data can confirm it
            others = [x for k, x in closes.items() if k != v and x and (k == "binance" or token not in tradfi())]
            agree = any(abs(c / x - 1) <= 0.05 for x in others) if c else False
            ratio = c / ref if (c and ref) else None
            if not d:
                row["match"], row["note"] = None, "no candles"
            elif ratio and (ratio < 0.1 or ratio > 10):   # far off the token's own price: never trust agreement
                row["match"], row["note"] = False, f"different asset: price {c:.4g} vs ~{ref:.4g} ({refname})"
            elif agree or (ratio and ((0.85 <= ratio <= 1.15) if cg else (0.5 <= ratio <= 2.0))):
                row["match"] = True
            else:
                row["match"], row["note"] = None, "can't confirm it's the same token"
        else:
            row["match"], row["note"] = None, "no UTC daily candles"
        rows.append(row)
    ok = [x for x in rows if x.get("match") is True and _key(x["venue"]) in got and len(got[_key(x["venue"])][1]) >= 20]
    best = None
    if ok:
        x = max(ok, key=lambda x: x.get("qv7") or 0)
        k = _key(x["venue"])
        best = (k, got[k][0], got[k][1])
    return rows, best


def _key(name):
    return next(k for k, n in NAMES.items() if n == name)


def trade_link(v, sym):
    return {"okx": f"https://www.okx.com/trade-swap/{sym.lower()}",
            "bitget": f"https://www.bitget.com/futures/usdt/{sym}",
            "gate": f"https://www.gate.com/futures/USDT/{sym}",
            "hyperliquid": f"https://app.hyperliquid.xyz/trade/{sym}",
            "kucoin": f"https://www.kucoin.com/futures/trade/{sym}",
            "mexc": f"https://futures.mexc.com/exchange/{sym}"}.get(v)


def checked():
    """Which venues answered in this run (the proof behind a 'no perp anywhere' skip)."""
    return {"at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "reached": ["Binance (data files)"] + [NAMES[v] + (" (via CoinGecko)" if v == "bybit" else "") for v in CHECKED if _lists.get(v) is not None],
            "unreachable": [NAMES[v] for v in CHECKED if v in _lists and _lists[v] is None]}


def errors():
    return dict(_err)


if __name__ == "__main__":
    import sys
    tok = sys.argv[1] if len(sys.argv) > 1 else "ADI"
    rec = {"usdM": float(sys.argv[2]), "amountTokens": float(sys.argv[3])} if len(sys.argv) > 3 else {}
    rows, best = survey(tok, rec, date.today() - timedelta(days=45), date.today())
    print(json.dumps(rows, indent=1)); print("best:", best and (best[0], best[1], len(best[2])), errors())
