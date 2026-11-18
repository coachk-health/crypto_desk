import json,sys,random,statistics as st,collections
sys.path.insert(0,'/home/claude/crypto_desk/scripts'); import levels
R='/home/claude/crypto_desk/'
bt=json.load(open(R+'data/backtest.json'))
bad={tuple(x) for x in json.load(open(R+'research/bad.json'))}
def mv(p,a,b):
    if p.get(str(a)) is None or p.get(str(b)) is None: return None
    return ((1+p[str(b)]/100)/(1+p[str(a)]/100)-1)*100
def sim(e,stop=12,tgt=35,cov=14):
    b={int(d):tuple(1+x/100 for x in v) for d,v in e['ohlc'].items()}
    if any(d not in b for d in range(-7,cov+1)): return None
    return levels.sim(b,'market',0,stop,tgt,cov)
def who(m):
    if not m: return 'unknown'
    t=sum(v or 0 for v in m.values()) or 1
    f={k:(v or 0)/t for k,v in m.items()}
    if f.get('team',0)>=.5: return 'team'
    if f.get('investors',0)>=.5: return 'investors'
    if f.get('community',0)+f.get('ecosystem',0)>=.5: return 'community/fund'
    if f.get('team',0)+f.get('investors',0)>=.5: return 'team+investors'
    return 'mixed'
rows=[]
evs=sorted(bt['events'],key=lambda e:(e['token'],e['date']))
hist=collections.defaultdict(list)
for e in evs:
    if not e.get('ohlc') or (e['token'],e['date']) in bad: continue
    r=sim(e); r2=sim(e,12,45,30)
    if not r: continue
    p=e['pathUsd']
    prev=hist[e['token']]
    row=dict(set='build',tok=e['token'],date=e['date'],R=r['r'],why=r['why'],R45=(r2 or {}).get('r'),
       pct=e.get('pctCirculating'),first=bool(e.get('firstInsiderUnlock')),type=e.get('type'),shape=e.get('shape'),
       who=who(e.get('recipientsMix')),adv=e.get('advDays'),usdM=e.get('usdM'),
       pump=mv(p,-30,-7),week=mv(p,-14,-7),after=mv(p,-7,14),
       prevN=len(prev),prevAvg=(st.mean(prev) if prev else None))
    rows.append(row)
    a=mv(p,-7,14)
    if a is not None: hist[e['token']].append(a)
# unseen 2023-25 (re-checked, strict)
ft=json.load(open(R+'data/frozen_test.json'))
mix={}
import glob
for f in glob.glob('/home/claude/work/oos/out*.json'):
    for t in json.load(open(f)):
        for e in t.get('events') or []: mix[(t['token'],e['date'])]=e.get('recipientsMix')
for t in ft['trades']:
    rows.append(dict(set='unseen',tok=t['token'],date=t['date'],R=t['v1']['R'],why=t['v1']['why'],R45=t['frozen']['R'],
       pct=t['pct'],first=t['first'],type=None,shape=t.get('shape'),who=who(mix.get((t['token'],t['date']))) if isinstance(mix.get((t['token'],t['date'])),dict) else 'unknown',
       adv=None,usdM=None,pump=t['pump'],week=t['week'],after=None,prevN=0,prevAvg=None))
core=lambda r:r['first'] or (r['pct'] or 0)>=25
def bucket(r):
    if r['pump'] is not None and r['pump']>=30: return 'SKIP','pumped 30%+ into the unlock'
    if not core(r): return 'SKIP','routine unlock (not first insider, under 25%)'
    w=r['week']
    if w is None: return 'SKIP','no price history'
    if -5<w<5: return 'SKIP','flat the week before (someone absorbing it)'
    if w>=5: return 'MAYBE','big/first unlock but rising into it'
    if w<=-20: return 'MAYBE','big/first unlock, already crashed 20%+ that week'
    return 'TAKE','big/first unlock, already sliding 5-20%'
for r in rows: r['bucket'],r['reason']=bucket(r)
json.dump(rows,open('rows.json','w'))
def S(s,key='R'):
    s=[r for r in s if r.get(key) is not None]
    if not s: return '—'
    v=[r[key] for r in s]
    return f"n={len(v):>3} win={round(100*sum(x>0 for x in v)/len(v)):>3}% avg={st.mean(v):+.2f}R total={sum(v):+6.1f}R"
if __name__=='__main__':
    for setn in ('build','unseen'):
        print('=====',setn)
        X=[r for r in rows if r['set']==setn]
        print('  ALL', S(X))
        for b in ('TAKE','MAYBE','SKIP'):
            print(' ',b, S([r for r in X if r['bucket']==b]))
            for why in sorted({r['reason'] for r in X if r['bucket']==b}):
                print('     ',f"{why:<50}",S([r for r in X if r['reason']==why]))
