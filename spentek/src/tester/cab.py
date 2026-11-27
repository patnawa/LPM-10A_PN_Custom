import sys
SDK="/home/claude/repo/LPM-10A/Firmware File/sdk"
sys.path.insert(0,SDK)
from test_cable_session import SessionHarness
from test_cable_check import SWITCH, RX, switch_end, rx_end, STRAIGHT, CROSSOVER
import cable_check as CC
from PIL import Image
H="/home/claude/apps/out/LPM-10A-TX_PN2.34H-home.bin"
def cases():
    broken=dict(STRAIGHT); broken[4]=None
    crossed=dict(STRAIGHT); crossed[5],crossed[6]=6,5
    gx=dict(CROSSOVER); gx.update({3:6,4:7,6:3,7:4})
    utp=dict(STRAIGHT); utp[8]=None
    utpx=dict(CROSSOVER); utpx[8]=None
    rev={i:7-i for i in range(8)}; rev[8]=8
    return [("sw ok",SWITCH,switch_end()),("sw short",SWITCH,switch_end(shorts=[{0,2}])),("sw unplug",SWITCH,switch_end(plugged=False)),
            ("sw open4",SWITCH,switch_end(broken)),
            ("rx ok",RX,rx_end()),("rx utp",RX,rx_end(utp)),("rx xover",RX,rx_end(CROSSOVER)),("rx utp xover",RX,rx_end(utpx)),("rx gig xover",RX,rx_end(gx)),
            ("rx open4",RX,rx_end(broken)),("rx 6-7 swap",RX,rx_end(crossed)),("rx short",RX,rx_end(shorts=[{0,1}])),
            ("rx rollover",RX,rx_end(rev)),("rx nothing",RX,rx_end({}))]
def run(path, sel=None, out=None):
    data=open(path,'rb').read(); shots=[]
    for name,mode,far in cases():
        if sel and name not in sel: continue
        h=SessionHarness(data,mode=mode,reading=far)
        h.s.log.clear()
        h.send(2); h.flush()
        st=bytes(h.s.uc.mem_read(CC.STATUS,9)); mp=bytes(h.s.uc.mem_read(CC.MAP,18))
        import struct
        print(f"{name:14s} status {st.hex()} map {struct.unpack('<9H',mp)} led {h.leds[-1:]} beeps {h.beeps}")
        for l in h.s.log:
            if l[0]=='ascii': print("      ",l[1],l[2],l[3],hex(l[4]),l[5])
        shots.append(h.s.image(1))
    if out:
        sh=Image.new("RGB",(250*len(shots)-10,320),(60,60,60))
        for i,im in enumerate(shots): sh.paste(im,(i*250,0))
        sh.save(out)
if __name__=="__main__":
    run(sys.argv[1] if len(sys.argv)>1 else H, out="/home/claude/apps/out/cab.png")
