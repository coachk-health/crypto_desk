#!/usr/bin/env python3
"""Daily exchange candles (open, high, low, close) from Binance's free public data files.

Why: CoinGecko's daily history is wrong for some tokens on some days (in February 2026 it
had NIL at $0.065-0.11 while Binance spot and futures both traded it near $0.05). Exchange
candles are what a trader could actually have filled at, and they include the day's high
and low, which stop-loss and take-profit tests need.

Source order for each token:
  1. Binance USD-M perpetual futures  (data.binance.vision/data/futures/um)  - where shorts are placed
  2. Binance spot                      (data.binance.vision/data/spot)
Symbols tried: <TOKEN>USDT, then 1000<TOKEN>USDT (prices divided by 1000).

A Binance symbol can belong to a different token with the same ticker, so the match is
checked against CoinGecko's recent prices (which agree with exchanges): the median ratio over
the latest overlapping days must be within 5%. No match -> the caller falls back to CoinGecko.

Standard library only. Files are cached in data/cache/bn/ (gitignored).
"""
import csv, io, json, statistics, urllib.error, urllib.request, zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "bn"
BASE = "https://data.binance.vision/data"
MARKETS = [("binance-futures", "futures/um"), ("binance-spot", "spot")]


def _fetch(url, cache_name, refresh=False, cache_missing=True):
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / cache_name
    if f.exists() and not refresh:
        b = f.read_bytes()
        return b if b else None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "coachk-crypto-desk/1.0"})
        with urllib.request.urlopen(req, timeout=40) as r:
            b = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            b = b""
        else:
            raise
    if b or cache_missing:  # a file for the last few days may simply not be published yet
        f.write_bytes(b)
    return b or None


def _rows(zbytes):
    out = {}
    with zipfile.ZipFile(io.BytesIO(zbytes)) as z:
        for name in z.namelist():
            for r in csv.reader(io.TextIOWrapper(z.open(name))):
                if not r or not r[0].isdigit():
                    continue
                ts = int(r[0])
                if ts > 10**14:  # some spot files use microseconds
                    ts //= 1000
                d = datetime.fromtimestamp(ts / 1000, timezone.utc).strftime("%Y-%m-%d")
                out[d] = {"o": float(r[1]), "h": float(r[2]), "l": float(r[3]), "c": float(r[4]), "qv": float(r[7])}
    return out


def _months(a, b):
    y, m = a.year, a.month
    while (y, m) <= (b.year, b.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def symbol_days(market_path, sym, start, end):
    """{date: {o,h,l,c,qv}} for one Binance symbol between start and end (dates)."""
    days = {}
    if not listed(market_path, sym) and not _any_month(market_path, sym, start, end):
        return days
    today = datetime.now(timezone.utc).date()
    for y, m in _months(start, end):
        tag = f"{y}-{m:02d}"
        closed_month = (y, m) < (today.year, today.month)
        b = None
        if closed_month:
            # last month's file appears a few days into the new month
            fresh = (y, m) == ((today.replace(day=1) - timedelta(days=1)).year, (today.replace(day=1) - timedelta(days=1)).month)
            b = _fetch(f"{BASE}/{market_path}/monthly/klines/{sym}/1d/{sym}-1d-{tag}.zip",
                       f"{market_path.replace('/', '_')}-{sym}-{tag}.zip", cache_missing=not (fresh and today.day <= 7))
        if b:
            days.update(_rows(b))
            continue
        if closed_month and not (fresh and today.day <= 7):
            continue  # no file: the symbol was not trading that month
        # current month (or last month before its file is published): daily files
        d = date(y, m, 1)
        while d.month == m and d <= min(end, today - timedelta(days=1)):
            b = _fetch(f"{BASE}/{market_path}/daily/klines/{sym}/1d/{sym}-1d-{d}.zip",
                       f"{market_path.replace('/', '_')}-{sym}-{d}.zip", cache_missing=(today - d).days > 3)
            if b:
                days.update(_rows(b))
            d += timedelta(days=1)
    return days


def _any_month(market_path, sym, start, end):
    """True if any closed month in the range has a file (for symbols delisted since)."""
    today = datetime.now(timezone.utc).date()
    for y, m in _months(start, end):
        if (y, m) >= (today.year, today.month):
            break
        tag = f"{y}-{m:02d}"
        if _fetch(f"{BASE}/{market_path}/monthly/klines/{sym}/1d/{sym}-1d-{tag}.zip",
                  f"{market_path.replace('/', '_')}-{sym}-{tag}.zip"):
            return True
    return False


def listed(market_path, sym):
    """Quick existence check: is there a file for last month?"""
    t = datetime.now(timezone.utc).date().replace(day=1) - timedelta(days=1)
    tag = f"{t.year}-{t.month:02d}"
    return _fetch(f"{BASE}/{market_path}/monthly/klines/{sym}/1d/{sym}-1d-{tag}.zip",
                  f"{market_path.replace('/', '_')}-{sym}-{tag}.zip") is not None


def token_days(token, start, end, cg_days=None):
    """Best exchange candles for a token. Returns (source, symbol, days) or (None, None, {}).
    cg_days: CoinGecko {date: {price}} used only to confirm the symbol is the same token."""
    for name, path in MARKETS:
        for sym, scale in ((f"{token}USDT", 1.0), (f"1000{token}USDT", 1000.0)):
            try:
                days = symbol_days(path, sym, start, end)
            except Exception:
                days = {}
            if len(days) < 20:
                continue
            if scale != 1.0:
                days = {d: {k: (v / scale if k != "qv" else v) for k, v in x.items()} for d, x in days.items()}
            if cg_days is not None and not same_token(days, cg_days):
                continue
            return name, sym, days
    return None, None, {}


def same_token(days, cg_days, n=10):
    common = sorted(d for d in days if (cg_days.get(d) or {}).get("price"))
    if len(common) < 5:
        return False
    recent = common[-n:]
    r = statistics.median(days[d]["o"] / cg_days[d]["price"] for d in recent)
    return abs(r - 1) <= 0.05


if __name__ == "__main__":
    import sys
    tok = sys.argv[1] if len(sys.argv) > 1 else "NIL"
    src, sym, d = token_days(tok, date(2026, 2, 20), date(2026, 3, 5))
    print(src, sym, json.dumps({k: d[k] for k in sorted(d)[:3]}))
