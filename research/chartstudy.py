import json,sys,statistics as st,random,collections
from buckets import rows,S
from tiers import tier
F=json.load(open(sys.argv[1] if len(sys.argv)>1 else 'chartfeat_core.json'))
X=[]
for r in rows:
    f=F.get(f"{r['set']}|{r['tok']}|{r['date']}")
    if f: X.append({**r,**f,'tier':tier(r)[0]})
def band(k,cuts,s,label=None):
    print(f'-- {label or k}')
    v=[r for r in s if r.get(k) is not None]
    for a,b in zip(cuts[:-1],cuts[1:]):
        g=[r for r in v if a<=r[k]<b]
        bs=[r for r in g if r['set']=='build']; us=[r for r in g if r['set']=='unseen']
        print(f'   {a:>8}..{b:<8} all {S(g)}   | build {len(bs):>3} {st.mean([r["R"] for r in bs]) if bs else 0:+.2f}  unseen {len(us):>3} {st.mean([r["R"] for r in us]) if us else 0:+.2f}')
inf=1e9
if __name__=='__main__':
    T=[r for r in X if r['tier'] in ('A','B')]
    print('trades (A+B):',len(T), ' with funding',sum(r.get('fund7') is not None for r in T),' with OI',sum(r.get('oiChg') is not None for r in T))
    band('fund7',[-inf,-0.1,0,0.05,0.1,inf],T,'funding paid by longs over the 7 days before entry (%)')
    band('oiChg',[-inf,-20,-5,5,20,inf],T,'open interest change, the week before entry (%)')
    band('ls',[0,1,1.5,2,3,inf],T,'long/short account ratio at entry')
    band('taker',[0,0.9,1.0,1.1,inf],T,'taker buy/sell ratio, day before entry')
    band('aboveSma20',[-inf,-15,-5,0,5,inf],T,'price vs 20-day average at entry (%)')
    band('aboveSma50',[-inf,-25,-10,0,10,inf],T,'price vs 50-day average at entry (%)')
    band('fromHigh60',[-inf,-50,-30,-15,0.01],T,'distance below the 60-day high (%)')
    band('fromLow60',[0,5,15,30,inf],T,'distance above the 60-day low (%)')
    band('atr',[0,5,8,12,inf],T,'daily range, average of last 2 weeks (%)')
    band('volRatio',[0,0.7,1.0,1.5,inf],T,'volume last week vs the 4 weeks before')
    band('bigUpDay',[-inf,5,10,20,inf],T,'biggest up day in the 2 weeks before entry (%)')
    band('redDays',[0,3,5,8],T,'red days in the last 7')
