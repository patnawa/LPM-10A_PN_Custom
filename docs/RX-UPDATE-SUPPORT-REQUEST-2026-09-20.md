# FNIRSI RX update clarification — draft

ข้อความพร้อมส่งไปยัง Technical Support ตาม
[หน้าติดต่อ FNIRSI](https://www.fnirsi.com/pages/contact): `support@fnirsi.com`
ยังไม่ได้ส่งข้อความแทนเจ้าของเครื่อง

**Subject: LPM-10A receiver update — BOOTLOADER / 3.0.1.TXT, how to verify acceptance?**

Hello FNIRSI Technical Support,

I need the confirmed firmware-update procedure for the **LPM-10A receiver
probe (RX), which has no display**. Holding SCAN while connecting USB exposes
a Windows drive named BOOTLOADER. Windows identifies it as NATIONS SD Flash
Disk / N32L40X and lists an empty `3.0.1.TXT`. That file can be listed but
cannot be opened normally or made to stay deleted. No formatting was performed.

The official LPM-10A V2.0.7 download contains
`APP_LPM-10RX_V3.0.0_260416.bin`, 26,152 bytes, SHA-256
`083f3825e8f8a38627417e26732e88fd13ee0dbe3c13ca1cd1cd9c4875c7c8c5`.
The package's M+Power/display instructions describe the transmitter, and I
could not find receiver-specific update instructions or an RX V3.0.1 download.

For transparency, I have also tested a custom image based on that RX file,
with a visible startup flashlight indication. Windows reported successful
copies using both a flushed file stream and native file copy, including the
original factory filename. After disconnecting and powering on, the expected
startup indication did not appear; the normal flashlight button still works.
There is no application-flash readback, so I cannot confirm the running version.

Read-only SWD inspection now reports DBG_ID `0x22644017` (N32L406, 128 KiB flash,
24 KiB SRAM), FLASH_OB `0x03FFFFFE` (L1 enabled), and application VTOR `0x08006800`.
Live SRAM data during Digital reception uses different variable addresses from
the V3.0.0 application in your download; it does not match the custom image's
normal execution. No flash/option-byte writes, unlock, or mass erase were performed.
Direct SCSI reads in UDISK currently return an empty `UNKOWN.TXT`, also present
in bootloader RAM, while Windows directory enumeration shows `3.0.1.TXT`.
Neither filename is being treated as authenticated application identity.

A read-only scan of all 51,200 reported 2,048-byte sectors returned only volume
metadata and zero-filled data space, not an application backup. In the returned
filesystem image, BPB FAT2 starts at LBA 15, but its reserved-entry pattern appears
at LBA 27; the two FAT copies differ. Bytes 510–511 of the returned boot sector
are zero. I am reporting these observations without assuming that they cause the
update issue. No format, FAT repair, or raw-sector write was performed.

Please clarify:

1. Does `3.0.1.TXT` identify the application, the bootloader, or something else?
2. Which official RX firmware matches this receiver, and is the supplied
   V3.0.0 RX file compatible? Please provide the applicable official file.
3. What are the exact RX update steps, including button handling, completion
   indication, and how to leave update mode? Does acceptance depend on the
   filename, version, an integrity check, or a hardware revision?
4. How can I confirm the installed RX firmware or obtain a supported readback
   after copying, independently of the Windows file listing?
5. Please provide the matching RX application image for this N32L406 receiver,
   or identify the hardware/revision distinction from the bundled V3.0.0 image.

The underlying issue is Digital tracing audio continuing for about one second
after changing TX from Digital to Analog. The receiver produces repeated short
beeps during that interval; Analog release does not show the same delay. I need
to establish the RX's actual software identity before attributing that behavior
to a particular firmware build.

Thank you.
