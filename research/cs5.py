import json,statistics as st
from cs4 import X,S,boot,core,oi
def call(r):
    if (r['pump'] or 0)>=30 or not core(r): return None
    if (r['pct'] or 0)>=25: return 'A'
    return 'B' if oi(r) is not None and oi(r)<=-10 else None
T=sorted([r for r in X if call(r)],key=lambda r:r['date'])
print('v3',S(T),boot(T),' build',S([r for r in T if r['set']=='build']),' unseen',S([r for r in T if r['set']=='unseen']))
for risk in (0.5,1.0,2.0):
    eq=1;pk=1;dd=0;st_=0;mx=0
    for r in T:
        eq*=1+r['R']*risk/100; pk=max(pk,eq); dd=min(dd,eq/pk-1); st_=st_+1 if r['R']<0 else 0; mx=max(mx,st_)
    print(f' risk {risk}%: x{eq:.2f}, worst DD {dd*100:.1f}%, longest losing run {mx}')
b=[r for r in T if r['set']=='build']; print('build-year trades',len(b),'=> per month',round(len(b)/12,1))
json.dump([{k:r[k] for k in ('set','tok','date','R','why','pct','first','pump','week','oiChg')} for r in T],open('v3_trades.json','w'))
