import json,statistics as st,random,collections
from buckets import rows,S,core
F=json.load(open('chartfeat_all.json'))
X=[{**r,**F[k]} for r in rows if (k:=f"{r['set']}|{r['tok']}|{r['date']}") in F and F[k]]
def boot(s,n=3000):
    by=collections.defaultdict(list)
    for r in s: by[r['tok']].append(r['R'])
    g=list(by.values()); rng=random.Random(9)
    m=sorted(st.mean([v for x in rng.choices(g,k=len(g)) for v in x]) for _ in range(n)); return round(m[int(n*.05)],2),round(m[int(n*.95)],2)
oi=lambda r:r.get('oiChg')
Rt=[r for r in X if not core(r)]
a=[r for r in Rt if oi(r) is not None and oi(r)<=-10]; b=[r for r in Rt if oi(r) is not None and oi(r)>-10]
print('routine OI fell 10%+',S(a),boot(a),' | rest',S(b),boot(b))
np=lambda r:(r['pump'] or 0)<30
A=[r for r in X if core(r) and np(r) and (r['pct'] or 0)>=25]
B=[r for r in X if core(r) and np(r) and (r['pct'] or 0)<25]
for lab,s in (('A',A),('B',B)):
    for l2,f in (('OI fell 10%+',lambda r:oi(r)<=-10),('OI -10..+10',lambda r:-10<oi(r)<10),('OI rose 10%+',lambda r:oi(r)>=10)):
        g=[r for r in s if oi(r) is not None and f(r)]
        print(f'  {lab} {l2:<14}',S(g),' build',S([r for r in g if r['set']=='build']),' unseen',S([r for r in g if r['set']=='unseen']))
# candidate strategy v3
def call(r):
    if (r['pump'] or 0)>=30: return None
    if not core(r): return None
    o=oi(r)
    if (r['pct'] or 0)>=25:
        return 'A' if o is None or o<10 else 'A-oiUp'
    return 'B' if o is not None and o<=-10 else None
for lab in ('A','A-oiUp','B'):
    g=[r for r in X if call(r)==lab]
    print(lab,S(g),boot(g) if len(g)>3 else '','build',S([r for r in g if r['set']=='build']),'unseen',S([r for r in g if r['set']=='unseen']))
T=sorted([r for r in X if call(r) in('A','B')],key=lambda r:r['date'])
for risk in (1.0,):
    eq=1;pk=1;dd=0;streak=0;mx=0
    for r in T:
        eq*=1+r['R']*risk/100; pk=max(pk,eq); dd=min(dd,eq/pk-1)
        streak=streak+1 if r['R']<0 else 0; mx=max(mx,streak)
    print(f'v3 all at {risk}%: {len(T)} trades, x{eq:.2f}, max DD {dd*100:.1f}%, longest losing run {mx}')
print('v3 trades per year build-year:',len([r for r in T if r['set']=='build']))
