import sys, struct
from emu4 import *
img=open(sys.argv[1],'rb').read(); cave=BASE+28552
p=fresh(img,cave,0); p.ccr.clear(); r=p.hold2(0,2,1300); p.run(600)
print("1. Mode + Lamp held 1.3 s:",r,"| locked",p.st()['locked'],"| mode",p.b(MODE),"lamp mode",p.st()['lmode'],"vol",p.st()['vol'],"| notes (ms, Hz):",[(b,c) for a,b,c,d in p.notes()])
for key,name in ((0,"mode"),(1,"mains"),(2,"lamp")):
    p.ccr.clear(); r=p.hold(key,120); p.run(300); print(f"   locked, {name} key short press: {r}, mode {p.b(MODE)}, flashlight toggles {p.lamp_toggles}, notes {[(b,c) for a,b,c,d in p.notes()]}")
p.ccr.clear(); r=p.hold(0,1000); p.run(400); print("   locked, mode key long press:",r,"vol",p.st()['vol'],"notes",[(b,c) for a,b,c,d in p.notes()])
p.signal=57; p.ccr.clear(); p.run(600); print("   tracing still sounds while locked:",len(p.notes())>0); p.signal=None; p.run(500)
p.ccr.clear(); r=p.hold2(0,2,1300); p.run(600); print("2. same gesture again:",r,"| locked",p.st()['locked'],"| notes",[(b,c) for a,b,c,d in p.notes()])
r=p.hold(0,120); p.run(400); print("   mode key now:",r,"mode",p.b(MODE))
p=fresh(img,cave,0); r=p.hold2(0,2,600); p.run(400); print("3. both keys for only 0.6 s:",r,"locked",p.st()['locked'],"mode",p.b(MODE),"flashlight toggles",p.lamp_toggles)
p=fresh(img,cave,0); p.hold2(0,2,1300); p.run(4500); print("4. lock is not saved: flash writes",p.fl)
