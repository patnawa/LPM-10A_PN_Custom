import sys, struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
BASE=0x08006800; DISPATCH=0x0800AC50; END=0x0800AC7C; SKIP=0x08008354
T_MODE0=0x08007724; T_PLAIN=0x08007508; SETCCR=0x0800B364; DELAY=0x0800B9A0
MODE=0x20000048; KEEP=0x2000010C; GAP=0x2000005A; MS=0x200000FC; T40=0x20000100; HOLD=0x2000010E; BATT=0x2000004A; ST=0x20001800; STN=64
PEND=0x20000049
FL_UNLOCK,FL_ERASE,FL_WORD,FL_LOCK=0x08007BA8,0x080079D8,0x08007AF8,0x08007AE4
raw=lambda mv: round(mv*4096/6600)
class Probe:
    def __init__(s, img, cave, mv=3900, saved=None):
        mu=s.mu=Uc(UC_ARCH_ARM, UC_MODE_THUMB|UC_MODE_MCLASS)
        mu.mem_map(0x08000000,0x20000); mu.mem_map(0x20000000,0x8000); mu.mem_map(0x40000000,0x20000)
        mu.mem_write(BASE,img); mu.mem_write(0x0801E800, saved if saved is not None else b"\xff"*0x800); mu.mem_write(ST,b"\x5a"*STN); mu.mem_write(BATT, struct.pack("<5H",*[raw(mv)]*5))
        s.cave=cave; s.ccr=[]; s.old=[]; s.gpio=[]; s.t=0; s.ms=0; s.signal=None; s.lamp=0; s.lamp_toggles=0; s.delays=0; s.fl=[]; s.unlocked=False; s.leds=[]; s.switches=[]; s.sigmode=None; s.sigval=57
        def code(u,addr,size,_):
            if addr==SETCCR: s.ccr.append((s.t,u.reg_read(UC_ARM_REG_R0))); u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
            elif addr in (T_MODE0,T_PLAIN): s.old.append(s.t); u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
            elif addr==FL_UNLOCK: s.fl.append("unlock"); s.unlocked=True; u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
            elif addr==FL_LOCK: s.fl.append("lock"); s.unlocked=False; u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
            elif addr==FL_ERASE:
                a=u.reg_read(UC_ARM_REG_R0)&~0x7FF; assert s.unlocked and a==0x0801E800, hex(a); s.fl.append(("erase",hex(a),s.ms)); s.flash_writing=True; u.mem_write(a,b"\xff"*0x800); s.flash_writing=False
                u.reg_write(UC_ARM_REG_R0,6); u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
            elif addr==FL_WORD:
                a=u.reg_read(UC_ARM_REG_R0); v=u.reg_read(UC_ARM_REG_R1); assert s.unlocked and 0x0801E800<=a<0x0801F000 and bytes(u.mem_read(a,4))==b"\xff"*4; s.fl.append(("word",hex(a),hex(v)))
                u.mem_write(a,struct.pack("<I",v)); u.reg_write(UC_ARM_REG_R0,6); u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
            elif addr==DELAY: s.delays+=u.reg_read(UC_ARM_REG_R0); u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
        mu.hook_add(UC_HOOK_CODE,code)
        def wr(u,a,addr,size,val,d):
            if 0x40010800<=addr<0x40010900 and val&0x400:
                if addr&0xff==0x18: s.lamp=1
                elif addr&0xff==0x28: s.lamp=0
                s.gpio.append((s.t,s.lamp))
            elif 0x40010800<=addr<0x40011000: s.leds.append((s.ms,hex(addr),hex(val)))
            elif addr>=0x20000000 and not (ST<=addr<ST+STN or addr in (KEEP,PEND) or 0x20001500<=addr<0x20001600):
                raise AssertionError(f"stray RAM write {addr:#x}")
        mu.hook_add(UC_HOOK_MEM_WRITE,wr)
    def b(s,a): return s.mu.mem_read(a,1)[0]
    def wb(s,a,v): s.mu.mem_write(a,bytes([v]))
    def st(s):
        d=bytes(s.mu.mem_read(ST,STN)); k="prevk start parity off lmode vol theme peak_on peak armed ph mute".split()
        r=dict(zip(k,d[:12])); r["req"]=d[16]; r["accent"]=d[17]; r["seq"]=struct.unpack_from("<I",d,20)[0]; r["save_at"]=struct.unpack_from("<I",d,40)[0]; r["auto"]=d[52]; return r
    def call(s, entry, r0=0, r1=0, r5=0, stops=(0x08000000,), limit=4000):
        mu=s.mu; mu.reg_write(UC_ARM_REG_R0,r0); mu.reg_write(UC_ARM_REG_R1,r1); mu.reg_write(UC_ARM_REG_R5,r5)
        mu.reg_write(UC_ARM_REG_SP,0x20001600); mu.reg_write(UC_ARM_REG_LR,0x08000001)
        pc=entry
        for _ in range(limit):
            mu.emu_start(pc|1,0,count=1); pc=mu.reg_read(UC_ARM_REG_PC)
            if pc in stops or pc==SKIP: break
        assert mu.reg_read(UC_ARM_REG_SP)==0x20001600, "stack not balanced"
        return pc
    def boot(s):
        s.wb(MODE,1); s.mu.mem_write(T40,struct.pack("<I",s.t)); s.call(s.cave+4, r0=100); s.wb(KEEP,1)
    def tick(s, full=True):
        mu=s.mu
        if full or s.t%64==0:
            mu.reg_write(UC_ARM_REG_R0,s.t); mu.reg_write(UC_ARM_REG_SP,0x20001600); mu.reg_write(UC_ARM_REG_LR,0xDEAD0001)
            mu.emu_start(DISPATCH|1,END,count=3000); assert mu.reg_read(UC_ARM_REG_PC)==END, hex(mu.reg_read(UC_ARM_REG_PC))
            assert mu.reg_read(UC_ARM_REG_SP)==0x20001600
        s.t+=1
        if s.t%40==0:
            s.ms+=1; mu.mem_write(MS, struct.pack("<II",s.ms,s.t))
            if s.b(PEND): s.switches.append((s.ms,s.b(PEND)-1)); s.wb(MODE,s.b(PEND)-1); s.wb(PEND,0)     # the main loop applies a mode request
            if s.sigmode is not None: s.signal = s.sigval if s.b(MODE)==s.sigmode else None
            k=s.b(KEEP)
            if k: s.wb(KEEP,k-1)
            elif s.b(GAP): s.wb(GAP,s.b(GAP)-1)
            elif s.signal is not None and s.b(MODE)!=2: s.wb(GAP,s.signal); s.wb(KEEP,30)
    def run(s,ms,full=True):
        for _ in range(ms*40): s.tick(full)
    def hold(s,key,ms):
        """press a key for ms, then release it the way the firmware's key scan does"""
        n=0
        for i in range(ms):
            if i%5==0: n+=1; s.mu.mem_write(HOLD+2*key, struct.pack("<H",n))
            s.run(1)
        s.mu.mem_write(HOLD+2*key, struct.pack("<H",0))
        pc=s.call(s.cave+8, r1=n, r5=key)
        if pc==SKIP: return "handled"
        if key==2: s.lamp_toggles+=1
        elif key==1: s.wb(MODE,2)
        else: s.wb(MODE,0 if s.b(MODE)==1 else 1)
        s.wb(KEEP,100); return "stock"
    def notes(s,t0=0,t1=None):
        """sound as [(start ms, length ms, Hz, amplitude)] from the speaker duty writes"""
        ev=[(t,v) for t,v in s.ccr if t>=t0 and (t1 is None or t<t1) and v!=800]; out=[]; i=0
        while i<len(ev):
            j=i
            while j+1<len(ev) and ev[j+1][0]-ev[j][0]<=40 and abs((ev[j+1][0]-ev[j][0])-(ev[i+1][0]-ev[i][0] if i+1<len(ev) else 0))<=1: j+=1
            if j>i:
                gap=(ev[j][0]-ev[i][0])/(j-i); out.append((round(ev[i][0]/40), round((ev[j][0]-ev[i][0]+gap)/40), round(20000/gap), abs(ev[i][1]-800)))
            i=j+1
        return out
