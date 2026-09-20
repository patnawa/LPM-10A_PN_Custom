# RX UDISK RAM inspection — 2026-09-20

The captured bootloader RAM contains a mass-storage USB implementation and the
same `UNKOWN.TXT` name returned in the raw FAT root directory. It does not contain
a recoverable firmware acceptance rule or a result from an upload. No firmware
was copied in this session; the retained USB command/status objects describe a
readiness poll, not an image validation result.

## Scope and source evidence

This report analyzes existing files only. It issued no target commands and made
no firmware, option-byte, flash, or device-memory changes. The owner entered
UDISK mode before the parent investigation captured two complete 24 KB live SRAM
reads, separated by Windows raw-volume reads. Both snapshots reported VTOR
`0x08000000`, DHCSR `0x01010000`, and FLASH_OB `0x03FFFFFE`. The recorded method
used no reset or halt. Each SRAM read took approximately 3.5 seconds, so neither
is atomic and neither provides a complete history of USB transactions.

Artifacts are in `C:\Users\Alpha\Desktop\LPM-10RX-SWD-2026-09-20`:

| File | Bytes | SHA-256 |
|---|---:|---|
| `rx-sram-udisk-before.bin` | 24,576 | `b9f38ef99acda3365150e5685fe7fc33a571e68bc91b61c6d19bd2d79053b193` |
| `rx-sram-udisk-after-reads.bin` | 24,576 | `0b674f4c37e182704b51825124265a82be3561e70e710e1b4db7c1729fa0c4bb` |
| `udisk-root-swd-session.bin` | 16,384 | `52d7bc9c38e7c1095674e74ad9287f946231b6de0629593ee079566155490f81` |
| `udisk-boot-sector-swd-session.bin` | 2,048 | `28a86f2023b8eacdb7120b3d8693654309c3f173704392f8336f7a7f0ceca118` |
| `udisk-data-prefix-swd-session.bin` | 32,768 | `c35020473aed1b4642cd726cad727b63fff2824ad68cedd7ffb73c7cbd890479` |

Acquisition times and register values are retained in
[the session record](experiments/results/rx-swd-udisk-session-2026-09-20.json).
Exact changed bytes and parsed objects are in
[the offline analysis evidence](experiments/results/rx-udisk-ram-analysis-2026-09-20.json).

## Filename and filesystem observations

RAM `0x20000050..0x2000005A` contains the exact 11-byte FAT short-name field
`UNKOWN  TXT`, followed by a zero byte. It is unchanged in both snapshots.
The raw root directory contains only these entries before its end marker:

| Root offset | Name | Attribute | First cluster | File size |
|---|---|---:|---:|---:|
| `0x00` | `UNKOWN.TXT` | `0x20` | 0 | 0 |
| `0x20` | `BOOTLOADER` volume label | `0x08` | 0 | 0 |
| `0x40` | End-of-directory marker | — | — | — |

The supplied 32 KB data-region prefix is entirely zero. The boot-sector BPB
describes 2,048-byte sectors, four sectors per cluster, two reserved sectors,
two FATs of 13 sectors each, and 512 root-directory entries. These fields place
the root at byte 57,344 and data at byte 73,728, agreeing with the acquisition
record. Total sectors are 51,200. This presented geometry is not a statement of
the MCU's physical flash capacity or of how the updater stores files.

No ASCII or UTF-16LE `3.0.1`, `3.0.0`, `APP_LPM`, `APP_`, or `LPM-10RX` string
occurs in either full SRAM snapshot. `3.0.1` also does not occur in this raw root
directory. The absence of a version string does not identify the installed
application version: its source could reside in protected flash, be encoded,
or be accessed only on another path. The meaning of the name `UNKOWN` is not
established by these data; it must not be translated into an invented error code.

Subsequent independent host reads strengthen the directory observation. The
parent used `CreateFileW` with `GENERIC_READ`, `FILE_FLAG_NO_BUFFERING`, and a
page-aligned buffer; its complete 16 KB root matches the initial root byte for
byte. A later `SCSI_PASS_THROUGH_DIRECT` READ(10), LBA 28, returned one 2,048-byte
sector identical to the first sector of both roots, with SCSI status zero and
zero sense bytes. READ CAPACITY(10) returned `0000C7FF 00000800`: last LBA 51,199,
2,048 bytes per sector. These results are documented in
[the OS-unbuffered read record](experiments/results/rx-udisk-os-unbuffered-2026-09-20.json)
and [the direct SCSI read record](experiments/results/rx-udisk-scsi-direct-2026-09-20.json).
This offline inspection independently compared the returned binary files.

Agreement between live target RAM, OS-unbuffered root data, and a direct SCSI
read makes a Python-buffering explanation for `UNKOWN.TXT` insufficient. A
previous Windows display of `3.0.1` remains a separate observation; these data
do not establish its origin, freshness, cache layer, or meaning. They show that
the current device-facing directory read returns `UNKOWN.TXT`, without proving
why it differs from the earlier display.

