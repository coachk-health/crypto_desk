import json,random,statistics as st,collections
from buckets import rows,S,core
def boot(s,key='R',n=3000):
    s=[r for r in s if r.get(key) is not None]
    by=collections.defaultdict(list)
    for r in s: by[r['tok']].append(r[key])
    g=list(by.values()); rng=random.Random(5)
    m=sorted(st.mean([v for x in rng.choices(g,k=len(g)) for v in x]) for _ in range(n)); return round(m[int(n*.05)],2),round(m[int(n*.95)],2)
CN=lambda s:[r for r in rows if r['set']==s and core(r) and (r['pump'] is None or r['pump']<30)]
for s in ('build','unseen'):
    X=CN(s); print(s,'core not pumped',S(X),boot(X))
X=CN('build')+CN('unseen'); print('both',S(X),boot(X))
print('\n-- inside core-not-pumped (build): who gets the tokens')
B=CN('build'); U=CN('unseen')
for w in sorted({r['who'] for r in B+U}): print(f'  {w:<16} build',S([r for r in B if r['who']==w]),' unseen',S([r for r in U if r['who']==w]))
print('-- first insider vs 25%+ only')
print('  first insider  build',S([r for r in B if r['first']]),' unseen',S([r for r in U if r['first']])); print('  25%+ not first build',S([r for r in B if not r['first']]),' unseen',S([r for r in U if not r['first']]))
print('-- cliff vs linear (build)')
for t in sorted({str(r['type']) for r in B}): print(f'  {t:<16}',S([r for r in B if str(r['type'])==t]))
print('-- size vs trading volume (build)')
for lab,a,b in [('<1 day',0,1),('1-5 days',1,5),('5-20 days',5,20),('20+ days',20,1e9)]: print(f'  {lab:<16}',S([r for r in B if r['adv'] is not None and a<=r['adv']<b]))
print('-- size % of circulating')
for lab,a,b in [('<10%',0,10),('10-25%',10,25),('25-50%',25,50),('50%+',50,1e9)]:
    print(f'  {lab:<16} build',S([r for r in B if r['pct'] is not None and a<=r['pct']<b]),' unseen',S([r for r in U if r['pct'] is not None and a<=r['pct']<b]))
print('-- the week before')
for lab,a,b in [('crashed 20%+',-1e9,-20),('fell 5-20%',-20,-5),('flat',-5,5),('rose 5%+',5,1e9)]:
    print(f'  {lab:<16} build',S([r for r in B if r['week'] is not None and a<=r['week']<b]),' unseen',S([r for r in U if r['week'] is not None and a<=r['week']<b]))
print('-- pump bands (core)')
C=[r for r in rows if core(r)]
for lab,a,b in [('fell 30%+',-1e9,-30),('-30..0',-30,0),('0..+15',0,15),('+15..+30',15,30),('+30%+',30,1e9)]:
    print(f'  {lab:<12} build',S([r for r in C if r['set']=='build' and r['pump'] is not None and a<=r['pump']<b]),' unseen',S([r for r in C if r['set']=='unseen' and r['pump'] is not None and a<=r['pump']<b]))
print('\n-- prior unlocks of the same token (build, 2+ earlier unlocks)')
Rt=[r for r in rows if r['set']=='build' and r['prevN']>=2]
for lab,a,b in [('dumped 10%+ avg before',-1e9,-10),('-10..0',-10,0),('rose before',0,1e9)]:
    s=[r for r in Rt if a<=r['prevAvg']<b]; print(f'  {lab:<24}',S(s), ' + falling wk:',S([r for r in s if r['week'] is not None and r['week']<=-5]),' + falling & not pumped:',S([r for r in s if r['week'] is not None and r['week']<=-5 and (r['pump'] or 0)<30]))
