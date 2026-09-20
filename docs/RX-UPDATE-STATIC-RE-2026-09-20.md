# RX update interface: static reverse engineering, 2026-09-20

The official RX application exposes its load address, startup checks, UID binding,
and version-page handling. It does **not** expose the USB bootloader's file
acceptance protocol. No application-wide checksum, update-entry command, or USB
updater was identified in this image. This is a static application audit, not a
bootloader dump or confirmation that a modified image was installed.

## Exact input and scope

Examined the local official file:

`C:\Users\Alpha\Documents\GitHub\LPM-10A_FNIRSI_originals\APP_LPM-10RX_V3.0.0_260416.bin`

- Size: **26,152 bytes** (`0x6628`).
- SHA-256: `083f3825e8f8a38627417e26732e88fd13ee0dbe3c13ca1cd1cd9c4875c7c8c5`.
- Raw application addresses: `0x08006800` through `0x0800CE27` inclusive.
- The preceding region, `0x08000000..0x080067FF`, is absent from this file.
- Inspected Thumb instructions, vectors, constant references, flash-operation
  callers, initialized data, and the scatter-loading table. No hardware commands,
  firmware changes, or protection changes were performed for this audit.

The physical device currently exposes SWD/SRAM access but flash reads fault,
according to the separate live investigation. Those observations do not turn this
local stock binary into a readback of the installed application. In particular,
`3.0.1.TXT` on the virtual disk has not been mapped to an application version by
the evidence below.

## Startup, vectors, and RAM

| Evidence in the stock image | Observed behavior |
|---|---|
| Vector word at `0x08006800` | Initial stack pointer `0x20001618`. |
| Reset vector at `0x08006804` | Thumb entry `0x0800695D`; reset code calls `SystemInit`, then the C runtime. |
| `SystemInit`, final store at `0x0800A904` | Initially writes **`0x08000000`** to SCB VTOR. This corrects the earlier symbol comment that attributed application-vector relocation directly to `SystemInit`. |
| `main` at `0x0800B70C`; call at `0x0800B71A` | Masks interrupts and calls `0x080087C8`, which writes **`0x08006800`** to VTOR. Application relocation is completed here before normal interrupts start. |
| Scatter loader `0x08006DDC`; table `0x0800CDEC` | Copies `0x18` bytes from `0x0800CE10` to `0x20000000`. |
| Second table entry `0x0800CDFC` | Clears `0x1600` bytes at `0x20000018`, ending at `0x20001617`. |
| External interrupt vectors | IRQ 25 points to TIM1 at `0x0800A97C`; IRQ 50 to TIM5 at `0x0800AC1C`. All other external vectors in the 82-word table point to the default loop. No active USB ISR is present. |
| Startup stores `0x0800B8C6..0x0800B8EE` | Sets the beep counter to 100, temporarily sets mode 1, enables timer IRQs, delays, then stores mode 0. |

The copied 24-byte data area contains initialized program state: an error word,
the 64 MHz clock value, sampling-active state, and cipher parameters. It consumes
the file's final bytes. It is not an unexplained update footer.

Useful **stock-layout** RAM addresses for interpreting read-only snapshots:

| Address | Size | Meaning recovered from code |
|---|---:|---|
| `0x20000004` | 4 | `SystemCoreClock`, initially 64,000,000. |
| `0x20000008` | 1 | Sampling-active state. |
| `0x2000000C` | 8 | Cipher parameters; replaced from the external binding record during startup. |
| `0x20000030` | 24 | RCC clock-frequency results. |
| `0x20000048` | 1 | Selected receive mode: 0 Digital, 1 Analog, 2 mains. |
| `0x20000056` | 1 | Battery state. |
| `0x2000005A` | 1 | Gap counter between Digital beeps. |
| `0x2000005B`, `0x2000005C` | 1 each | Digital and Analog sample indices. |
| `0x20000068`, `0x2000006A` | 2 each | Digital and Analog gate levels. |
| `0x2000006C` | 2 | Recent-signal countdown. |
| `0x2000006E` | 128 | Sample buffer. |
| `0x200000EE` | 1 | Digital sampling substep. |
| `0x200000FC`, `0x20000100` | 4 each | TIM1 and TIM5 interrupt counters. |
| `0x20000104` | 4 | Idle counter. |
| `0x2000010A` | 2 | Power-key hold counter. |
| `0x2000010C` | 1 | Beep countdown. |
| `0x2000010E`, `0x20000110`, `0x20000112` | 2 each | Mode, mains, and lamp key hold counters. |

