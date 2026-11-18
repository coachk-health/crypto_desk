import json,statistics as st
from buckets import rows,S,core
F=json.load(open('chartfeat_all.json'))
X=[{**r,**F[k]} for r in rows if (k:=f"{r['set']}|{r['tok']}|{r['date']}") in F and F[k]]
Rt=[r for r in X if not core(r)]   # routine unlocks: never used to find these signals
print('routine unlocks',S(Rt))
def show(lab,f,s=Rt):
    a=[r for r in s if f(r)]; b=[r for r in s if not f(r)]
    print(f'  {lab:<44} yes {S(a)}\n  {"":<44} no  {S(b)}')
ok=lambda r,k:r.get(k) is not None
show('OI fell 20%+ the week before',lambda r:ok(r,'oiChg') and r['oiChg']<=-20)
show('OI fell 10%+',lambda r:ok(r,'oiChg') and r['oiChg']<=-10)
show('OI fell 10%+ and price fell 5%+',lambda r:ok(r,'oiChg') and r['oiChg']<=-10 and (r['week'] or 0)<=-5)
show('more accounts short than long (ls<1)',lambda r:ok(r,'ls') and r['ls']<1)
show('price 0-10% above its 50-day avg',lambda r:ok(r,'aboveSma50') and 0<=r['aboveSma50']<10)
show('funding 0.2-0.3% over 7 days',lambda r:ok(r,'fund7') and 0.2<=r['fund7']<0.3)
show('funding negative (shorts paying)',lambda r:ok(r,'fund7') and r['fund7']<0)
show('pumped 30%+',lambda r:(r['pump'] or 0)>=30)
print('routine OI bands')
for a,b in [(-1e9,-30),(-30,-20),(-20,-10),(-10,0),(0,10),(10,1e9)]:
    print(f'   {a}..{b}',S([r for r in Rt if ok(r,'oiChg') and a<=r['oiChg']<b]))
