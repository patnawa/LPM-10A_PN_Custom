import sys, struct, random
sys.argv=[sys.argv[0],"/home/claude/theme/out/LPM-10A-TX_PN2.34C-cyber.bin",sys.argv[1] if len(sys.argv)>1 else "out/LPM-10A-TX_PN2.34X-tetris.bin"]
exec(open("/home/claude/apps/check_apps3.py").read().split("# A. stock pages")[0])
sys.path.insert(0,"/home/claude/theme")
from unicorn.arm_const import *
import build_cyber as BC
G=0x2000F900
def themed(s,scale=1):
    im=Image.new("RGB",(240,320)); px=im.load()
    for y in range(320):
        for x in range(240):
            c=BC.theme(s.fb[y][x]); px[x,y]=(((c>>11)&31)*255//31,((c>>5)&63)*255//63,(c&31)*255//31)
    return im
def poll(s):
    uc=s.uc; sp=0x2000E000-0x18
    uc.reg_write(UC_ARM_REG_SP,sp); uc.reg_write(UC_ARM_REG_LR,E.MAGIC|1)
    uc.emu_start(0x0800F462|1,0x0800F46C,count=20_000_000)
    assert uc.reg_read(UC_ARM_REG_PC)==0x0800F46C and uc.reg_read(UC_ARM_REG_SP)==sp
    assert uc.reg_read(UC_ARM_REG_R1)==sp+8 and uc.reg_read(UC_ARM_REG_R0)==0x20001000, (hex(uc.reg_read(UC_ARM_REG_R0)),)
    return uc.reg_read(UC_ARM_REG_R2)
names={4:"CableTest",5:"SCAN",6:"FLASH",7:"Length",8:"QC",9:"SPEED",10:"POE",11:"SETTING",12:"Pinout",13:"Link",14:"Tetris"}
print("A. navigation (sel -> UP, DOWN, LEFT, RIGHT):"); ok=True
for sel in range(4,15):
    row=[]
    for k in (UPK,DOWNK,LEFTK,RIGHTK):
        s=home(new,sel); key(s,k); row.append(sysb(s)[1])
    print(f"   {names[sel]:9s} -> {[names.get(v,v) for v in row]}"); ok&=all(4<=v<=14 for v in row)
print("   every move lands on a real tile:",ok)
shots=[]
s=home(new,14); shots.append(themed(s)); print("B. page 3 text",texts(s))
s=home(new,12); key(s,OKH); seq=[stb(s)[0]]
for k in (SR,SR,SR,SL,SL,SL): key(s,k); seq.append(stb(s)[0])
print("C. Pinout tile, RIGHT x3 LEFT x3 -> pages",seq, "poll timeout on Link page",hex(poll(s)))
# settings list UP/DOWN unchanged
def lst(path):
    s=scene(path); s.w8(SYS+2,2); s.w8(SYS+3,0); s.set_state(11); s.post(0x32); s.drain(); r=[]
    for a in (28,29,29,28): key(s,a); r.append(sysb(s)[2])
    return r
print("D. settings list UP/DOWN items: parent",lst(par),"new",lst(new))
s=home(new,5); print("E. poll on home: timeout",hex(poll(s)),"game magic",s.uc.mem_read(G,1)[0])
# Tetris
s=home(new,14); s.uc.mem_write(G,bytes(range(1,233))); s.vals["tick"]=1000; s.vals["tick_step"]=0
poll(s); posted=key(s,OKH); print("F. OK on Tetris tile: msgs",[hex(m) for m in posted],"sys",sysb(s),"st",stb(s))
t=poll(s); gs=lambda: struct.unpack("<BBBBbbBBIIHB",s.uc.mem_read(G,19))
print("   first poll timeout",t,"state",gs(),"text",[x for x in texts(s) if x.strip()][-9:])
shots.append(themed(s))
x0=gs()[4]; key(s,SL); poll(s); x1=gs()[4]; key(s,SR); key(s,SR); poll(s); x2=gs()[4]
r0=gs()[3]; key(s,28); poll(s); r1=gs()[3]; key(s,SOK); poll(s); r2=gs()[3]
print(f"   LEFT x {x0}->{x1}, RIGHT RIGHT ->{x2}; UP rot {r0}->{r1}; OK rot ->{r2}")
y0=gs()[5]; s.vals["tick"]+=700; poll(s); y1=gs()[5]; print(f"   gravity after 700 ms: y {y0}->{y1}")
key(s,29); poll(s); b=bytes(s.uc.mem_read(G+32,200)); print("   DOWN: hard drop locked",sum(1 for v in b if v),"cells, score",gs()[9],"new piece y",gs()[5])
# board on screen == board in RAM
def screen_ok():
    b=bytes(s.uc.mem_read(G+32,200)); COL=[0,0x07FF,0x0640,0xFD20,0xFFE0,0x0500,0xFB14,0xF800]; st=gs(); bad=0
    cur=set()
    SH=[[0x0F00,0x2222,0x00F0,0x4444],[0x44C0,0x8E00,0x6440,0x0E20],[0x4460,0x0E80,0xC440,0x2E00],[0xCC00]*4,[0x06C0,0x8C40,0x6C00,0x4620],[0x0E40,0x4C40,0x4E00,0x4640],[0x0C60,0x4C80,0xC600,0x2640]]
    for i in range(16):
        if SH[st[2]][st[3]]>>(15-i)&1: cur.add((st[4]+(i&3),st[5]+(i>>2)))
    for cy in range(20):
        for cx in range(10):
            want=COL[st[2]+1] if (cx,cy) in cur else COL[b[cy*10+cx]]
            if s.fb[62+cy*12+5][16+cx*12+5]!=want: bad+=1
    return bad
print("   screen matches RAM after drop: mismatched cells",screen_ok())
random.seed(5); lines=0; games=0; polls=0; over_seen=False; mid=None
for n in range(6000):
    a=random.choice([SL,SR,28,SOK,29,None,None,None]) 
    if a: key(s,a)
    s.vals["tick"]+=random.choice([20,20,60,200]); poll(s); polls+=1
    st=gs()
    if st[1] and not over_seen: over_seen=True; shots.append(themed(s)); print("   game over at poll",n,"score",st[9],"lines",st[10],"level",st[11],"screen mismatches (banner covers some)",screen_ok())
    if st[10]>=3 and mid is None and not st[1]: mid=themed(s); print("   mid-game check at poll",n,"lines",st[10],"mismatched cells",screen_ok())
    lines=max(lines,st[10])
if mid: shots.insert(2,mid)
print("   6000 random polls ok; max lines in a game",lines,"final state",gs()[:6])
# skilled play for line clears: fill rows by dropping O pieces
s.uc.mem_write(G+1,b"\x01"); key(s,SOK); poll(s)
cl=0
for n in range(40):
    s.uc.mem_write(G+2,bytes([3,0])); s.uc.mem_write(G+7,b"\x01"); poll(s); col=(n%5)*2
    st=gs(); dx=col-st[4]
    for _ in range(abs(dx)): key(s,SR if dx>0 else SL); poll(s)
    key(s,29); poll(s)
st=gs(); print("G. forced O-piece fill: lines",st[10],"score",st[9],"level",st[11],"over",st[1],"mismatched cells",screen_ok()); shots.append(themed(s))
key(s,BACK); print("H. BACK -> sys",sysb(s),"page",stb(s)[0],"poll timeout",hex(poll(s)))
s2=home(new,14); print("   home redrawn equals fresh home at Tetris tile:",flat(s)==flat(s2))
key(s,OKH); poll(s); print("   re-enter: resumes game (lines kept):",gs()[10]==st[10], "over",gs()[1])
sheet=Image.new("RGB",(250*len(shots)-10,320),(60,60,60))
for i,im in enumerate(shots): sheet.paste(im,(250*i,0))
sheet.save("out/x.png"); print(sheet.size)
