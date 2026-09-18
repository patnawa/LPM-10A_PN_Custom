================================================================
 LPM-10A receiver (probe) firmware  PN 1.0   (UNOFFICIAL build)
================================================================

File      : APP_LPM-10RX_PN1.0.bin
Built from: APP_LPM-10RX_V3.0.0_260416.bin  (official FNIRSI V3.0.0)
            sha256 083f3825e8f8a38627417e26732e88fd13ee0dbe3c13ca1cd1cd9c4875c7c8c5
Result    : sha256 419c52a04a0e9a840b405669fc51aa785659e41bda3296caac62f37ebc7d1244
Size      : 26152 bytes (identical to stock; raw image, no container)
Changed   : 28 bytes, one in-place edit inside the battery routine.

NOT AN OFFICIAL FNIRSI RELEASE.  Verified by disassembly and CPU
emulation (rx-sdk/verify.py, 25 checks); NOT tested on hardware.
FNIRSI's own files are not distributed with this build.

!! THE RECEIVER FLASHING PROCEDURE HAS NOT BEEN CONFIRMED HERE.  Do
!! not flash this until the update mode and the way back to stock are
!! confirmed on a real probe.  The stock file is the only recovery.
!!
!! Reported procedure (from the internet, 2026-09-18, unverified):
!!   probe powered off -> hold SCAN and plug in the USB cable -> the
!!   probe appears as a USB drive -> copy the receiver .bin onto it
!!   -> unplug -> it updates.
!! If you want to establish it, do it with FNIRSI's OWN stock file
!! first (APP_LPM-10RX_V3.0.0_260416.bin from the official package):
!! that proves both the entry into update mode and the way back
!! without risking anything.  The bootloader may also insist on the
!! stock file name, as the transmitter's does.
!!
!! Is it worth it?  Not really: this build changes only the
!! low-battery shutdown of the probe.  Every PN transmitter firmware
!! works with the stock probe firmware.

----------------------------------------------------------------
 CHANGES  (PN 1.0, 2026-09-17)
----------------------------------------------------------------

[FIXED] Critical-battery shutdown could not be cancelled.
        The probe reads its battery every 0.5 s.  One reading below
        3280 mV (a beep burst is exactly the load that dips a tired
        cell for one reading) entered a critical state that powered
        the probe off 2.5 s later no matter what the voltage did
        afterwards.  Now each reading at or above 3400 mV returns to
        the normal low-battery state and clears the counter, so only
        five consecutive readings (2.5 s) below 3400 mV switch the
        probe off.  The low-battery LED thresholds (3579 / 3621 mV)
        and the shutdown timing on a genuinely flat pack are unchanged.

Everything else is stock: tone decoding, the three modes, the
speaker, the keys, the 5-minute auto-off (which is already held
while a tone is being received), the UID-binding check at power-on.

----------------------------------------------------------------
 KNOWN, NOT CHANGED  (see docs/RX-AUDIT.md)
----------------------------------------------------------------

  * The digital decoder is an exact 16-bit match with no tolerance
    for clock drift, and the receiver's 5 ms sample is 0.94 % shorter
    than the transmitter's slot by construction; expect intermittent
    beeping even when the probe is still.  The fix is a proper
    correlator; it needs bench time.
  * No signal-strength indication in the digital mode.
  * The third key is a 50/60 Hz mains detector, not a tone mode; the
    second tone mode listens for the transmitter's ~825 Hz cadence.

----------------------------------------------------------------
 VERIFY THIS FILE
----------------------------------------------------------------

  certutil -hashfile APP_LPM-10RX_PN1.0.bin SHA256
  -> 419c52a04a0e9a840b405669fc51aa785659e41bda3296caac62f37ebc7d1244
