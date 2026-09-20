# Detailed Digital / Analog performance audit

**Follow-up:** this records the pre-improvement PN 1.9/1.10 RX behavior.
Several findings are now addressed in the local
[RX PN 1.11 / TX PN 2.14 candidate](TONE-TRACKING-PN1.11-PN2.14-2026-09-20.md).
Device and comparative validation remain pending; the original findings below
are preserved as the baseline.

## ข้อสรุปภาษาไทย

**ยังไม่ใช่ประสิทธิภาพสูงสุด และยังไม่ควรรับรองว่าเทียบเท่า Fluke**
Digital/Analog เป็นสองโหมดที่ผู้ใช้ยืนยันว่าใช้งานได้ แต่การตรวจเชิงลึกพบทั้ง
ข้อผิดพลาดใน TX และข้อจำกัดใน RX ที่ยังปรับปรุงได้ การเก็บรูปคลื่นเดิมหมายถึง
รักษาความเข้ากันได้กับวงจรจริง ไม่ได้หมายความว่าอัลกอริทึมรับเหมาะสมที่สุดแล้ว

| จุดตรวจ | ผลที่พบ | ความหมายต่อการใช้งาน |
|---|---|---|
| TX / ปุ่มขวา | เปลี่ยน PA8 โดยไม่แจ้งสถานะให้ตัวควบคุมพาหะรู้; จำลองพบช่วงผิดสถานะได้ 10.1 ms | แก้การจัดการสถานะใน PN 2.14 โดยคงคำสั่ง GPIO เดิม |
| Digital / เคลื่อนโพรบ | ความแรงเปลี่ยนภายในหน้าต่างข้อมูล อาจทำให้ปฏิเสธรหัสหรือยังรายงานความแรงเก่า | ในแบบจำลองที่ตรวจเทียบกับ ARM การเข้าสู่ระดับใหม่อาจใช้ประมาณ 390–470 ms ก่อนรวมเวลาสร้างเสียง |
| Digital / noise กระชาก | กระชากหลายครั้งในสองช่วงอ่านค่า ดัน threshold จนรหัสปกติหายก่อนถึงตัวคำนวณ median | ยังต้องปรับส่วนตรวจหารหัส ไม่ใช่เฉพาะสูตรวัดความแรง |
| Digital / ความละเอียดเสียง | ช่วงที่สัญญาณแรง ค่าความแรงต่างกันหลายสิบเปอร์เซ็นต์อาจได้เสียงเดิม | ยังมีช่องให้ปรับการแสดงความแรงสำหรับแยกสายในมัด |
| Analog / ความละเอียดและการตอบสนอง | มีเพียงสามระดับเสียง; ตัวอย่างสัญญาณแรงขึ้นต้องรอ 378 ms จึงเปลี่ยนเสียง | รับโทนได้ แต่ยังไม่เหมาะที่สุดกับการเทียบสายขณะเคลื่อนโพรบ |
| Analog / ภาระคำนวณ | คำนวณ DFT 31 bins มากกว่า 230,000 คำสั่งต่อหน้าต่าง และหยุดรับข้อมูลระหว่างคำนวณ | มีโอกาสลดช่วงที่ไม่ได้เก็บข้อมูลโดยปรับโค้ดให้ผลเดิม |
| สัญญาณอิ่มตัว / สัญญาณรั่วไปสายข้างเคียง | ยังมีกรณีอิ่มตัวที่ได้เสียงแรงปกติ และรหัสเดียวกันจากสายข้างเคียงยังผ่าน | รหัสตรงกันหรือเสียงดังที่สุดไม่ใช่หลักฐานยืนยันว่าสายนั้นเป็นต้นทางเสมอ |

ผลตัวเลขด้าน RX ด้านล่างมาจาก ADC จำลองที่ป้อนเข้าเฟิร์มแวร์จริงใน emulator
ไม่ใช่การวัดระยะหรือความแม่นยำกับมัดสายจริง ผู้ใช้ไม่มีเครื่องมือวัด จึงคง
ภาคส่งและแรงขับเดิม และแยกข้อเสนอปรับ RX ออกจากการแก้ TX ที่พิสูจน์ได้ชัดเจน

## Scope and evidence

Audited the preserved PN 2.12 TX waveform/control logic, the PN 2.14 two-mode
candidate, and the exact delivered PN 1.9/PN 1.10 RX binaries. Sync32 and Pulse
test are removed from the PN 2.14 menu at the owner's request. The owner reports
Digital/Analog work and Sync32 is silent with RX PN 1.10 in digital mode.

