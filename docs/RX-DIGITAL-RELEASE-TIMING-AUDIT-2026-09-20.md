# RX PN 1.12 — countdown and completed-window timing audit

**ผลตรวจ:** ตัวนับเวลาของ Digital ไม่มีค่าตั้งใจให้ค้างเสียงหนึ่งวินาที
หลังผลตรวจจับครั้งสุดท้าย และใช้ TIM1 ตัวเดียวกับ Analog แต่หลักฐานนี้ยัง
ไม่อธิบายอาการที่เจ้าของยืนยันล่าสุดว่า หลัง TX แสดง Pause แล้ว Digital
ยังมี **เสียงยาวต่อเนื่องเส้นเดียวประมาณหนึ่งวินาที** ขณะที่ Analog หยุดได้เร็ว
คำตอบก่อนหน้าที่เลือกระหว่าง “หลายบี๊บหรือเกินหนึ่งวินาที” ไม่ควรถูกตีความ
เป็นหลักฐานว่าเสียงมีช่วงเงียบคั่น เจ้าของยังรายงานเสียงค้างหลังย้ายโพรบออกด้วย
เจ้าของยืนยันต่อมาว่าเสียงยืนยันปุ่ม MODE ของ RX ขณะ TX อยู่ Pause ก็นาน
ประมาณหนึ่งวินาที ทั้งที่โค้ดเขียน BEEP=100 จึงต้องตรวจเส้นทางนับเวลาเสียง
ร่วมด้วย ไม่ใช้ RECENT ของการรับรหัสเพียงอย่างเดียวอธิบายอาการ

พบช่องว่างที่มีอยู่จริงในสัญญาเวลา: หน้าต่าง ADC ที่เก็บเสร็จแล้วไม่มี timestamp
หาก main ถูกเลื่อนออกไปนาน ข้อมูลเก่ายังสามารถถูกวิเคราะห์และต่ออายุเสียงเมื่อ
main กลับมาทำงานได้ ยังไม่พบเส้นทางปกติในโค้ดที่ทำให้ main ล่าช้าถึงระดับนี้
จึง **ไม่สรุปว่าเป็นสาเหตุของอาการบนเครื่อง** และไม่เปลี่ยนเฟิร์มแวร์จากข้อสมมตินี้

## Identity and observed setup

The inspected artifact is `APP_LPM-10RX_PN1.12-overload.bin`, 26,152 bytes,
SHA-256 `4ea18c52bde25353a9a38dbf46775425860f7859bc2c10e3c908a7bff4044403`.
Instruction addresses below refer to these delivered bytes, not just patch
source. The existing boot emulator was run again against this exact file:

```text
cd "LPM-10A/Firmware File/rx-sdk"
python boot_emu.py ../experimental/APP_LPM-10RX_PN1.12-overload.bin
```

| Programmed item | Observed value / nominal consequence |
|---|---|
| RCC CFG | `0x0008240F` |
| SystemCoreClock / HCLK | 64,000,000 Hz |
| APB1 / APB2 | 32,000,000 Hz each; timer clocks 64,000,000 Hz |
| TIM1 PSC / ARR / RCR | 0 / 64000 / 0 → one update per **1.000015625 ms** |
| TIM5 PSC / ARR | 0 / 1600 → one update per **25.015625 µs** |

This is boot execution with modeled peripheral readiness and the existing
documented skips. It stops at ADC initialization. It proves the programmed
values in that startup path, not the oscillator frequency or interrupt arrival
latency measured on the physical unit. No Digital/Analog switch reconfigures
these timer periods in the inspected mode-switch paths.

The repetition counter was checked explicitly after the MODE-confirmation
observation. It is not merely zero because emulator registers start blank:
`tim_time_base_struct_init` at `0x0800B074` writes zero to the structure's
repetition field, and `tim_time_base_init` at `0x0800B192` writes that value to
TIM1 RCR at `0x40012C30`. Two independent leaf-initialization replays started
with RCR=9 and RCR=255, PSC=9 and ARR=9999; both finished with PSC=0, ARR=64000
and RCR=0. The traces also show the explicit ARR/PSC writes at `0x0800B162`,
`0x0800B16A` and `0x0800AEA8`. The boot register image has CTRL1=1 and SMCTRL=0.
No programmed tenfold repetition/counter-clock divisor was found by this check.

## Actual state transitions

