import sys, struct
from emu4 import *
img=open(sys.argv[1],'rb').read(); cave=BASE+28552
p=fresh(img,cave,0); p.run(4000); print("1. auto off (default): mode switches in 4 s:",p.switches)
p.ccr.clear(); r=p.hold(1,2700); p.run(400); print("2. mains key extra-long press:",r,"| mode",p.b(MODE),"| auto",p.st()['auto'],"| notes (ms, Hz):",[(b,c) for a,b,c,d in p.notes()])
p.switches.clear(); p.ccr.clear(); p.leds.clear(); t0=p.ms; p.run(6000)
print("3. no signal: switches (ms since on, new mode):",[(a-t0,m) for a,m in p.switches]); print("   sound while searching:",[(b,c) for a,b,c,d in p.notes()],"| LED writes per switch:",p.leds[:3])
p.sigmode=1; p.sigval=57; p.switches.clear(); t0=p.ms; p.run(5000); print("4. tester sending Analog only: switches",[(a-t0,m) for a,m in p.switches],"-> mode",p.b(MODE),"| beeping:",p.signal is not None)
p.sigmode=0; p.switches.clear(); p.ccr.clear(); t0=p.ms; p.run(5000); n=[x for x in p.notes() if x[1]>80]
print("5. tester changes to Digital: switches",[(a-t0,m) for a,m in p.switches],"-> mode",p.b(MODE),"| lost alarm played:",len(n)>0)
p.sigmode=None; p.signal=None; p.run(1500); p.switches.clear(); p.ccr.clear(); r=p.hold(0,120); p.run(500); print("6. mode key by hand while auto is on:",r,"-> announce notes",len([x for x in p.notes() if x[1]>=50]),"| then keeps searching:", end=" "); p.switches.clear(); p.run(3000); print(len(p.switches)>0)
p.hold(1,120); p.run(800); p.switches.clear(); p.run(4000); print("7. in Mains mode: switches",p.switches,"mode",p.b(MODE))
p.run(4000); page=bytes(p.mu.mem_read(0x0801E800,8)); print("8. saved page:",page.hex())
q=fresh(img,cave,0,saved=page+b"\xff"*0x7f8); print("   next power-on: auto",q.st()['auto']); q.switches.clear(); q.run(3000); print("   and it searches:",len(q.switches)>0)
r=q.hold(1,2700); q.run(500); q.switches.clear(); q.run(3000); print("9. extra-long press again: auto",q.st()['auto'],"switches",q.switches)
import random; random.seed(4)
p=fresh(img,cave,0); p.hold(1,2700)
for i in range(150):
    p.sigmode=random.choice([None,0,1]); p.sigval=random.choice([20,57,146]); 
    if p.sigmode is None: p.signal=None
    k=random.choice([0,1,2,None,None,None])
    if k is not None: p.hold(k,random.choice([60,120,900,2700]))
    p.run(random.choice([100,400,1300]))
print("10. 150 random steps with auto in play: ok; switches",len(p.switches),"flash writes",sum(1 for x in p.fl if x and x[0]=='erase'))