No update-request RAM global was identified. The initial copy/clear also means a
bootloader cannot rely on this application's ordinary globals preserving a prior
RAM flag through C startup. This does not rule out a bootloader-private flag in
another location. PN patches reuse some padding bytes; an unknown installed
revision could use a different layout. RAM resemblance alone cannot authenticate
a version.

## External flash records and the application's write paths

| Routine / call sites | Exact input and behavior | Update implication |
|---|---|---|
| UID-binding check `0x0800BAE8`, called at `0x0800B860` | Reads chip UID words at `0x1FFFF7F0..0x1FFFF7FB` and the record beginning `0x08006700`. Loads its first 8 bytes into cipher state. Decodes 16 bytes at record +8 and compares 12 bytes with the UID. | This binds the device record to the chip; it is not a checksum over the application image. |
| Conditional initialization inside the same check, `0x0800BB2A..0x0800BB5E` | If the record's first word is not `0xFFFFFFFF`, copies its 24 bytes, changes that first word to `0xFFFFFFFF`, encodes the 12-byte UID into the copy, and calls `0x08008524`. | Application startup can modify the external binding record under this condition. Do not invoke this routine manually from a debugger. |
| Binding-record writer `0x08008524` | Erases the page at `0x08006000`, writes six words at `0x08006700`, then writes `0x2E33565F` (`_V3.` in byte order) at `0x0800676C`. | The writer touches a page below the application. This is a specific record-initialization path, not a general application updater. |
| Boot-tag check `0x08007C20`, called at `0x0800B876` | Reads only byte `0x0800676E` and requires ASCII `3` (`0x33`); returns 1 otherwise. Main loops if it returns 1. | Confirms one application-side compatibility test. It does not show whether the USB bootloader checks filenames or the same tag. |
| Version-page check `0x0800B388`, called at `0x0800B89E` | Compares the six bytes `3.0.0\0` at image address `0x0800CDE4` with the page at `0x0801F000`. On mismatch, prepares a padded copy and calls the writer at `0x0800B924`. | The stock application records its own version after reaching this point in startup. A virtual-disk filename's relationship to this page remains unknown. |
| Version-page writer `0x0800B924` | Erases `0x0801F000`, writes the supplied words, and relocks flash. For this version string the caller supplies three words, including padding. | No application-image programming range is involved. |

The direct callers of page erase (`0x080079D8`) are `0x08008544` and
`0x0800B93C`. Direct callers of word programming (`0x08007AF8`) are
`0x0800857A`, `0x080085B0`, and `0x0800B972`. These belong to the two record
writers above. No reachable application rewrite loop or transfer to a bootloader
update entry was identified. The routines are generic flash primitives, but
their mere presence does not establish an updater command interface.

Main also samples PB2 and PB1 before normal startup and waits for PC13 release.
The exact early branches help interpret a powered but uninitialized application:

- `0x0800B780..0x0800B7BA` samples PB2 five times, counting low readings. At least
  three low readings select the special branch at `0x0800B7C6`.
- Its loop at `0x0800B7D8` reads PB2 and PB1. Both high cause PB8 to be cleared at
  `0x0800B818`, followed by an infinite loop at `0x0800B81E`. Other combinations
  remain in a delay/poll loop. PB2 high when inspected later therefore does not
  by itself exclude earlier qualification for this branch.
