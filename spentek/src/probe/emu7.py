import sys, struct
from emu4 import *
img=open(sys.argv[1],'rb').read(); cave=BASE+28552
def alarm(p): return [(a,b,c) for a,b,c,d in p.notes() if b>80 and c<2600]
p=fresh(img,cave,0); p.hold(1,2700); p.run(500); p.sigmode=0; p.sigval=36; p.run(3000)
print("1. auto on, locked on Digital: mode",p.b(MODE),"beeping",p.signal is not None)
p.sigmode=1; p.ccr.clear(); p.switches.clear(); t0=p.ms; p.run(4000)
print("   tester changes to Analog: switches (ms after)",[(a-t0,m) for a,m in p.switches],"-> mode",p.b(MODE),"beeping",p.signal is not None,"| alarm notes",alarm(p))
p.sigmode=None; p.signal=None; p.ccr.clear(); p.switches.clear(); t0=p.ms; p.run(5000)
print("2. signal really gone: switches",[(a-t0,m) for a,m in p.switches],"| alarm (ms after loss, ms, Hz)",[(a-t0,b,c) for a,b,c in alarm(p)])
p.ccr.clear(); p.run(6000); print("   no repeat alarm while it keeps searching:",alarm(p)==[])
p=fresh(img,cave,0); p.signal=36; p.run(1500); p.signal=None; p.ccr.clear(); t0=p.ms; p.run(2500)
print("3. auto off: alarm (ms after loss)",[a-t0 for a,b,c in alarm(p)][:1],"switches",p.switches)
p=fresh(img,cave,0); p.hold(1,2700); p.hold(2,1000); p.hold(2,1000); p.run(800); p.sigmode=0; p.sigval=36; p.run(3000); p.sigmode=None; p.signal=None; p.ccr.clear(); p.run(5000)
print("4. auto on + silent lamp mode",p.st()['lmode'],": notes after loss",len(p.notes()))
import random; random.seed(9)
p=fresh(img,cave,0); p.hold(1,2700)
for i in range(150):
    p.sigmode=random.choice([None,0,1]); p.sigval=random.choice([20,36,57,146])
    if p.sigmode is None: p.signal=None
    k=random.choice([0,1,2,None,None,None])
    if k is not None: p.hold(k,random.choice([60,120,900,2700]))
    p.run(random.choice([100,400,1300]))
print("5. 150 random steps: ok")