def sweep(p,t0,t1):
    ev=[t for t,v in p.ccr if t0<=t<t1 and v!=800]; g=[b-a for a,b in zip(ev,ev[1:])]
    return (round(20000/g[0]), round(20000/g[-1]), len(ev)) if g else (None,None,len(ev))
def fresh(img,cave,mode=0,mv=3900,settle=2300,saved=None):
    p=Probe(img,cave,mv,saved); p.boot(); p.run(240); p.wb(MODE,0); p.run(settle-240); p.wb(MODE,mode); p.run(300); p.ccr.clear(); p.old.clear(); return p
def pulses(p,n):
    out=[]; start=None; guard=0
    while len(out)<n and guard<4000:
        kb=p.b(KEEP); p.run(1); ka=p.b(KEEP); guard+=1
        if kb==0 and ka==30: start=p.t
        if kb==1 and ka==0 and start: out.append((start,p.t)); start=None
    return out
if __name__=="__main__":
    img=open(sys.argv[1],'rb').read(); cave=BASE+28552
    p=Probe(img,cave,4100); p.boot(); print("1. boot: delay asked of the firmware",p.delays,"ms; state",{k:v for k,v in p.st().items() if k in("peak","lmode","vol","theme")})
    p.run(240); p.wb(MODE,0); p.run(2600)
    print("   power-on tune + battery (4.10 V):",[(a,b,c) for a,b,c,d in p.notes()])
    for mv in (3650,3750,3900):
        q=Probe(img,cave,mv); q.boot(); q.run(240); q.wb(MODE,0); q.run(2600); print(f"   {mv} mV -> battery blips:",len([n for n in q.notes() if n[0]>=1250]))
    print("2. tracing, waka theme (first two pulses, Hz at start -> end):")
    for mode,name in ((0,"Digital"),(1,"Analog")):
        for g in (20,57,146):
            p=fresh(img,cave,mode); p.signal=g; pl=pulses(p,2); o=[sweep(p,a,b) for a,b in pl]
            print(f"   {name} gap {g:3d}: {o[0][0]}->{o[0][1]}, {o[1][0]}->{o[1][1]} | strength step {p.st()['off']} | lamp writes {len(p.gpio)}")
    p=fresh(img,cave,0); p.signal=57
    print("3. mode key short press:",p.hold(0,120),"-> mode",p.b(MODE)); p.ccr.clear(); p.signal=None; p.run(700); print("   announce:",[(b,c) for a,b,c,d in p.notes()])
    p.ccr.clear(); print("   mains key short press:",p.hold(1,120),"-> mode",p.b(MODE)); p.run(900); print("   announce:",[(b,c) for a,b,c,d in p.notes()])
    p.ccr.clear(); print("   mode key short press:",p.hold(0,120),"-> mode",p.b(MODE)); p.run(700); print("   announce:",[(b,c) for a,b,c,d in p.notes()])
    p=fresh(img,cave,0)
    for i in range(3):
        p.ccr.clear(); r=p.hold(0,1000); p.run(400); print(f"4. mode key long press: {r}, mode stays {p.b(MODE)}, volume {p.st()['vol']}, sounds (ms, Hz, amplitude):",[(b,c,d) for a,b,c,d in p.notes()])
    p.hold(0,1000); p.hold(0,1000); p.run(300); p.signal=57; p.ccr.clear(); pl=pulses(p,1); print("   tracing pulse at volume 2: amplitude",{abs(v-800) for t,v in p.ccr if v!=800})
    p.ccr.clear(); p.wb(KEEP,100); p.run(120); print("   key beep at volume 2: (ms, Hz, amplitude)",[(b,c,d) for a,b,c,d in p.notes()])
    p=fresh(img,cave,0)
    for i in range(3):
        p.ccr.clear(); r=p.hold(0,2700); p.run(500); th=p.st()['theme']; n=p.notes(); p.signal=57; p.ccr.clear(); pl=pulses(p,2); o=[sweep(p,a,b) for a,b in pl]; p.signal=None; p.run(300)
        print(f"5. mode key extra-long press: {r}, theme {th}, mode {p.b(MODE)}; feedback+sample notes {len(n)}; pulses {o}")
    p=fresh(img,cave,0); p.ccr.clear(); r=p.hold(1,1000); p.run(300); print("6. mains key long press:",r,"mode",p.b(MODE),"peak hold",p.st()['peak_on'],[(b,c) for a,b,c,d in p.notes()])
    for g,label in ((71,"first cable"),(36,"stronger cable"),(71,"back on the first"),(57,"one step below the best"),(146,"weak bleed")):
        p.signal=g; p.run(250); p.ccr.clear(); pl=pulses(p,2); o=[sweep(p,a,b) for a,b in pl]; s_=p.st()
        print(f"   {label:24s} gap {g:3d} step {s_['off']} best {s_['peak']}: pulses {o} muted {s_['mute']}")
    p.signal=None; p.run(1500); p.ccr.clear(); p.hold(1,1000); p.run(300); print("   long press again: peak hold",p.st()['peak_on'],[(b,c) for a,b,c,d in p.notes()])
    p=fresh(img,cave,0); p.signal=36; p.run(900); p.ccr.clear(); t0=p.ms; p.signal=None; p.run(1200); n=[x for x in p.notes() if x[1]>40]
    print("7. strong signal vanishes: alarm notes (ms after loss, ms, Hz):",[(a-t0,b,c) for a,b,c,d in n])
    p=fresh(img,cave,0); p.signal=123; p.run(900); p.ccr.clear(); p.signal=None; p.run(1200); print("   weak signal vanishes: notes over 40 ms:",len([x for x in p.notes() if x[1]>40]))
    p=fresh(img,cave,0); p.signal=57
    print("8. lamp key short press:",p.hold(2,120),"flashlight toggles",p.lamp_toggles)
    for i in range(4):
        p.ccr.clear(); r=p.hold(2,1000); p.run(700); nb=len(p.notes()); lm=p.st()['lmode']; p.ccr.clear(); p.gpio.clear(); p.signal=57; pl=pulses(p,3)
        on=sum(1 for t,v in p.gpio if v); snd=len([1 for t,v in p.ccr if v!=800]); edges=sum(1 for a,b in zip(p.gpio,p.gpio[1:]) if a[1]!=b[1]); dur=(p.gpio[-1][0]-p.gpio[0][0])/40000 if len(p.gpio)>1 else 0
        print(f"   long press: {r} -> lamp mode {lm}, blips+feedback {nb}; during 3 pulses: speaker flips {snd}, lamp edges {edges} in {dur:.2f} s; short press: {p.hold(2,120)}")
    p=fresh(img,cave,2); p.wb(KEEP,100); p.ccr.clear(); p.run(120); print("9. mains mode 100 ms beep: (ms, Hz, amplitude)",[(b,c,d) for a,b,c,d in p.notes()], "old-helper calls",len(p.old))
    for mode in (0,1):
        p=fresh(img,cave,mode); p.wb(KEEP,100); p.ccr.clear(); p.run(120); print(f"   mode {mode} 100 ms key beep:",[(b,c,d) for a,b,c,d in p.notes()])
    p=fresh(img,cave,0,mv=3500); p.ccr.clear(); p.run(61000,full=False); p.run(400); print("10. battery 3.50 V after a minute:",[(b,c) for a,b,c,d in p.notes()])
    p=fresh(img,cave,0,mv=3900); p.ccr.clear(); p.run(61000,full=False); p.run(400); print("    battery 3.90 V after a minute:",p.notes())
    p.ccr.clear(); p.run(120000,full=False); p.run(300); print("11. idle for 3 minutes:",[(b,c) for a,b,c,d in p.notes()])
    print("12. auto-off constant:", struct.unpack_from("<I", img, 0x0800A9CC-BASE)[0], "ms")
