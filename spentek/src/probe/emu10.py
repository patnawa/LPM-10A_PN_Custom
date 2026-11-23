import sys, struct
from emu4 import *
img=open(sys.argv[1],'rb').read(); cave=BASE+28552
names=["waka","beeps","geiger","sonar","laser","rise","two-tone","trill","detector","heartbeat","cricket","telegraph","arpeggio","siren"]
def shape(p,a,b):
    ev=[(t,v) for t,v in p.ccr if a<=t<b and v!=800]; g=[y[0]-x[0] for x,y in zip(ev,ev[1:])]
    if not g: return "silent"
    amps=[abs(v-800) for t,v in ev]; third=max(1,len(g)//3)
    f=lambda gs: round(20000/(sum(gs)/len(gs)))
    return f"{f(g[:third])} -> {f(g[third:2*third] or g)} -> {f(g[-third:])} Hz over {round((ev[-1][0]-ev[0][0])/40)} ms, amplitude {amps[0]} -> {amps[-1]}"
p=fresh(img,cave,0)
for i in range(15):
    th=p.st()['theme']; p.signal=36; p.run(200); p.ccr.clear(); pl=pulses(p,2); a=shape(p,*pl[0]); b=shape(p,*pl[1])
    p.signal=146; p.run(400); p.ccr.clear(); pw=pulses(p,1); w=shape(p,*pw[0]); p.signal=None; p.run(400)
    print(f"theme {th} {names[th]:8s} strong: {a}" + ("" if a==b else f" | next pulse: {b}")); print(f"                   weak:   {w}")
    p.ccr.clear(); r=p.hold(0,2700); p.run(600); n=[(b_,c) for a_,b_,c,d in p.notes()]
    print(f"   extra-long press -> theme {p.st()['theme']}, sample notes {n[2:]}")
p.run(4000); page=bytes(p.mu.mem_read(0x0801E800,8)); print("saved page",page.hex())
for th in (13,14):
    q=fresh(img,cave,0,saved=b"\x31\x4b\x50\x53"+bytes([0,th,0,0])+b"\xff"*0x7f8); print(f"stored theme {th} -> restored as",q.st()['theme'])
p=fresh(img,cave,0); p.ccr.clear(); r=p.hold(0,2700+3200); p.run(500); print("mode key held 5.9 s:",r,"-> theme",p.st()['theme'],"mode",p.b(MODE)); p.run(4000); print("   saved theme",bytes(p.mu.mem_read(0x0801E805,1))[0])
p=fresh(img,cave,1); p.hold(0,120); p.run(600)
for i in range(3): p.hold(0,2700); p.run(500)
p.wb(MODE,1); p.run(600); p.signal=57; p.run(300); p.ccr.clear(); pl=pulses(p,1); print("analog mode, theme",p.st()['theme'],":",shape(p,*pl[0]))