- The normal branch calls `power_on_latch` at `0x0800B844`, setting PB8 high,
  then waits for PC13 high at `0x0800B84A..0x0800B85E` before the UID/tag checks.
- The UID and tag failure loops are at `0x0800B874` and `0x0800B88A`, respectively,
  before timer initialization at `0x0800B8B2`.

The GPIO descriptions above use actual N32 register semantics: helper
`0x08008170` writes PBC to clear bits; `0x08008184` writes PBSC to set bits. Older
symbol names inverted those labels. The PB1/PB2 branch has no identified
USB/file-processing work; its physical role needs the schematic. Do not relabel
it as the update-entry condition. These branches describe the stock code and
do not establish where the current physical device is executing.

## What can and cannot be concluded about image acceptance

**Established about this application:** its linked base, reset entry, stack
pointer, initialized-data boundaries, boot-tag test, binding-record use, and
version-page writes. Modified images have retained its size and vector table;
that is a conservative construction choice, not proof of bootloader acceptance.

**No in-file checksum field identified:** the reserved vector slots are zero and
the first eight words sum to `0x50033A92`, not zero. The final word is initialized
RAM data, not an unexplained CRC. CRC32 over all preceding bytes is `0xA7819E55`,
whereas that word is zero. These observations exclude specific obvious layouts;
they do not prove absence of bootloader validation.

**Still unknown:** accepted filenames, allowed file sizes/versions, FAT write
ordering or close/flush requirements, completion indication, meaning of
`3.0.1.TXT`, and any checksum/signature/compatibility rules implemented outside
this image. The statement “the bootloader writes the file as-is” is not supported
by this audit. Successful Windows copying is not application flash verification.

Non-destructive next steps:

1. Read SCB VTOR and repeated small SRAM snapshots while the device runs. Compare
   counter and mode behavior against the stock layout as a compatibility check;
   retain raw bytes and timestamps rather than assigning an unverified version.
2. Correlate existing USB observations with a captured normal file-transfer
   sequence and explicit physical completion behavior. A USB capture can show
   host/device protocol responses but still cannot replace flash readback.
3. Seek a vendor-provided RX bootloader image, supported verification command,
   exact RX update specification, or another accessible official package. A
   genuine bootloader binary would permit acceptance-rule analysis without
   changing this device's protection state.
4. Keep the current read-protection setting, binding page, and application intact.
   Do not use unlock, mass erase, option-byte writes, or debugger calls into the
   flash-writing routines to obtain a dump.

## Existing live SRAM capture: limited content inspection

Also inspected the already captured file
`C:\Users\Alpha\Desktop\LPM-10RX-SWD-2026-09-20\rx-sram-live-2206.bin`.
It is 24,576 bytes, SHA-256
`673e3bacad0e1d01321ad0eed70a64a1ab2b3eceea8a1a2299a1d84108a59a8b`.
The parent investigation identifies this as an unhalted live read around 22:07;
it is not an atomic snapshot. This inspection issued no additional target reads.

- No `BOOTLOADER`, `APP_`, `3.0.0`, `3.0.1`, `FAT12`, `FAT16`, `USBC`, `USBS`,
  or `N32` byte string was found. No meaningful updater label was found in the
  printable ASCII or UTF-16LE runs.
- An exhaustive 16-byte-window comparison found no match to the stock image
  among windows containing at least five distinct byte values. This filters
  trivial zero patterns; it does not exclude transformed, short, or different
  firmware code/data in RAM.
- Most bytes in the stock ordinary-global/BSS area were zero, with stack-area
  activity and high nonzero density above approximately `0x20001F00`. Unused SRAM
  contents are not evidence of encryption, a bootloader buffer, or executable
  code. Runtime-state interpretation is being handled separately.

This capture yielded no recoverable USB update packet, filename rule, or copied
stock application code. It cannot substitute for protected flash readback.

## Existing local packages do not supply the missing updater

