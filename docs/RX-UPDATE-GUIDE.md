# คู่มืออัปเดตเฟิร์มแวร์ RX (probe) — RX firmware update guide

*ภาษาไทยก่อน, English below.* ใช้ได้กับ RX PN ทุกรุ่นตั้งแต่ PN 1.12 และกับการย้อนกลับไปโรงงาน V3.0.0
พิสูจน์บนเครื่องจริง 2026-09-21 (แฟลชสำเร็จ 8 ครั้งในวันเดียว: V3.0.0, PN 1.12, 1.14, 1.15, 1.16, 1.17, 1.18, 1.19)
รุ่นปัจจุบัน / current build: **RX PN 1.30** (`APP_LPM-10RX_PN1.30-clean-strength-update.bin`, release [rx-v1.30](https://github.com/patnawa/LPM-10A_PN_Custom/releases/tag/rx-v1.30))

---

## 1. สรุปสั้น (อ่านแค่นี้ก็ทำได้)

1. ปิด RX → **กด SCAN ค้าง** → เสียบ USB เข้าคอม → ปล่อย SCAN เมื่อไดรฟ์ชื่อ **`BOOTLOADER`** ขึ้น
2. **ก๊อปปี้ไฟล์ที่ชื่อลงท้าย `-update.bin`** (เช่น `APP_LPM-10RX_PN1.30-clean-strength-update.bin`) ลงไดรฟ์นั้น
   ด้วย **Explorer แบบปกติ** (ลาก-วาง หรือ Ctrl-C/Ctrl-V หรือ `Copy-Item`)
3. **ภายใน ~1 วินาที ไดรฟ์จะหายไปเอง** = เขียนเสร็จและ RX รีบูตเข้าเฟิร์มแวร์ใหม่แล้ว ถอด USB ใช้งานได้
   (ถ้าเครื่องเงียบ กดปุ่มเปิดตามปกติ; ตอนบูตจะได้ยิน chirp สูง→ต่ำ ในรุ่น PN 1.14 ขึ้นไป)

**ห้าม**: ก๊อปปี้ไฟล์ `.bin` ที่ไม่มี `-update` (image ดิบ) — บูตโหลดเดอร์จะเงียบ ไม่ทำอะไร;
ใช้โปรแกรมเขียนแบบช้า/ทีละ sector/`dd` — บูตโหลดเดอร์จะยกเลิกและเข้าแอปเดิม

## 2. ทำไมก่อนหน้านี้อัปเดตไม่ได้ และแก้อะไร

**ต้นเหตุ:** บูตโหลดเดอร์ของ RX รับเฉพาะไฟล์รูปแบบ **container** (มีส่วนหัว 4 KB) แบบเดียวกับไฟล์ TX ของ FNIRSI
แต่ไฟล์ RX ที่ FNIRSI แจก (`APP_LPM-10RX_V3.0.0_260416.bin`) และไฟล์ PN ทุกตัวก่อน 2026-09-21 เป็น **image ดิบ**
(เริ่มด้วย vector table) → บูตโหลดเดอร์รับข้อมูลครบทุก sector แล้ว**ทิ้งเงียบ ๆ** ไม่มี error ใด ๆ
ผลทดสอบ "device pass" ของ RX PN 1.3–1.8 ก่อนหน้านี้จึงเป็นการทดสอบเฟิร์มแวร์โรงงานทั้งหมด

พบโดยต่อ ST-Link อ่าน SRAM ของบูตโหลดเดอร์ (อ่านอย่างเดียว) ขณะก๊อปปี้ไฟล์แบบต่าง ๆ — รายละเอียดใน
[RX-UPDATE-PROCEDURE-2026-09-21.md](RX-UPDATE-PROCEDURE-2026-09-21.md)

**สิ่งที่แก้ใน repo เพื่อให้อัปเดตได้:**

| ไฟล์ | สิ่งที่เพิ่ม |
|---|---|
| `rx-sdk/lpm10rx/container.py` | `wrap(raw)` สร้าง container จาก image ดิบ, `unwrap()` ตรวจ/แกะ, CLI `python -m lpm10rx.container wrap|check` |
| `rx-sdk/build.py` | ทุก `--write` เขียน **2 ไฟล์**: `<ชื่อ>.bin` (image ดิบ ใช้เทียบ hash/emulate) และ **`<ชื่อ>-update.bin`** (container ที่ต้องก๊อปปี้) |
| `rx-sdk/lpm10rx/image.py` | `Image.extend()` ต่อโค้ดท้าย image ได้ (container พกความยาว payload ไปเอง) — ใช้ตั้งแต่ PN 1.14 |
| `rx-sdk/test_container.py` | เทสว่ารูปแบบ = ไฟล์ที่เครื่องรับจริงแบบ byte-exact |

**รูปแบบ container** (ไฟล์ 32 768 ไบต์สำหรับ image ≤ 28 KB):

```
offset  ขนาด  ความหมาย                                    ตัวอย่าง (PN 1.19)
0x0000  32    ชื่อภายใน ASCII เติมศูนย์                    "APP_LPM-10RX_V3.0.0_260416.bin"
0x0020  u32   payload_off = 0x1000                        00 10 00 00
0x0024  u32   payload_len = ขนาด image ดิบ                 c8 67 00 00  (= 26 568)
0x0028  u32   payload_end = payload_off + payload_len - 1 c7 77 00 00
0x002C  ..    ศูนย์จนถึง 0x1000
0x1000  ..    image ดิบ (โหลดที่ 0x08006800; เริ่ม 18 16 00 20 = stack pointer)
  ...         เติมศูนย์ให้ไฟล์เป็นผลคูณของ 4 096
```

ชื่อภายในและเลขเวอร์ชันในชื่อ **ไม่มีผล**ต่อการรับ (ทดสอบทั้ง V3.0.0 และ V3.0.2) จึงคงชื่อไฟล์โรงงานไว้
เหมือนที่ TX ทำ; ไม่พบ checksum/signature ใด ๆ ในรูปแบบนี้

## 3. อ่านสถานะจากไดรฟ์

ไฟล์เปล่า `.TXT` บนไดรฟ์ `BOOTLOADER` คือ**ช่องบอกสถานะ**ของบูตโหลดเดอร์ (Windows อาจแสดงชื่อเก่าจาก cache —
ชื่อจริงเห็นตอน mount ใหม่หรือหลัง Eject):

| ชื่อไฟล์ | ความหมาย |
|---|---|
| `PN1.20.TXT` … `PN1.30.TXT` | รุ่น PN ที่ติดตั้งอยู่ (ตั้งแต่ PN 1.20 แอปเขียนชื่อรุ่นลงหน้าเวอร์ชันทุกครั้งที่บูต) |
| `3.0.0.TXT` (หรือ `3.0.1.TXT`, `3.0.2.TXT`) | แอปโรงงาน หรือ PN ก่อน 1.20 (ใช้สตริง `3.0.0` ของโรงงาน) |
| `UNKOWN.TXT` | ไฟล์ล่าสุดที่ได้รับ**ไม่ใช่ container** → ถูกทิ้ง ไม่มีอะไรเปลี่ยน |
| `APPRUN.TXT` | ได้รับส่วนหัว container แล้ว แต่ข้อมูลหยุดมาเกิน ~100 ms (เขียนช้า) → ยกเลิก เข้าแอปเดิม |

## 4. ตรวจว่าติดตั้งรุ่นไหน

ตั้งแต่ PN 1.20 ดูจากไฟล์สถานะได้เลย: เข้าไดรฟ์ `BOOTLOADER` อีกครั้ง (ไม่ต้องก๊อปปี้อะไร) จะเห็นเช่น `PN1.30.TXT`
ถ้าเห็น `3.0.0.TXT` = โรงงานหรือ PN ก่อน 1.20 ซึ่งแยกได้ด้วยการฟัง:

| ที่ได้ยิน | รุ่นที่ติดตั้ง |
|---|---|
| บี๊บ 50 ms / เว้น 50 ms คงที่เมื่อจับสัญญาณ, เสียงเดียวทุกโหมด | โรงงาน (V3.0.0 / 3.0.1) |
| พัลส์ 30 ms จังหวะเร็วขึ้นตามความแรง, เสียงเดียว 2.5 kHz ทั้ง Digital/Analog | PN 1.12 |
| เปิดเครื่องได้ยิน chirp สูง→ต่ำ; Analog เสียงต่ำกว่า Digital 1 octave; กดเปลี่ยนโหมด chirp | PN 1.14 ขึ้นไป |
| หมุนปุ่มแล้วจังหวะ**ไม่**เปลี่ยน (เปลี่ยนตามระยะสายเท่านั้น) | PN 1.15–1.19 |
| แนบสาย = เร็วสุดเท่ากันทุกตำแหน่งปุ่ม | PN 1.18/1.19 |

ตรวจแบบแม่นยำ: `docs/experiments/rx_ro.py sram` ผ่าน ST-Link แล้วเทียบ return address บน stack กับจุด BL ของ image
(วิธีใน RX-UPDATE-PROCEDURE)

## 5. ย้อนกลับ (รุ่น PN ก่อนหน้า หรือโรงงาน V3.0.0)

**รุ่น PN ก่อนหน้า:** ก๊อปปี้ไฟล์ `-update.bin` ของรุ่นนั้นตามข้อ 1 ได้เลย เช่น PN 1.29 =
`LPM-10A/Firmware File/archive/APP_LPM-10RX_PN1.29-levels-update.bin` หรือไฟล์ใน release rx-v1.29

**โรงงาน V3.0.0:** ไฟล์โรงงานไม่อยู่ใน repo (กติกาของโปรเจกต์) สร้าง container เองจากไฟล์ในแพ็กเกจ FNIRSI V2.0.7:

```
cd "LPM-10A/Firmware File/rx-sdk"
python -m lpm10rx.container wrap "<path>/APP_LPM-10RX_V3.0.0_260416.bin" APP_LPM-10RX_V3.0.0-update.bin
```

ได้ไฟล์ 32 768 ไบต์ sha256 `33c83bb8f1b92e23613473019247cf8ecb54efa6fa30af397d6e09fea9b6949e` แล้วก๊อปปี้ตามข้อ 1
(ยืนยันแล้วบนเครื่อง 2026-09-21) เวอร์ชัน 3.0.1 ที่เคยมากับเครื่อง**ไม่มีไฟล์ กลับไม่ได้**

## 6. สร้างไฟล์อัปเดตเอง / ตรวจไฟล์

```
python build.py --write                       # PN 1.30 (โปรไฟล์ล่าสุด): ได้ทั้ง .bin และ -update.bin ใน experimental/
python -m lpm10rx.container check <ไฟล์.bin>  # บอกว่าเป็น container (ใช้ได้) หรือ image ดิบ (ใช้ไม่ได้)
```

## 7. แก้ปัญหา

| อาการ | สาเหตุ / ทำอย่างไร |
|---|---|
| ก๊อปปี้แล้วไดรฟ์ยังอยู่ ไม่มีอะไรเกิด, ไฟล์สถานะ `UNKOWN.TXT` | ก๊อปปี้ image ดิบ → ใช้ไฟล์ `-update.bin` |
| ไฟล์สถานะ `APPRUN.TXT` และเครื่องเด้งเข้าแอป | เขียนช้า/สตรีม → ใช้ Explorer ธรรมดา |
| ไดรฟ์ไม่ขึ้น | ต้องปิดเครื่องก่อน แล้วกด SCAN ค้างตอนเสียบ USB; ลองสาย/พอร์ต USB อื่น |
| หลังไดรฟ์หาย เครื่องเงียบ | ปกติ — กดปุ่มเปิด |
| อยากแน่ใจว่าไฟล์ถูกก่อนก๊อปปี้ | `python -m lpm10rx.container check` และเทียบ sha256 กับ `SHA256SUMS.txt` (หน้าโฟลเดอร์) หรือ `experimental/RX-PN1.30-SHA256SUMS.txt` |

ถอด USB ขณะอยู่ในไดรฟ์ (ยังไม่ก๊อปปี้) = เครื่องดับ ไม่มีผลอะไร; การเขียนใช้เวลา ~1 วินาที ไม่พบกรณีเขียนค้าง

---

# English

## 1. The short version

1. Probe off → **hold SCAN** → plug USB into the PC → release SCAN when a drive named **`BOOTLOADER`** appears.
2. **Copy the file whose name ends in `-update.bin`** (e.g. `APP_LPM-10RX_PN1.30-clean-strength-update.bin`)
   onto that drive with **Explorer** (drag-and-drop, Ctrl-C/Ctrl-V or `Copy-Item`).
3. **Within about a second the drive disappears by itself** — the file is programmed and the probe has
   restarted on the new firmware. Unplug USB. (If it is silent, press the power key; PN 1.14+ chirps high→low at boot.)

**Do not**: copy a `.bin` without `-update` (a raw image — the bootloader silently ignores it); use a slow /
sector-by-sector / `dd`-style writer (the bootloader gives up and runs the old application).

## 2. Why updates never worked before, and what was changed

**Root cause:** the RX bootloader only programs a **container** with a 4 KB header — the same layout as
FNIRSI's TX file — but the RX file FNIRSI ships (`APP_LPM-10RX_V3.0.0_260416.bin`) and every PN RX file
before 2026-09-21 were **raw images** (vector table first). The bootloader receives every sector and then
**drops the file silently**; nothing changes and no error is shown. Every RX "device pass" reported for
PN 1.3–1.8 was therefore a test of the factory firmware.

Found by watching the bootloader's SRAM over ST-Link (read-only) while copying files in different ways:
[RX-UPDATE-PROCEDURE-2026-09-21.md](RX-UPDATE-PROCEDURE-2026-09-21.md).

**Repository changes that make updates work:**

| File | Added |
|---|---|
| `rx-sdk/lpm10rx/container.py` | `wrap(raw)` builds the container, `unwrap()` checks/extracts, CLI `python -m lpm10rx.container wrap|check` |
| `rx-sdk/build.py` | every `--write` emits **two files**: `<name>.bin` (raw, for hashes/emulation) and **`<name>-update.bin`** (the container to copy) |
| `rx-sdk/lpm10rx/image.py` | `Image.extend()` appends code after the image (the container carries the payload length) — used since PN 1.14 |
| `rx-sdk/test_container.py` | asserts the layout is byte-exact with the file the probe accepted |

**Container layout** (32 768-byte file for images ≤ 28 KB):

```
offset  size  meaning                                     example (PN 1.19)
0x0000  32    internal ASCII name, zero padded            "APP_LPM-10RX_V3.0.0_260416.bin"
0x0020  u32   payload_off = 0x1000                        00 10 00 00
0x0024  u32   payload_len = raw image size                c8 67 00 00  (= 26 568)
0x0028  u32   payload_end = payload_off + payload_len - 1 c7 77 00 00
0x002C  ..    zeros up to 0x1000
0x1000  ..    raw image (loads at 0x08006800; starts 18 16 00 20 = stack pointer)
  ...         zero padding to a multiple of 4 096
```

The internal name and its version number **do not affect acceptance** (V3.0.0 and V3.0.2 behaved identically),
so the vendor file name is kept, as the TX builds do. No checksum or signature exists in this format.

## 3. Reading the drive's status

The empty `.TXT` on the `BOOTLOADER` drive is the bootloader's **status channel** (Windows may show a stale
name from its cache; the real name appears on a fresh mount or after Eject):

| File | Meaning |
|---|---|
| `PN1.20.TXT` … `PN1.30.TXT` | the installed PN build (from PN 1.20 the application writes its build name to the version page at every boot) |
| `3.0.0.TXT` (or `3.0.1.TXT`, `3.0.2.TXT`) | the factory application, or a PN build before 1.20 (they keep the factory `3.0.0`) |
| `UNKOWN.TXT` | the last file received was **not a container** → dropped, nothing changed |
| `APPRUN.TXT` | a container header arrived but data stopped for >~100 ms (slow writer) → aborted, running the old app |

## 4. Telling which build is installed

From PN 1.20 the status file names the build: open the `BOOTLOADER` drive again (copy nothing) and it shows,
for example, `PN1.30.TXT`. `3.0.0.TXT` means the factory application or a PN build before 1.20; tell those
apart by listening:

| What you hear | Installed |
|---|---|
| steady 50 ms beep / 50 ms gap when a signal is present, one pitch in every mode | factory (V3.0.0 / 3.0.1) |
| 30 ms pulses whose rate rises with strength, one 2.5 kHz pitch for Digital and Analog | PN 1.12 |
| high→low chirp at power-on; Analog one octave below Digital; chirp on mode change | PN 1.14 or later |
| turning the knob does **not** change the rate (only distance to the cable does) | PN 1.15–1.19 |
| touching the cable is the fastest rhythm at every knob position | PN 1.18 / 1.19 |

Exact check: `docs/experiments/rx_ro.py sram` over ST-Link, then compare stack return addresses with the
image's BL sites (method in RX-UPDATE-PROCEDURE).

## 5. Rolling back (an earlier PN build, or factory V3.0.0)

**An earlier PN build:** copy that build's `-update.bin` as in section 1, for example PN 1.29 =
`LPM-10A/Firmware File/archive/APP_LPM-10RX_PN1.29-levels-update.bin` or the file in release rx-v1.29.

**Factory V3.0.0:** the vendor file is not in this repository (project rule). Build the container from the file in FNIRSI's
V2.0.7 package:

```
cd "LPM-10A/Firmware File/rx-sdk"
python -m lpm10rx.container wrap "<path>/APP_LPM-10RX_V3.0.0_260416.bin" APP_LPM-10RX_V3.0.0-update.bin
```

Result: 32 768 bytes, sha256 `33c83bb8f1b92e23613473019247cf8ecb54efa6fa30af397d6e09fea9b6949e`; copy it as in
section 1 (verified on the device 2026-09-21). The 3.0.1 build the probe shipped with has no file and
**cannot be restored**.

## 6. Building or checking an update file

```
python build.py --write                       # PN 1.30 (latest profile): writes .bin and -update.bin to experimental/
python -m lpm10rx.container check <file.bin>  # says whether it is a container (usable) or a raw image (ignored)
```

## 7. Troubleshooting

| Symptom | Cause / what to do |
|---|---|
| copied, drive still there, nothing happens, status `UNKOWN.TXT` | you copied a raw image → use the `-update.bin` |
| status `APPRUN.TXT` and the probe jumped to the app | slow/streamed write → use a plain Explorer copy |
| no drive appears | power off first, hold SCAN while plugging USB; try another cable/port |
| silent after the drive vanished | normal — press the power key |
| want to be sure before copying | `python -m lpm10rx.container check` and compare sha256 with the folder's `SHA256SUMS.txt` or `experimental/RX-PN1.30-SHA256SUMS.txt` |

Unplugging USB while the drive is shown (before copying) just powers the probe off; nothing changes. Programming
takes about one second; no interrupted write has been observed.