## USB objects and their limits

Two objects at `0x20000B54` and `0x20000B94` have identical first 31 bytes and
decode as USB mass-storage Command Block Wrappers. A 13-byte Command Status
Wrapper is at `0x20000BB4`. All three objects are unchanged between snapshots:

| Field | Captured value |
|---|---|
| CBW signature | `0x43425355` (`USBC`) |
| CBW/CSW tag | `0xA50D68E0` |
| Transfer length | 0 |
| Flags / LUN | 0 / 0 |
| Command length | 6 |
| Command bytes | `00 00 00 00 00 00` |
| CSW signature | `0x53425355` (`USBS`) |
| CSW residue / status | 0 / 0 |

The signatures, sizes, matching tag, and zero status match the standard
Bulk-Only Transport structures; status zero means the associated command passed.
See [USB-IF Bulk-Only Transport, sections 5.1–5.3](https://www.usb.org/sites/default/files/usbmassbulk_10.pdf).
Opcode zero is TEST UNIT READY, a readiness poll rather than an upload or
firmware verification command; see
[USB-IF Mass Storage Bootability, section 3.4](https://www.usb.org/sites/default/files/usb_msc_boot_1.0.pdf).
These are retained RAM objects, not a packet trace. Their identical contents do
not prove that no other commands ran between reads, or determine whether a
particular Windows read used cached data. Their success status cannot establish
that firmware was accepted, erased, programmed, or verified.

Additional unchanged data support the presence of a Nations-style USB storage
stack: ASCII inquiry-like records contain `NATIONS SD Flash Disk   1.0` and
`NATIONS NAND Flash Disk 1.0` starting at `0x200000B1` and `0x200000D5`.
A descriptor-like object at `0x20000130` starts `1A 03`, followed by UTF-16LE
`N32L40x` and zero padding. These labels do not establish which storage backend
is active or identify an application version.

## What changed after the volume reads

Only 25 of the 24,576 bytes differ, in ten contiguous runs:

| RAM range | Before → after | Bounded interpretation |
|---|---|---|
| `0x20000008..09` | `9B 3B` → `B5 3D` | Word at `0x08` increases from 15,259 to 15,797; its role is not proven |
| `0x20000128` | `0F` → `24` | Unidentified state byte |
| `0x2000012C` | `01` → `10` | Unidentified state byte |
| `0x2000014C` | `AC` → `92` | Unidentified state byte |
| `0x20000150` | `03` → `01` | Unidentified state byte |
| `0x20000354..35D` | `F8 FF FF FF FF FF FF FF FF FF` → ten zero bytes | Plausible sector-buffer content change |
| `0x20001710` | `08` → `00` | Stack-like area, no proven variable identity |
| `0x20001713..17` | `20 78 56 34 12` → five zero bytes | Stack-like area; previous sentinel-like value alone has no command meaning |
| `0x20001730..31` | `01 00` → `00 80` | Stack-like area |
| `0x20001748` | `28` → `20` | Flash-range word changes `0x08003B28` → `0x08003B20`; not a captured PC |

The interval `0x20000354..0x20000B53` is exactly one 2,048-byte logical sector
and immediately precedes the first retained CBW. Before the volume reads, its
first ten bytes resemble a FAT16 reserved/allocated-entry prefix and the other
2,038 bytes are zero. Afterward all 2,048 bytes are zero, compatible with the
zero-filled data region read by the host. Its sector-buffer role is a strong
structural inference, but no code was recovered to prove that allocation or to
assign a specific LBA to either content. No application image is present in
that interval in either capture; other uses of the same buffer remain unknown.

## Pointers and code recovery

RAM contains plausible callback tables with odd Thumb addresses in the protected
boot region. For example, `0x20000158` holds `0x080008AF`; many adjacent entries
hold `0x08003665`; `0x200001A4..0x200001C8` contains multiple `0x080019xx` and
`0x08001Bxx` addresses. These locate candidate bootloader functions if a readable
boot image becomes available. They are pointers, not copied function bodies.

Other entries resemble descriptor-pointer/length pairs: at `0x20000194`,
`0x08004962` is followed by length 18; at `0x2000019C`, `0x08004974` is followed
by length 32. Further pairs point at `0x08004994`, `0x08004998`, `0x080049BE`,
RAM `0x20000130`, and `0x080049E4`. Their sizes and the RAM string object fit USB
descriptor data, but protected pointees were not read. They are not established
application-version or firmware-validation pointers.

No 16-byte window with at least five distinct byte values matches either the
official RX V3.0.0 image or exact PN 1.13 image anywhere in the boot RAM snapshot.
The same method filters trivial zero patterns but cannot exclude shorter,
transformed, different, or bootloader-specific code. RAM above `0x20002000` is
entirely unchanged between these two snapshots and mostly has high byte entropy.
Neither entropy nor a few incidental printable runs establishes encryption,
executable code, or a firmware payload; no such payload was recovered.

## Complete read scan and inconsistent FAT copies

The subsequent [complete SCSI read scan](experiments/results/rx-udisk-complete-read-scan-2026-09-20.json)
covered all 51,200 reported logical sectors, 104,857,600 bytes (100 MiB), using
READ(10) only. The device was later disconnected by the owner and ordinary RX
operation still worked. This additional analysis used the saved files only.

The acquisition retained the two nonzero eight-sector chunks. Reconstructing
the stream from their hash-verified contents and the recorded zero sectors
independently reproduces the full acquisition SHA-256:
`1194d1e3b2f9994d2056a68523c3092beb38348e22dbb3a36375cbd63a5f9d2d`.
Only 93 bytes are nonzero, all in these four sectors:

| LBA | Nonzero bytes | Returned content |
|---:|---:|---|
| 0 | 46 | BPB/boot-sector fields |
| 2 | 4 | `F8 FF FF FF`, then zeros |
| 27 | 4 | `F8 FF FF FF`, then zeros |
| 28 | 39 | `UNKOWN.TXT` and `BOOTLOADER` root entries |

Every other reported sector returned zeros. No application or bootloader
payload is exposed through the ordinary logical-sector reads in this capture.
This is a statement about the presented read interface, not evidence that
physical MCU flash is empty or that a previous write erased it.

Using the BPB's own two reserved sectors, two FATs, 13 sectors per FAT, and
512 root entries gives the following layout:

| Region | BPB-derived LBA interval |
|---|---|
| Reserved | 0–1 |
| First FAT | 2–14 |
| Second FAT | 15–27 |
| Root directory | 28–35 |
| Data | 36–51,199 |

The corresponding data-cluster count is 12,791, so valid data-cluster numbers
are 2 through 12,792. The layout calculations and reserved FAT entry meanings
follow Microsoft's primary FAT specification, version 1.03, sections
"FAT Data Structure" and "FAT Type Determination"; see
[the Microsoft specification mirrored by Florida State University](https://www.cs.fsu.edu/~cop4610t/assignments/project3/spec/fatspec.pdf).

The observed second FAT does **not** match the first. Its expected starting
sector, LBA 15, is entirely zero. The second `F8 FF FF FF` pattern occurs at
LBA 27, the last sector of that FAT region. Therefore, interpreted using the
declared geometry:

- FAT1 entries 0 and 1 are `0xFFF8` and `0xFFFF`, with its other entries zero.
- FAT2 entries 0 and 1 are zero; its entries 12,288 and 12,289 are instead
  `0xFFF8` and `0xFFFF`.
- The two complete 26,624-byte FATs differ in eight bytes, at within-FAT offsets
  `0..3` and `24576..24579`.

Those high FAT2 entries are within the declared data-cluster range. A reader
using that copy would therefore see a different allocation state, as well as
incorrect reserved entries. There is another independent format anomaly:
boot-sector bytes 510 and 511 are `00 00`, whereas the FAT specification requires
`55 AA` there even with logical sectors larger than 512 bytes. The 2,048-byte
sector size itself is an allowed FAT value. These standard rules are from the
same [Microsoft FAT specification, "Boot Sector and BPB" and "FAT Data Structure"](https://www.cs.fsu.edu/~cop4610t/assignments/project3/spec/fatspec.pdf).

These are concrete inconsistencies in the bytes returned by the virtual disk.
They could matter to a host or checker that validates the boot signature or
consults/compares the second FAT. A host that relies on the first FAT could
behave differently. The captures do not show which behavior Windows used
during earlier copies, or whether the updater's write path uses the same sector
mapping as its read projection. Thus they do **not** establish the cause of the
unsuccessful firmware change, identify a source-code bug, or justify repairing
or formatting the virtual drive. No corrective writes were attempted.

## Remaining acceptance questions

No upload occurred, no new candidate image appeared in the root/data capture,
and no proven IAP command/state variable was identified. The evidence therefore
does not determine the required filename, filename prefix, extension handling,
raw versus container format, image length rule, checksum/signature rule,
program destination, sector-order requirements, or commit/eject/reset trigger.
The application/bootloader layout mismatch reported in
[the static RX investigation](RX-UPDATE-STATIC-RE-2026-09-20.md) remains unresolved.

Useful next evidence would be a vendor bootloader image or matching source,
an official update/verification protocol, or a USB packet trace correlated with
a user-authorized ordinary update attempt. Read-only observations of these
small RAM areas can help correlate state with traffic, but cannot replace the
missing validation code. This inspection supplies no basis to bypass read
protection, call arbitrary bootloader pointers, or modify inferred state fields.
