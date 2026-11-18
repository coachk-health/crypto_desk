import json,sys,io,zipfile,csv,urllib.request,urllib.error,statistics as st
from datetime import date,timedelta,datetime,timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0,'/home/claude/crypto_desk/scripts'); import candles
from buckets import rows
BASE="https://data.binance.vision/data/futures/um"
C=Path('/home/claude/work/dl')
def get(url,name):
    f=C/name
    if f.exists(): b=f.read_bytes(); return b or None
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"coachk-crypto-desk/1.0"}),timeout=40) as r: b=r.read()
    except urllib.error.HTTPError as e:
        b=b"" if e.code==404 else None
        if b is None: return None
    f.write_bytes(b); return b or None
def unzip_rows(b):
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        return [r for n in z.namelist() for r in csv.reader(io.TextIOWrapper(z.open(n)))]
def funding(sym,d0):
    out={}
    for m in {(d0+timedelta(days=k)).strftime('%Y-%m') for k in (-30,-8)}:
        b=get(f"{BASE}/monthly/fundingRate/{sym}/{sym}-fundingRate-{m}.zip",f"fr-{sym}-{m}.zip")
        if not b: continue
        for r in unzip_rows(b):
            if r and r[0].isdigit():
                d=datetime.fromtimestamp(int(r[0])/1000,timezone.utc).date(); out.setdefault(d,[]).append(float(r[2])*100)
    return out
def metrics(sym,d):
    b=get(f"{BASE}/daily/metrics/{sym}/{sym}-metrics-{d}.zip",f"m-{sym}-{d}.zip")
    if not b: return None
    rs=[r for r in unzip_rows(b) if r and r[0][:2]=='20']
    def f(x):
        try: return float(x)
        except: return None
    oi=[f(r[3]) for r in rs if f(r[3])]; ls=[f(r[6]) for r in rs if f(r[6])]; tk=[f(r[7]) for r in rs if f(r[7])]; top=[f(r[5]) for r in rs if f(r[5])]
    return dict(oi=oi[-1] if oi else None, ls=st.mean(ls) if ls else None, taker=st.mean(tk) if tk else None, top=st.mean(top) if top else None)
def feat(r):
    d0=date.fromisoformat(r['date'])
    try:
        src,sym0,days=candles.token_days(r['tok'],d0-timedelta(days=95),d0+timedelta(days=15))
    except Exception as e:
        return None
    if not src: return None
    b={(date.fromisoformat(k)-d0).days:v for k,v in days.items()}
    need=range(-60,-7)
    if any(k not in b for k in range(-30,-7)): return None
    c=lambda k:b[k]['c']
    cl=[b[k]['c'] for k in range(-60,-7) if k in b]
    P=b[-7]['o']
    sma=lambda n:st.mean([b[k]['c'] for k in range(-7-n,-7) if k in b])
    hi60=max(b[k]['h'] for k in range(-60,-7) if k in b); lo60=min(b[k]['l'] for k in range(-60,-7) if k in b)
    atr=st.mean([(b[k]['h']-b[k]['l'])/b[k]['c']*100 for k in range(-21,-7)])
    qv=lambda a,z:[b[k]['qv'] for k in range(a,z) if k in b and b[k]['qv']]
    v1,v0=qv(-14,-7),qv(-42,-14)
    upday=max((b[k]['c']/b[k-1]['c']-1)*100 for k in range(-13,-7) if k-1 in b)
    red=sum(b[k]['c']<b[k]['o'] for k in range(-14,-7))
    o=dict(hist=len(cl),aboveSma20=(P/sma(20)-1)*100,aboveSma50=(P/sma(50)-1)*100 if len(cl)>=45 else None,
           fromHigh60=(P/hi60-1)*100,fromLow60=(P/lo60-1)*100,atr=atr,
           volRatio=(st.mean(v1)/st.mean(v0)) if v1 and v0 else None,bigUpDay=upday,redDays=red,src=src)
    if src=='binance-futures':
        sym=sym0
        fr=funding(sym,d0)
        w=[x for k in range(-14,-7) for x in fr.get(d0+timedelta(days=k),[])]
        o['fund7']=sum(w) if w else None  # % paid by longs over the 7 days before entry
        m8,m15=metrics(sym,d0-timedelta(days=8)),metrics(sym,d0-timedelta(days=15))
        if m8 and m15 and m8['oi'] and m15['oi']:
            o['oiChg']=(m8['oi']/m15['oi']-1)*100; o['ls']=m8['ls']; o['taker']=m8['taker']; o['top']=m8['top']
    return o
if __name__=='__main__':
    todo=rows if len(sys.argv)<2 else [r for r in rows if r['first'] or (r['pct'] or 0)>=25]
    out={}
    with ThreadPoolExecutor(12) as ex:
        for r,f in zip(todo,ex.map(feat,todo)):
            out[f"{r['set']}|{r['tok']}|{r['date']}"]=f
    json.dump(out,open('chartfeat_'+('core' if len(sys.argv)>1 else 'all')+'.json','w'))
    print(len(out),sum(1 for v in out.values() if v),sum(1 for v in out.values() if v and v.get('fund7') is not None),sum(1 for v in out.values() if v and v.get('oiChg') is not None))