Evidence includes actual ARM execution of carrier initialization, GPIO
configuration, key dispatch, TIM1/TIM5 handlers, detector/median code, the full
analog DFT, and beep publication. ADC values, oscillator-ready bits, peripheral
timing and the analog link are modeled. Instruction counts are not CPU cycles,
on-device deadlines, or proof of physical cable selectivity.

## TX: correct timing, one control defect

Actual SystemInit and RCC_GetClocksFreq execution reports nominal clocks of
144 MHz system/AHB, 36 MHz APB1 and 72 MHz APB2. The timer clock doubles when
the respective APB prescaler is greater than one; this is documented in the
[Nations N32G45x reference manual, clock tree section 6.2.1](https://www.nationstech.com/uploadfile/file/20230822/1692689014562769.pdf).

| Configuration | Nominal result |
|---|---:|
| TIM1 PSC 0, ARR 316, CCR1 158 | 454,258.675 Hz carrier |
| TIM2 PSC 71, ARR 100, 72 MHz timer clock | 101 microseconds per tick |
| Analog transition every six ticks | 825.0825 Hz modulation |
| Digital 50 ticks per chip | 5.05 ms per chip; 198.0198 chips/s |
| Distinct B6 pattern, eight chips | 40.4 ms code period |

The digital-wrap fix already present in PN 2.12 is correct. The original
waveforms do not need a speculative frequency or duty increase to repair the
reported problem. Physical clock tolerance is still unmeasured.

### RIGHT-key defect and repair

Actual SCAN RIGHT-click dispatch (`key=5,event=3`) reaches
`0x080149FC -> action 9 -> 0x0800D3B4 -> 0x0801446C`. Its call at `0x08014480`
invokes `0x0801C590`, which changes PA8 to analog input. PB13 can remain in
timer-output mode while the cached gate at `0x200000DC` still says HIGH.
Further HIGH requests then skip restoration.

The preserved parent reproduces up to 100 subsequent ticks before both pin
modes recover in the Digital fixture, or nominally 10.1 ms; the Analog fixture
needs six ticks, nominally 606 microseconds. This is a GPIO-state defect;
the electrical effect on the cable is not measured. It does not establish the
cause of the Sync32 failure.

The conservative PN 2.14 repair retains the original GPIO operation, preserves
PRIMASK, and invalidates the cache atomically. The next requested timer tick
then restores the appropriate state. It uses no new RAM. The audit checks all
800 Digital cursor phases and 12 Analog phases, both prior interrupt-mask
states, and the states observable at unmasked instruction boundaries.
The added interrupt-masked region executes 133 instructions in the audit;
its duration on the hardware has not been measured.
The original reason for the RIGHT GPIO operation remains uncertain, which is
why it is retained rather than deleted.

### Further TX optimization requires a tradeoff

The general GPIO initializer runs twice per carrier transition. In the audit,
the PB13 and PA8 configuration writes are separated by 126 executed instructions.
Across 10,001 full-IRQ ticks per mode, Digital averages 113.63 instructions with
a maximum of 393; Analog averages 170.76 with a maximum of 451. These results
are for the specified modeled sequence, not exhaustive timing bounds.

Specialized register updates could reduce instruction overhead and inter-pin
skew. They would change electrical transition behavior and deserve scope
comparison before deployment. The vendor's OFF routine also drives both pins
HIGH or both LOW according to deterministic RTOS-tick parity. Its analog/DC
purpose is unknown and has been preserved. Complementary PA8/PB13 timer outputs
do not prove balanced injection at the RJ45 connector.

## RX Digital: ranking is robust after acquisition, but acquisition is limiting

The independent model and **4,980 actual ARM executions** agree across 2,490
vectors for each pinned PN 1.9 and PN 1.10 image. The examples concern the
established B6 signal. All levels are raw ADC counts, not distance or calibrated
field strength.

### Impulses can prevent the robust estimator from running

For a clean 1,000-count baseline and 100-count contrast, two full-rail reduced
samples at positions 0 and 16 raise the trimmed-mean threshold to 1,128, above
the normal HIGH value of 1,100. The code is rejected before the code-group
median estimator runs.

This is also possible through the five-read reducer: two HIGH groups containing
three 4,095-count reads each reduce to 3,096, and the resulting threshold of
1,106 still exceeds the normal HIGH level. At contrast 10, two rail readings
per group suffice in the reproduced case. One isolated raw spike per group is
removed correctly. Thus median strength alone does not make the entire
detector robust against burst interference.

Potential improvement: robust estimation of both signal levels or bounded soft
correlation before code decisions. Evaluate noise-only acceptance and false
ranking before changing the existing eligibility rules.

### Movement causes mixed-window dropouts and stale ranking

An otherwise valid B6 waveform changing amplitude from 100 to 300 at reduced
sample 25 produces a rejected window. A change at sample 33 can preserve the
old 100-count strength. Across eight phases and 49 transition positions:

| Amplitude step | New rank | Rejected | Old/intermediate rank | Worst modeled settled-rank delay |
|---|---:|---:|---:|---:|
| 100 -> 300 | 172 | 95 | 125 | 390.244 ms |
| 3000 -> 60 | 23 | 189 | 180 | 470.294 ms |

Each row contains 392 reduced-sample cases. Delays exclude processing time,
the physical acquisition aperture and audible scheduling. They are not measured
human/device response times. The limitation arises from non-overlapping
48-sample windows and threshold/grouping behavior when amplitudes mix.

Potential improvement: once a code phase is qualified, estimate strength from
a shorter trailing interval while preserving deliberate unlock rules. This
needs moving-probe and noisy-window regressions, rather than merely shortening
the code window and accepting more interference.

### Cadence mapping masks strong-signal differences

At a previous amplitude of 2,000 counts and a 38 ms quiet gap, new amplitudes
1,717 through 2,313 keep the same feedback because of the 3 ms cadence deadband.
At amplitude 3,000 and a 30 ms gap, the retained range is 2,672 through 3,268.
The high-minus-low estimate can be correct while audible comparison remains
coarse. Filtering the strength before mapping, or a precision feedback range,
could improve discrimination; simply removing all hysteresis would add jitter.

### Baseline, overload and code identity limits

The inherited absolute HIGH-sum gate requires a minimum clean contrast of 34
counts at baseline zero, compared with 9 at baseline 25 or 1,000. Removing it
would change weak-signal and noise acceptance and requires evaluation against
real ADC noise. A 188-count linear baseline change across the window at contrast
100 leaves only two of eight phases accepted in the tested examples.

Partial saturation can also escape the uncertainty indication: clipping 15 of
30 HIGH samples to 4,095 still yields a normal stronger estimate of 3,797; the
upper median reaches the rail at 16 clipped HIGH samples. The existing guard
recognizes rail-dominated medians, not every clipped or compressed waveform.

Finally, a same-phase coupled copy adds to the measured code amplitude. A
100-count target plus a 200-count correlated contribution is indistinguishable
from a 300-count code in this observation. A stronger coupled neighbor can win
the ranking. Code matching proves recognition of the waveform, not physical
identity of the cable under the tip.

## RX Analog: adequate tone recognition, limited precision feedback

The analog audit checks **52 full-analyzer ARM windows**, four instruction/stack
profiles, all 832 IRQs for acquisition, and existing mode/gate regression cases.
Unlike Digital, Analog takes one ADC reading per sample, with no five-reading
trimmed reducer. It acquires 64 readings at 3,075.0012 samples/s in 20.813 ms.

| Finding | Reproduced evidence | Assessment |
|---|---|---|
| Frequency offset | Bin 17 is 816.797 Hz; TX is nominally 825.083 Hz. A 300-count sinusoid gives margin 299 at bin center versus 261 at TX frequency | Approximately 13% lower margin in this fixture; a modest opportunity, not a reason to change both devices' waveform immediately |
| Coarse strength | Margins above 10/200/600 select 200/100/50 ms tones and equal quiet gaps; square-envelope steps from 25 through 300 counts all select 200 ms | Too few audible levels for fine bundle comparison |
| Slow feedback change | Weak tone starts at tick 0; strong results begin at tick 21; the first strong tone starts at tick 399 | 378 ticks, approximately 378 ms, of response lag in the modeled publisher/scheduler sequence |
| Expensive analysis | 230,116–235,128 retired instructions and 408 bytes of stack across four profiles | All 31 DFT bins run before rearming acquisition; a processing gap exists, but its hardware duration has not been measured |
| Missing overload indication | Clipped 825 Hz examples with 25, 43 or 55 of 64 readings at the rails still select the ordinary fastest tone | Strong ordinary feedback can conceal unusable saturation |
| Marginal false indications | Actual analyzer beeps for selected independent-noise windows containing no tone | Single-window weak acceptance needs further evaluation |

The noise metric is the sum of bins 1–31 after excluding bins 1 and 17, divided
by **12**. It is not the average of the remaining 29 bins. Replacing the divisor
with 29 would change acceptance substantially; it is not a harmless arithmetic
cleanup.

In separate synthetic 1,024-window independent-uniform-noise sets, the
mathematical model accepted 2/6/8/14 windows at noise ranges of +/-200/400/800/1600
counts. Selected cases were reproduced in the actual ARM analyzer. These counts
are not field false-alarm rates and do not characterize real cable noise.

Recommended sequence: improve grading and update latency while preserving
eligibility; add an uncertainty indication for substantial upper-rail clipping;
optimize existing DFT results bit-for-bit; then evaluate short temporal
confirmation for marginal signals using recorded noise. Do not merely lower
the detector threshold to make it appear more sensitive.

## Sampling, control and electrical unknowns

The existing ADC completion transaction remains serialized and returns data
only after completion. A failed conversion requests reset after 500 polls;
an old source comment incorrectly said 128 and is corrected without changing
binary output. Across 20 injected-completion cases, the current code retains
the intended channel ownership and reset behavior.

With immediate modeled completion, 107 executed instructions occur with
interrupts masked. An injected 500-instruction conversion delay gives 602
masked instructions; the timeout fixture reaches 2,597 before requesting reset.
These are model counts, not measured conversion times. Interrupt latency and
ADC settling still need hardware evidence before changing sample time or
removing serialization.

The PA2-derived gate is sampled every 500 nominal milliseconds. Digital opens
at raw level 2; Analog at raw level 580. A derived code `raw//580` is written to
PB12–PB14, with zero mapped to the same output pattern as code 3. The actual
publisher invalidates acquisition when a gate opens/closes, but not for code
changes within an already open gate.

If those pins control analog gain, a window spanning a code change could mix
different gains and uncalibrated amplitudes would not be directly comparable.
If they are indicators, that inference would be wrong. The physical mapping is
not established by disassembly. The manufacturer lists adjustable sensitivity,
but does not establish this internal pin mapping on its
[LPM-10A product page](https://www.fnirsi.com/products/lpm-10a). No gate or gain
control is changed in this audit.

Firmware evidence alone cannot establish output impedance, jack voltage/current,
pair balance, front-end bandwidth, pickup geometry, internal clipping, usable
range or target-to-neighbor contrast. These set practical limits alongside the
code. Increasing transmitter drive could increase coupled signals in neighboring
cables as well; it is not a demonstrated path to better identification.

## Changes delivered and improvement priorities

**Delivered in TX PN 2.14:** only Digital/Analog in the menu, explicit frequency
labels with suitable button width, and the proven RIGHT-key cache repair.
Carrier frequency, waveform, pin-drive settings and existing mode timing remain
unchanged. See the [candidate and checksums](TONE-RECOVERY-PN2.14-2026-09-20.md).
RX PN 1.10 remains unchanged and can continue receiving these two modes.

**Not implemented by this audit:** the proposed RX signal-processing changes.
They alter sensitivity, response and false indications, so each needs its own
comparison against the concrete counterexamples above. The next firmware work
should prioritize robust Digital acquisition and faster post-lock strength
tracking, then precision feedback and equivalent-result Analog DFT optimization.
This is a more evidence-based direction than adding another unsupported code
or increasing electrical drive without measurements.

## Reproduce the audit

Run from the repository root with the SDK's existing dependencies:

```text
python docs/experiments/tx_tone_performance_audit.py
python docs/experiments/digital_bundle_audit.py --arm
python docs/experiments/rx_analog_performance_audit.py --arm
python docs/experiments/rx_control_performance_audit.py
```

The scripts pin their firmware inputs by SHA-256 and emit structured findings.
The TX script preserves the failing PN 2.12 case and demonstrates the repair
in emulator memory. It does not write a firmware image. New acquisition and
real-GPIO regressions are in `rx-sdk/test_scan_acquisition_timing.py` and
`sdk/test_scan_hardware.py`; the delivered fix is tested in
`sdk/test_scan_recovery.py`. Earlier scalar CPU tests passing is not a substitute
for the owner's device feedback recorded at the top of this report.
