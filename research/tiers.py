import json,random,statistics as st,collections
from buckets import rows,S,core
from dig import boot
def tier(r):
    if r['pump'] is not None and r['pump']>=30: return 'SKIP','pumped 30%+ into the unlock'
    if (r['pct'] or 0)>=25: return 'A','25%+ of circulating supply, not pumped'
    if r['first']: return 'B','first insider unlock, under 25%, not pumped'
    return 'SKIP','routine unlock'
for r in rows: r['tier'],r['tierWhy']=tier(r)
if __name__=='__main__':
    for t in ('A','B','SKIP'):
        b=[r for r in rows if r['set']=='build' and r['tier']==t]; u=[r for r in rows if r['set']=='unseen' and r['tier']==t]
        print(t,'build',S(b),boot(b) if len(b)>3 else '','\n   unseen',S(u),boot(u) if len(u)>3 else '','\n   both',S(b+u),boot(b+u) if len(b+u)>3 else '')
    # A with falling filter
    for lab,f in (('A falling 5%+',lambda r:r['week'] is not None and r['week']<=-5),('A flat',lambda r:r['week'] is not None and -5<r['week']<5),('A rising',lambda r:r['week'] is not None and r['week']>=5)):
        for s in ('build','unseen'): print(lab,s,S([r for r in rows if r['set']==s and r['tier']=='A' and f(r)]))
    # account sim, both sets chronological, A full 1%, B half 0.5%
    for risk_b in (0.5,1.0):
        tr=sorted([r for r in rows if r['tier'] in('A','B')],key=lambda r:r['date'])
        eq=1.0;peak=1;dd=0
        for r in tr:
            eq*=1+r['R']*(0.01 if r['tier']=='A' else risk_b/100); peak=max(peak,eq); dd=min(dd,eq/peak-1)
        print(f'account A=1% B={risk_b}%: x{eq:.2f} maxDD {dd*100:.1f}% over {len(tr)} trades, {tr[0]["date"]}..{tr[-1]["date"]}')