Inspected the existing archive
`C:\Users\Alpha\Downloads\Compressed\LPM-10A_Firmware_V2.0.7.zip`
(SHA-256 `9eb4d55844fa195d4d63501a78aede2a22623eea863d8f98776a694721d8c96d`).
Its only binaries are the exact RX input above and the official TX image. Other
entries are directories, a changelog, and a README; there is no bootloader file.

| Local image | Layout inspection | Result for RX updater research |
|---|---|---|
| Official TX `LPM-10A-TX_V2.0.7_260610.bin`, 389,120 bytes; SHA-256 `29081ccbbd929a884c7c81fb309aa2894ce2ab84e061918538b3ead8e632940b` | First 44 bytes are an image-name/offset/length/end header. Bytes `0x2C..0xFFF` are all zero. Payload starts at file `0x1000`, with SP `0x2000E888` and reset vector `0x0800A34D`, linked at `0x0800A000`. Its payload length is `0x5DC98`; all bytes after that payload are zero padding. | The 4 KB prefix is a container header, not bootloader machine code. No preceding flash region is supplied. |
| TX PN 2.14, 393,216 bytes; SHA-256 `a7402de6f18e39df55bbe53f5641efd5135f0de4d81f9407515cf9d8710c5527` | Same container/payload start and vector location; application payload extended by our patches. Only one plausible vector table was found, at file `0x1000`. | The larger file is not a full-chip image or newly recovered bootloader. |
| Existing `LPM-10C_Firmware_V1.1.2.zip`, image `APP_LPM-10C_V1.1.2_251118.bin`, 408,948 bytes; image SHA-256 `2f9b0012abfc277c70263935b0b8e319315d568c668b8eef348e79fd284ac2d5` | Raw application starts with SP `0x2000F278` and reset `0x0800A34D`. The code at file `0x34C` matches that reset entry when linked at `0x0800A000`. No second plausible vector table was found. | Another device's application, not an RX bootloader dump. No shared updater implementation was identified. |

`BOOTLOADER`, `UNKOWN`, `NATIONS`, `FAT12`, `FAT16`, and `LPM-10RX` strings were
absent from these TX/LPM-10C images. The TX images also lacked `USBC`/`USBS` mass
storage signatures. Absence of strings alone does not prove absence of code,
but the validated application boundaries and empty TX container prefix provide
no bootloader implementation to disassemble. No RX filename parser or sector
commit rule can be recovered from these packages on this evidence. No additional
downloads or device changes were made.

Related evidence: [RX application audit](RX-AUDIT.md),
[video and USB diagnosis](TONE-CLIP-DIAGNOSIS-2026-09-20.md), and
[device feedback chronology](TONE-DEVICE-FEEDBACK-2026-09-20.md).

## Live Digital RAM layout differs from every stored RX application

This is a bounded comparison of already captured RAM with local binaries; it
issued no hardware commands and changed no firmware. The capture is
`C:\Users\Alpha\Desktop\LPM-10RX-SWD-2026-09-20\digital-pause-20260920-221932.jsonl`,
SHA-256 `b925f22b2a3d0c368e97c2296b763bb66329ec478ac04383d66ea9bd5ad686b3`.
It contains 2,348 rows spanning approximately 40.0066 seconds. The capture writer
at `docs/experiments/rx_swd_runtime_capture.py` reads the raw `state_hex` bytes
directly from `0x20000048`, length 40; the separate raw `sram_0ec_0fb_hex` block
starts at `0x200000EC`, length 16. These are actual hardware read addresses,
not addresses inferred from the field names. No two-byte slicing offset was
found in the writer. The two reads in each row are not atomic.

All 16 available RX images were inspected: official V3.0.0, PN 1.0 through
PN 1.13, and the PN 1.13 lamp identity diagnostic. All are 26,152 bytes. Their
SHA-256 hashes, instruction bytes/disassembly, scheduler groups, and full raw-byte
histograms are recorded in
[the comparison evidence](experiments/results/rx-live-abi-comparison-2026-09-20.json).
No image in that set changes the following four pairs of actual sampler
instructions; they are byte-identical to the official stock image:

