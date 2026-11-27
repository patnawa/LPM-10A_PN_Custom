import sys, struct
from emu4 import *
img=open(sys.argv[1],'rb').read(); cave=BASE+28552
p=fresh(img,cave,0); print("1. blank flash page: defaults",{k:v for k,v in p.st().items() if k in("lmode","vol","theme")},"flash activity",p.fl)
p.hold(0,1000); p.run(1500); print("2. volume changed; 1.5 s later: flash activity",p.fl)
p.hold(0,2700); p.run(2000); print("   theme changed too; 2 s after that:",p.fl)
p.run(1500); print("   3 s after the last change:",p.fl, "| page:",bytes(p.mu.mem_read(0x0801E800,8)).hex())
n=len(p.fl); p.run(5000); print("   no further writes while idle:",len(p.fl)==n)
p.hold(2,1000); p.hold(2,1000); p.run(4500); print("3. lamp mode 2 saved:",[x for x in p.fl[n:] if x[0]=="word"])
page=bytes(p.mu.mem_read(0x0801E800,0x800))
q=fresh(img,cave,0,saved=page); print("4. next power-on restores",{k:v for k,v in q.st().items() if k in("lmode","vol","theme")},"with no write:",q.fl==[])
q.hold(2,1000); q.run(4500); print("   strobe (lamp mode",q.st()['lmode'],") is stored as lamp mode",bytes(q.mu.mem_read(0x0801E806,1))[0])
q.hold(1,1000); m=len(q.fl); q.run(4500); print("5. peak hold toggle causes no write:",len(q.fl)==m)
q=fresh(img,cave,0); q.signal=57; q.hold(0,1000); q.run(6000); print("6. while a signal is beeping the write waits:",q.fl==[], "| pending",q.st()['save_at']>0); q.signal=None; q.run(1500); print("   and happens once it is quiet:",[x[0] for x in q.fl if not isinstance(x,str)])
for bad in (b"\x31\x4b\x50\x53\x09\x07\x05\x00", b"\x00"*8, b"\x31\x4b\x50\x53\xff\xff\xff\xff"):
    q=fresh(img,cave,0,saved=bad+b"\xff"*(0x800-8)); print("7. odd page",bad.hex(),"->",{k:v for k,v in q.st().items() if k in("lmode","vol","theme")})
