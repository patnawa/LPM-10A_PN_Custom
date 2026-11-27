import sys, struct
sys.path.insert(0,"/home/claude/repo/LPM-10A/Firmware File/sdk")
from thai import engine as E, mockup as M
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1
from PIL import Image
KEY=0x0800D2B4; UPK,DOWNK,LEFTK,RIGHTK,OKH,BACK=2,3,4,5,6,7; SL,SR,SOK=30,31,32; ST=0x2000FE40; SYS=0x2000013C
par,new=sys.argv[1:3]
flat=lambda s:[v for row in s.fb for v in row]
def scene(path):
    s=E.Scene(image=path, lang=1)
    s.regs={1:0x7949,0x11:0,5:0,10:0,0:0x1140}; s.writes=[]
    def rd(uc): s.ret(s.regs.get(uc.reg_read(UC_ARM_REG_R0),0)); return True
    def wr(uc): s.writes.append((uc.reg_read(UC_ARM_REG_R0),uc.reg_read(UC_ARM_REG_R1))); s.ret(0); return True
    s.at[0x080178F0]=rd; s.at[0x08017AFC]=wr
    s.uc.mem_write(ST, bytes([0x77,0x55,0x33,0x99,0xEE,0xEE,0,0,0xEE,0xEE,0xEE,0xEE]))
    return s
def home(path, sel):
    s=scene(path); M.sc_home(s, sel); return s
def key(s,k):
    s.call(KEY,k); posted=[m for m,_ in s.msgs]; s.drain(); return posted
sysb=lambda s: tuple(s.uc.mem_read(SYS,4))            # state, sel, item, sub
stb=lambda s: struct.unpack("<BBBB", s.uc.mem_read(ST,4))
texts=lambda s:[t for k,t,x,y,fg,ex in s.log if k=='ascii']
# A. stock pages: only the dot row changes
for sel in (4,9):
    a,b=home(par,sel),home(new,sel)
    d=[(x,y) for y in range(320) for x in range(240) if a.fb[y][x]!=b.fb[y][x]]
    print(f"A. home sel {sel}: {len(d)} px differ, bbox", (min(x for x,y in d),min(y for x,y in d),max(x for x,y in d),max(y for x,y in d)) if d else None)
# B. navigation table
names={4:"CableTest",5:"SCAN",6:"FLASH",7:"Length",8:"QC",9:"SPEED",10:"POE",11:"SETTING",12:"Pinout",13:"Link"}
print("B. navigation (sel -> UP, DOWN, LEFT, RIGHT):")
ok=True
for sel in range(4,14):
    row=[]
    for k in (UPK,DOWNK,LEFTK,RIGHTK):
        s=home(new,sel); key(s,k); row.append(sysb(s)[1])
    prow=None
    if sel<12:
        prow=[]
        for k in (UPK,DOWNK,LEFTK,RIGHTK):
            s=home(par,sel); key(s,k); prow.append(sysb(s)[1])
    print(f"   {names[sel]:9s} -> {[names.get(v,v) for v in row]}" + ("" if prow is None or prow==row else f"   (was {[names.get(v,v) for v in prow]})"))
    ok &= all(4<=v<=13 for v in row)
print("   every move lands on a real tile:", ok)
# C. page 3 renders
shots=[]
for sel in (12,13):
    s=home(new,sel); shots.append(s.image(1)); print(f"C. home sel {sel}: text", texts(s))
# D. open tools, switch, back
s=home(new,12); posted=key(s,OKH); print("D. OK on Pinout tile: msgs",[hex(m) for m in posted],"state/sel/item/sub",sysb(s),"page/full/..",stb(s)); shots.append(s.image(1)); print("   header+title:", texts(s)[-40:][:3] if False else [t for t in texts(s) if t in ("TOOLS  ","Pinout","SETTING")][-3:])
key(s,SR); print("   RIGHT -> page", stb(s)[0], [t for t in texts(s)][-9:-5]); shots.append(s.image(1))
key(s,SR); print("   RIGHT -> page", stb(s)[0]); key(s,SL); print("   LEFT  -> page", stb(s)[0])
a=key(s,SOK); print("   OK on Link: msgs",a,"sub",sysb(s)[3])
posted=key(s,BACK); print("   BACK -> msgs",[hex(m) for m in posted],"state/sel/item/sub",sysb(s),"page",stb(s)[0]); shots.append(s.image(1))
s2=home(new,12); print("   that screen equals a fresh home drawn at the Pinout tile:", flat(s)==flat(s2))
# E. Settings > About untouched
def about(path):
    s=scene(path); s.w8(SYS+2,5); s.w8(SYS+3,0); s.set_state(11); s.post(0x32); s.drain(); key(s,SOK); return s
p,n=about(par),about(new)
print("E. About: px differing from parent", sum(x!=y for x,y in zip(flat(p),flat(n))), "| LEFT/RIGHT msgs", key(n,SL), key(n,SR), "page", stb(n)[0])
a,b=key(p,SOK),key(n,SOK); print("   OK -> parent",[hex(m) for m in a],"new",[hex(m) for m in b],"sub",sysb(n)[3])
p,n=about(par),about(new); a,b=key(p,BACK),key(n,BACK); print("   BACK from About -> parent",[hex(m) for m in a],sysb(p),"new",[hex(m) for m in b],sysb(n))
a,b=key(p,BACK),key(n,BACK); print("   BACK from list  -> parent",[hex(m) for m in a],sysb(p)[0],"new",[hex(m) for m in b],sysb(n)[0])
# F. stock tiles still launch
for sel in (4,7,9,11):
    a,b=home(par,sel),home(new,sel); ma,mb=key(a,OKH),key(b,OKH)
    print(f"F. OK on {names[sel]}: parent state {sysb(a)[0]} msgs {[hex(m) for m in ma][:4]} | new state {sysb(b)[0]} msgs {[hex(m) for m in mb][:4]}")
sheet=Image.new("RGB",(250*len(shots)-10,320),(60,60,60))
for i,im in enumerate(shots): sheet.paste(im,(250*i,0))
sheet.save("out/home3.png")