| Address / state | Delivered behavior | Consequence |
|---|---|---|
| TIM1 `0x0800A9B8–0x0800A9BE`; BEEP `0x2000010C` | Decrement nonzero active pulse once per acknowledged TIM1 invocation | Normal and uncertain pulses count down through the same timer in both modes |
| TIM1 `0x0800A9F0–0x0800AA1A`; GAP `0x2000005A` | Decrement quiet interval when BEEP is zero | The gap does not run concurrently with an active pulse |
| TIM1 `0x0800AA1E–0x0800AA3A`; RECENT `0x2000006C` | Decrement nonzero RECENT once per acknowledged invocation | No 1-second divider applies to Digital freshness |
| Publisher `0x08009F20–0x08009F48` | Require no mode request and current open gate; publish GRADE; nonzero GRADE writes RECENT=800 | An accepted or uncertain Digital window refreshes the indication |
| Same publisher, GRADE=0 | Clear grade without writing RECENT | A rejected window cannot renew freshness; remaining RECENT alone cannot restart pulses |
| Scheduler `0x08007724–0x08007760` | New pulse requires BEEP=0, no mode request, current gate, RECENT>500, GAP=0 and nonzero GRADE | With no new accepted publication, no new pulse can begin after 300 delivered TIM1 ticks |
| Pulse helper `0x080086EC` | Normal pulse=30 ticks; uncertainty pulse=100 ticks with gap=160 | Starting the last permitted pulse does not add another 800-tick hold |
| Analog refresh in [analog_feedback.py](../LPM-10A/Firmware%20File/rx-sdk/analog_feedback.py) | After accepted publication, replace RECENT with 600 | Its corresponding freshness interval is 100 ticks; the timer unit itself is unchanged |

Under timely TIM1 servicing, with no later accepted publication, no key press,
and states produced by these handlers, the last Digital pulse finishes within
approximately **400 nominal ms of the last successful publication**. This is
a conservative state-based bound, not a measurement from the time a probe moves
or TX is paused. A completed window may still contain earlier signal data, and
subsequent accepted windows restart the freshness interval.

The latest report concerns one continuous sound, not confirmed repeats separated
by quiet gaps. The scheduler cannot extend an already-active BEEP merely because
a new frame refreshes RECENT: it exits that scheduling path whenever BEEP is
nonzero. Consequently repeated frame acceptance alone does not explain an
individual normal 30-tick or uncertain 100-tick pulse lasting about one second.
The actual BEEP writes/countdown, IRQ service, and speaker PWM behavior need
inspection. The report does not prove any one of these mechanisms has failed.

## Completed data and foreground ownership

The main loop at `0x0800B8F2` calls `sampling_boundary` before mode dispatch.
Digital calls `sampling_ready`, which requires ACTIVE=0, no pending mode change
and a current open gate. It then copies the completed 48-sample buffer to its
stack, retains 32 samples and publishes ACTIVE=1 before signal processing.
Calling the analyzer again while acquisition remains active does not reprocess
the old buffer. A new analysis normally needs sixteen newly reduced samples.

The ready check has **no completion timestamp or maximum completed-buffer age**.
If foreground execution is deliberately withheld while interrupts keep running,
a completed buffer can wait; later analysis can accept its old code and refresh
RECENT. The independent
[integrated release audit](../LPM-10A/Firmware%20File/rx-sdk/test_rx_digital_release_audit.py)
contains a dedicated delayed-foreground reproducer. Its imposed stall is a test
condition, not evidence that the same stall occurs on the owner's device.

The foreground Digital loops are bounded by fixed 48/16/8-sample limits and
finite sorting work. The normal main dispatch path contains no delay call.
The ADC critical section permits at most 500 polls before requesting reset;
it does not wait indefinitely and then return old ADC data. TIM1 housekeeping
uses two finite five-read ADC operations every 500 ticks. Instruction counts,
MMIO bus latency and actual scheduling are separate quantities; this audit
does not promote finite loop bounds to a hardware worst-case-time guarantee.

## IRQ priority assumption that the harness does not establish

The application calls `tim1_nvic_init` at `0x0800A958` with IRQ 25 / requested
preemption priority 1, and `tim5_nvic_init` at `0x0800AD98` with IRQ 50 /
requested priority 2. Their shared routine at `0x08008718` calculates bytes
using the existing AIRCR priority grouping. Startup sets VTOR, but no explicit
priority-group assignment was identified on the inspected application path.

Executing these two real initialization routines with each synthetic AIRCR
group gives the following programmed priority bytes:

| AIRCR PRIGROUP supplied by the test | TIM1 IRQ 25 byte | TIM5 IRQ 50 byte |
|---:|---:|---:|
| 0, 1, 2 | `0x00` | `0x00` |
| 3 | `0x10` | `0x20` |
| 4 | `0x20` | `0x40` |
| 5 | `0x40` | `0x80` |
| 6 | `0x80` | `0x00` |
| 7 | `0x00` | `0x00` |

Thus source labels “priority 1” and “priority 2” alone do not prove the active
priority arrangement. The hardware bootloader's inherited AIRCR value is not
available here. The usual direct-handler test harness manually supplies
interrupt order and does not model an NVIC pending queue. Neither this matrix
nor that limitation reproduces a one-second delay or establishes timer
starvation; changing interrupt priorities is not justified as a demonstrated
fix for the reported symptom.

## Decision

No explicit one-second hold, stale-buffer repeat loop, or proved one-second
blocking routine was found in the inspected steady Digital path. The missing
completed-buffer timestamp is a conditional freshness gap; the actual source
of any foreground stall remains unidentified. The new report after TX Pause
is useful device evidence and takes precedence over ideal flat-input release
simulations. A physical cause must remain unresolved until the ongoing release
and residual-input checks are compared with repeatable device observations.
