/* Shared data + formatting for the stream desk. No build step, no keys. */
(function () {
  const PRICE_IDS = { btc: 'bitcoin', eth: 'ethereum', sol: 'solana' };

  async function json(path) {
    const r = await fetch(path + (path.includes('?') ? '&' : '?') + 't=' + Date.now(), { cache: 'no-store' });
    if (!r.ok) throw new Error(path + ' returned ' + r.status);
    return r.json();
  }

  async function load(base) {
    base = base || '';
    const [news, unlocks, site] = await Promise.all([
      json(base + 'data/news.json'),
      json(base + 'data/unlocks.json'),
      json(base + 'data/site.json').catch(() => ({}))
    ]);
    return { news, unlocks, site };
  }

  /* Live prices from the viewer's browser: CoinGecko, then Coinbase, then the brief's snapshot. */
  async function prices(snapshot) {
    try {
      const ids = Object.values(PRICE_IDS).join(',');
      const r = await fetch('https://api.coingecko.com/api/v3/simple/price?ids=' + ids + '&vs_currencies=usd&include_24hr_change=true');
      if (!r.ok) throw new Error('coingecko ' + r.status);
      const d = await r.json();
      const out = { live: true, source: 'CoinGecko', asOf: new Date() };
      for (const k in PRICE_IDS) {
        const x = d[PRICE_IDS[k]];
        if (x) out[k] = { price: x.usd, chg24h: x.usd_24h_change };
      }
      if (out.btc) return out;
    } catch (e) { /* fall through */ }
    try {
      const out = { live: true, source: 'Coinbase', asOf: new Date() };
      await Promise.all(Object.keys(PRICE_IDS).map(async k => {
        const r = await fetch('https://api.coinbase.com/v2/prices/' + k.toUpperCase() + '-USD/spot');
        const d = await r.json();
        out[k] = { price: +d.data.amount, chg24h: null };
      }));
      if (out.btc) return out;
    } catch (e) { /* fall through */ }
    const m = snapshot || {};
    return { live: false, source: m.asOf || 'brief', btc: m.btc, eth: m.eth, sol: m.sol };
  }

  /* Unlock moment in UTC. Without a time we only know the day. */
  function unlockDate(u) {
    const [y, mo, d] = u.date.split('-').map(Number);
    let h = 0, mi = 0;
    if (u.timeUTC) [h, mi] = u.timeUTC.split(':').map(Number);
    return new Date(Date.UTC(y, mo - 1, d, h, mi));
  }

  function countdown(u, now) {
    const t = unlockDate(u), exact = !!u.timeUTC;
    const ms = t - now;
    if (exact) {
      if (ms <= 0) return { text: 'Unlocked', past: true };
      const s = Math.floor(ms / 1000);
      const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60), sec = s % 60;
      const pad = n => String(n).padStart(2, '0');
      return { text: d > 0 ? d + 'd ' + pad(h) + 'h ' + pad(m) + 'm' : pad(h) + ':' + pad(m) + ':' + pad(sec), past: false, soon: ms < 86400000 };
    }
    // Day only: count whole UTC days.
    const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
    const days = Math.round((t - today) / 86400000);
    if (days < 0) return { text: 'Unlocked', past: true };
    if (days === 0) return { text: 'Today', past: false, soon: true };
    if (days === 1) return { text: 'Tomorrow', past: false, soon: true };
    if (days < 7) return { text: t.toLocaleDateString('en-US', { weekday: 'long', timeZone: 'UTC' }), past: false };
    return { text: t.toLocaleDateString('en-US', { day: 'numeric', month: 'short', timeZone: 'UTC' }), past: false };
  }

  function sortKey(u) { return unlockDate(u).getTime() + (u.timeUTC ? 0 : 86399000); }

  function upcoming(unlocks, now, days) {
    const end = now.getTime() + days * 86400000;
    return unlocks.upcoming
      .filter(u => {
        const t = unlockDate(u).getTime();
        const grace = u.timeUTC ? 0 : 86400000; // day-only rows stay up through their day
        return t + grace > now.getTime() && t <= end;
      })
      // Day-only rows sort to the end of their day so they don't jump ahead of timed ones.
      .sort((a, b) => sortKey(a) - sortKey(b));
  }

  function usd(m) {
    if (m == null || isNaN(m)) return null;
    if (m >= 1000) return '$' + (m / 1000).toFixed(2) + 'B';
    if (m >= 100) return '$' + Math.round(m) + 'M';
    if (m >= 10) return '$' + m.toFixed(1) + 'M';
    return '$' + m.toFixed(2) + 'M';
  }

  function price(p) {
    if (p == null) return '—';
    return '$' + Number(p).toLocaleString('en-US', { maximumFractionDigits: p < 10 ? 3 : p < 1000 ? 2 : 0 });
  }

  function change(c) {
    if (c == null || isNaN(c)) return { text: '', dir: '' };
    return { text: (c > 0 ? '+' : '') + c.toFixed(2) + '%', dir: c < 0 ? 'down' : 'up' };
  }

  function dayLabel(u, tz) {
    const t = unlockDate(u);
    const opts = { weekday: 'short', day: 'numeric', month: 'short', timeZone: u.timeUTC ? tz : 'UTC' };
    let s = t.toLocaleDateString('en-US', opts);
    if (u.timeUTC) s += ', ' + t.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: tz });
    else s += ', time not announced';
    return s;
  }

  function el(tag, attrs, kids) {
    const n = document.createElement(tag);
    if (attrs) for (const k in attrs) {
      const v = attrs[k];
      if (v == null || v === false) continue;
      if (k === 'class') n.className = v;
      else if (k === 'text') n.textContent = v;
      else if (k === 'style') n.style.cssText = v;
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    }
    (kids || []).forEach(c => { if (c != null && c !== false) n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
    return n;
  }

  /* Supply bar width: % of supply, 10% or more fills the bar. */
  function supplyWidth(pct) { return pct == null ? 0 : Math.min(100, Math.max(3, pct * 10)); }

  /* Hours since an ISO timestamp, or null. */
  function ageHours(iso) { const t = Date.parse(iso); return isNaN(t) ? null : (Date.now() - t) / 3600000; }

  function ago(iso) {
    const h = ageHours(iso); if (h == null) return 'unknown';
    if (h < 1) return Math.max(1, Math.round(h * 60)) + ' min ago';
    if (h < 48) return Math.round(h) + ' h ago';
    return Math.round(h / 24) + ' days ago';
  }

  window.Desk = { ageHours, ago, load, prices, unlockDate, countdown, upcoming, usd, price, change, dayLabel, el, supplyWidth };
})();