| Code address | Actual instructions | RAM role in all stored images |
|---|---|---|
| `0x0800760E` | `movw r0, #0xEE; movt r0, #0x2000` | Digital subsample step at `0x200000EE` |
| `0x08007668` | `movw r0, #0xF0; movt r0, #0x2000` | Digital subsample buffer at `0x200000F0` |
| `0x08007676` | `movw r1, #0x5B; movt r1, #0x2000` | Digital sample index at `0x2000005B` |
| `0x08007680` | `movw r3, #0x6E; movt r3, #0x2000` | Digital sample buffer at `0x2000006E` |

The stored Digital schedulers also consistently use GAP `0x2000005A` and RECENT
`0x2000006C`. This was checked against the binaries, not only Python constants:
stock and PN 1.0–1.2 construct those addresses at `0x08007734` and `0x08007744`;
PN 1.3–1.5 use literals at `0x08007758` and `0x0800775C`; PN 1.6 uses the mode
base `0x20000048` from `0x08007764`, plus offsets `0x24` and `0x12`; PN 1.7 onward
use that mode base from `0x08007768`, plus `0x24`, and the GAP literal at
`0x0800776C`.

The observed raw bytes have a different pattern:

| RAM location | Observed across all 2,348 rows | Meaning for this comparison |
|---|---|---|
| Byte `0x20000048` | Always 0 | Matches the known images' Digital mode value |
| Bytes `0x2000005A` and `0x2000005B` | Both always 0 | Known GAP and Digital index are inactive |
| Byte `0x2000005C` | Every integer 0–50; frequently 50 | Behaves like a countdown at a different address; exact role remains inferred |
| Byte `0x2000005D` | Every integer 0–47 | Behaves like a 48-sample index at a different address |
| Halfword `0x2000006C` | Always 2 | Does not resemble the known RECENT countdown |
| Halfword `0x2000006E` | 0–800 | Behaves like the RECENT countdown at a different address |
| Bytes `0x200000EE` and `0x200000EF` | Both always 0 | Known subsample step and patched sampling gate are inactive |
| Byte `0x200000F0` | Every integer 0–10 | Behaves like a subsample step at a different address |

The apparent alternative field roles are hypotheses. This evidence does not
justify shifting every subsequent structure field by two bytes: other areas
and alignment differ, while the timer-counter addresses still match.

PN 1.13 provides an additional direct check. Its scheduler at
`0x08007736..0x08007748` requires byte `0x200000EF` to equal 2 and halfword
`0x2000006C` to exceed 500 before starting Digital audio. Those locations are
respectively 0 and 2 in every captured row. Its publisher at `0x08009F3E`
loads 800 and stores it at `0x2000006C` at `0x08009F42`; the live value with a
0–800 range is instead at `0x2000006E`. Its Digital pulse starter writes 100
for an uncertain result at `0x080086F6`, or 30 for an ordinary result at
`0x080086FC`, to BEEP `0x2000010C`. Its TIM5 countdown helper uses the GAP
literal `0x2000005A` at `0x0800AA10`. These are constraints of the exact local
PN 1.13 machine code, not configurable runtime choices.

The consistent state pattern over thousands of reads is incompatible with
normal Digital execution using the RAM layout of any stored RX profile and is
strong evidence that the exact PN 1.13 image is not the application currently
executing. Non-atomic reads can miss individual transitions, but do not explain
this sustained combination of inactive expected fields and active adjacent
fields. This conclusion assumes the ordinary application is executing without
unobserved RAM corruption or external writes. It identifies neither the
installed version nor its complete layout. Protected application flash has not
been read, and this comparison cannot establish whether the cause is a
different vendor build, update rejection, a different selected application, or
another bootloader behavior. Further patches derived from the stored layout
should not be treated as validated on this device until that mismatch is
resolved.
