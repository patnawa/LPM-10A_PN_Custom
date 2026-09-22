# TX PN2.23R — original QC screen and automatic testing

ปรับตามผลใช้งาน PN2.23Q: ผู้ใช้ต้องการหน้าตาเดิมและการทดสอบอัตโนมัติ
เพราะตารางใหม่ใช้งานยากและข้อมูลกระพริบตลอด

PN2.23R กลับมาใช้รูปหัวสาย T568B และช่องผลทั้งแปดแบบเดิม
เข้า QC แล้ววัดอัตโนมัติต่อเนื่อง ไม่หยุดเมื่อครบ 20 วินาที
ไม่มีตารางจำนวนครั้ง ไม่มีปุ่มเริ่ม/หยุดหรือเริ่มรอบใหม่เพิ่มมา
กด Back เพื่อออก และกด Right ค้างเพื่อ Init ขณะถอดสาย
ปุ่ม Init เดิมยังใช้ได้ด้วย

## Cause and correction

The PN2.23Q renderer cleared the complete body before every table redraw.
A real Thumb/framebuffer regression with constant good readings showed a
black rectangle at `(8,52)..(230,315)` erasing **2,253 visible pixels** before
repainting them. A final screenshot looked unchanged and therefore missed
the transient blanking the user saw on the LCD.

The first failing command was:

```powershell
python -W ignore::ResourceWarning -m unittest test_qc_classic_ui -q
```

It failed in 0.602 s on Q. Ranked probes separated unconditional body erase,
the generic header/progress refresh, and continuously changing scan-counter
text. R removes the changing table, caches the displayed pin indications,
and handles repeated header/progress messages without clearing the body.

After the fix, unchanged readings and advancing scan counters produce **zero
pixel writes**, including repeated GUI refresh messages. A changed pin updates
only its original **15 by 15 pixel indicator**. The complete good/open result
framebuffers match PN2.23S pixel-for-pixel in English and Thai. The LED follows
the current eight readings, recovering to green when they are all good.

## Automatic operation and retained improvements

The first acquisition retains the 50 ms settling interval. Acquisition then
continues automatically until Back, power-off, or a calibration error that
requires Init. There is no 20-second completion and elapsed-timer wrap does
not restart settling. Ordinary OK/Right clicks follow the original key table;
old Q start/stop messages are ignored.

R retains the bounded single-pin acquisitions, five-sample calibration,
baseline preservation on failure, timer ownership, and session-generation
guards from Q. A failed Init displays the original persistent calibration
error prompt; it does not silently accept unstable calibration. Retry Init
with the cable removed. A successful Init restores the graphic and automatic
measurement. No extra controls or statistics are shown on the QC screen.

The existing count thresholds still describe contact-response indications,
not resistance or cable certification. The conservative calibration spread
limit remains six counts; its suitability on the physical unit needs feedback.
Internal history remains available to the code/tests but does not change the
classic current-result indicators.

## Build and verification

From `LPM-10A/Firmware File/sdk`:

```powershell
python qc_classic.py --write
python -W ignore::ResourceWarning -m unittest test_qc_classic test_qc_classic_ui test_qc_classic_build -q
python -W ignore::ResourceWarning -m unittest discover -q
```

The exact parent Q remains reproducible, SHA256
`969c775eba1f40805f9e64325a4e0838edf39fa0e964652a47c1158d0f7d5115`.
R adds a 16-byte initialized display cache to Q's 64-byte state and touches
only declared hooks, version fields and appended code. The historical Q
artifact and default release profiles remain unchanged.

Tests execute actual firmware GUI/key, timer and calibration paths while
modeling external pulse counts, RTOS scheduling and LCD I/O. They cover
continuous operation beyond 20 seconds/an hour and elapsed-timer wrap;
Back/reentry; calibration success, failure and retry; stale messages; 88
unmasked acquisition preemption points; startup initialization; pixel-write
traces; exact legacy artwork; patch ownership and deterministic containers.
Independent review found no blocking branch/stack/ownership defect.

The TX flash file is
`experimental/LPM-10A-TX_PN2.23R-qc-auto.bin`; its checksum is in
`experimental/TX-PN2.23R-SHA256SUMS.txt`.

The written artifact is **397,312 bytes**, SHA256
`cd94672633420a44e9bf9232de87adcc794cc57068035a260ffb6e4ffa35e8b4`.
File readback matches a fresh deterministic build and the checksum manifest.
The archived Q, default TX/RX releases and RX PN1.23G update retain their
previous hashes. The full TX suite passed **363 tests in 241.244 s** before
three additional regressions were added for composed startup initialization,
the historical Q erase behavior, and OPEN/CHECK display equivalence.
The final focused run passed **all 22 classic build/integration/UI tests in
34.486 s**, including those three additions.

Actual LCD flicker and electrical behavior still require confirmation on the
device. The emulator confirms that the repeated erase/redraw responsible for
the reproduced regression is absent.
