import sys, struct, random
img=sys.argv[1] if len(sys.argv)>1 else "out/LPM-10A-TX_PN2.35B-themes.bin"
sys.argv=[sys.argv[0],"/home/claude/theme/out/LPM-10A-TX_PN2.34C-cyber.bin",img]
exec(open("/home/claude/apps/check_apps3.py").read().split("# A. stock pages")[0])
del E.STUB_RET0[0x0800A3B8]
sys.path.insert(0,"/home/claude/theme")
import build_cyber as BC
from unicorn.arm_const import *
THM=0x20000C78+0xC6
def lum(c):
    r,g,b=c>>11,(c>>5)&63,c&31
    if r-b>=8: return None
    t=max(2*max(r,b),g)-14
    if t<0: t=0
    return t+(t>>2)
import build_apps6 as A6
def model(th,c):
    if th>=len(A6.THEMES): th=0
    n,mr,mg,mb,k=A6.THEMES[th]
    if k==2: return c
    if k==3: return c^0xFFFF
    if k==1: return BC.theme(c)
    t=lum(c)
    if t is None: return c
    return ((t*mr>>6)<<11)|((t*mg>>6)<<5)|(t*mb>>6)
def themed(s,th):
    im=Image.new("RGB",(240,320)); px=im.load()
    for y in range(320):
        for x in range(240):
            c=model(th,s.fb[y][x]); px[x,y]=(((c>>11)&31)*255//31,((c>>5)&63)*255//63,(c&31)*255//31)
    return im
# 1. the pixel routine against the model
s=scene(new); random.seed(3); cols=[0,0xFFFF,0x2105,0x31A7,0x7304,0xFE60,0x07E0,0x001F,0xF800,0xFD20,0x8410]+[random.randrange(65536) for _ in range(600)]
for th in list(range(12))+[12,255]:
    s.w8(THM,th); bad=0
    for c in cols:
        s.uc.reg_write(UC_ARM_REG_R3,0x1234ABCD)
        r=s.call(0x0806B310,c|0xABCD0000)&0xFFFF
        if r!=model(th,c) or s.uc.reg_read(UC_ARM_REG_R3)!=0x1234ABCD: bad+=1
    print(f"theme byte {th}: {len(cols)} colours, mismatches {bad}")
# 2. settings list
def settings(path,item=1,th=0):
    s=scene(path); s.w8(THM,th); s.w8(SYS+2,item); s.w8(SYS+3,0); s.set_state(11); s.post(0x32); s.drain(); return s
p,n=settings(par),settings(new)
d=[(x,y) for y in range(320) for x in range(240) if p.fb[y][x]!=n.fb[y][x]]
print("page 1 vs parent: differing px",len(d),"bbox",(min(x for x,y in d),min(y for x,y in d),max(x for x,y in d),max(y for x,y in d)) if d else None)
shots=[themed(n,0)]
seq=[]; s=settings(new)
for a in (28,28,29,29,29,29,29,29,29,28):
    m=key(s,a); seq.append((sysb(s)[2],[hex(x) for x in m]))
print("item after UP UP, DOWN x8, UP:",[i for i,_ in seq]); print("   msgs at page changes:",[m for i,m in seq if '0x36' in m][:2], "| within a page:",seq[2][1])
s=settings(new,1); print("row 1 text",[t for t in texts(s) if t.strip()][:9]); print("DOWN from About -> item",sysb(s)[2],"text",[t for t in texts(s) if t.strip()][-6:]); shots.append(themed(s,0))
ths=[]
for a in [SR]*12+[SL,SOK]:
    m=key(s,a); ths.append(s.uc.mem_read(THM,1)[0])
print("theme after RIGHT x12, LEFT, OK:",ths,"sub",sysb(s)[3],"item",sysb(s)[2])
for th in range(1,12):
    s2=settings(new,1,th); shots.append(themed(s2,th))
s2=settings(new,3,3); shots.append(themed(s2,3))
s.log.clear(); key(s,28); print("UP from Theme -> item",sysb(s)[2],[t for t in texts(s) if t.strip()]); shots.append(themed(s,s.uc.mem_read(THM,1)[0]))
m=key(s,SL); print("LEFT/RIGHT on Debug row: msgs",m,key(s,SR),"theme",s.uc.mem_read(THM,1)[0])
s.vals["tick"]=5000; s.uc.mem_write(0x2000FA00,bytes(208)); s.log.clear(); m=key(s,SOK); print("OK on Debug: msgs",[hex(x) for x in m],"sys",sysb(s),"page",stb(s)[:2],"lines",[t for t in texts(s) if t.strip()][:6]); shots.append(themed(s,s.uc.mem_read(THM,1)[0]))
s.call(0x0800F968); print("   1 s tick ->",[hex(x) for x,_ in s.msgs]); s.drain()
m=key(s,SOK); print("   OK on the page (clear):",[hex(x) for x in m],"page",stb(s)[0])
m=key(s,BACK); print("   BACK: msgs",[hex(x) for x in m],"sys",sysb(s),"page",stb(s)[0]); shots.append(themed(s,s.uc.mem_read(THM,1)[0]))
key(s,29); print("DOWN from Debug -> item",sysb(s)[2]); key(s,28); m=key(s,BACK); print("BACK from page 2 -> state",sysb(s))
# About still opens from item 5 and returns
s=settings(new,5); m=key(s,SOK); print("OK on About: msgs",[hex(x) for x in m],"sub",sysb(s)[3]); m=key(s,BACK); print("   BACK: msgs",[hex(x) for x in m],"sys",sysb(s))
p=settings(par,2); n=settings(new,2); a=key(p,SR); b=key(n,SR); print("stock value edit on item 2: parent",[hex(x) for x in a],p.uc.mem_read(0x20000C78+0xA2,4).hex(),"new",[hex(x) for x in b],n.uc.mem_read(0x20000C78+0xA2,4).hex())
sheet=Image.new("RGB",(250*len(shots)-10,320),(60,60,60))
for i,im in enumerate(shots): sheet.paste(im,(250*i,0))
sheet.save("out/s.png"); print(sheet.size)
