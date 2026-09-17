================================================================
 LPM-10A PN Custom firmware  PN 1.0   (UNOFFICIAL build)
================================================================

File      : LPM-10A-TX_PN1.0.bin
Version   : PN 1.0  (Settings > About shows "Software:PN 1.0")
Built from: LPM-10A-TX_V2.0.7_260610.bin  (official FNIRSI V2.0.7)
            sha256 29081ccbbd929a884c7c81fb309aa2894ce2ab84e061918538b3ead8e632940b
Result    : sha256 6c1c8fa726857942e476f834b24cf94782db31fc6542dfa72e1f0baa7b67b1e0
Size      : 389120 bytes (identical to stock)
Changed   : 6430 bytes: 8132 of font data replaced in place, 588 bytes
            of new code in the unused tail of the last flash sector
            (payload_len in the header grows to match), the rest are
            hooks and strings.  The image name stored inside the file
            is left as stock because the bootloader checks it.

NOT AN OFFICIAL FNIRSI RELEASE.  Verified by disassembly and CPU
emulation (sdk/verify.py, 96 checks); NOT tested on hardware.
Use at your own risk.  Rebuild or audit it yourself with sdk/.

The RX firmware APP_LPM-10RX_V3.0.0_260416.bin is NOT modified; use
the one from FNIRSI's package.  FNIRSI's own files (the stock TX and
RX images) are not distributed with this mod.

Every measurement formula in the firmware was traced and checked;
see FORMULA-AUDIT.md for the full list with verdicts.

----------------------------------------------------------------
 CHANGES  (PN 1.0, 2026-09-17; development history mod 1..4)
----------------------------------------------------------------

[FIXED] Auto Off switched the unit off in the middle of a cable trace.
        The idle timer kept counting while the SCAN tone or the FLASH
        port-blink was running, so with Auto Off at 5 / 10 / 15 min
        the tester powered itself down mid-trace.  The timer is now
        held, and restarted, while a tone or blink session is active.
        Everywhere else Auto Off behaves exactly as stock.

        Correction: mod 1 claimed stock never reset Auto Off on key
        presses.  That was wrong - stock does, on every key event -
        and that redundant patch has been removed.

[CHANGED] Version reported as PN 1.0 (About screen and boot log).

From mod 3:


[ADDED] NVP calibration for length measurement.
        Professional testers let you set the cable's Nominal Velocity
        of Propagation; stock had no calibration at all.  On the
        Length screen press UP / DOWN (hold for auto-repeat) to set
        NVP from 50 % to 99 %.  The value is shown as "NVP 69%" to the
        right of the Unit box and the four pair lengths are redrawn
        at once with the new factor, so you do not have to re-measure
        while adjusting.  69 % is the factory value (= the PHY's own
        calibration, identical to stock).  It is saved with the other
        settings at power-off; Factory Reset puts it back to 69 %.

        To calibrate: measure a cable of known length, then press
        UP / DOWN until the display reads its true length.

[CHANGED] Length unit is remembered.
        Stock forced centimetres every time the Length screen was
        opened.  The chosen unit (m / cm / ft) is now kept, also
        across power cycles.  Default is metres.

[CHANGED] New on-screen fonts, English and Chinese.
        The thin serif 8x16 ASCII font seen on every dev board is
        replaced by Ubuntu Sans Mono (semi-bold) at 8x16 and 6x12,
        and all 171 Chinese glyphs are re-rendered in Droid Sans
        Fallback, a modern sans (Hei) design, instead of the Song
        bitmap.  Same cell sizes, same layout, so every screen keeps
        its positions.  Both fonts are open-licensed (Ubuntu Font
        Licence 1.0 / Apache 2.0); see sdk/fonts.py.

From mod 2:

[CHANGED] Length is shown with one decimal (m / cm / ft).
[FIXED] Length result stuck to the previous cable.
[FIXED] Low-battery shutdown from a single noisy ADC sample.
[CHANGED] Battery gauge has 10 steps instead of 4.
[FIXED] 204 bytes of heap leaked on every settings save.

From mod 1:

[CHANGED] Boots straight to English.
[CHANGED] Corrected machine-translated English text.

----------------------------------------------------------------
 VERIFIED CORRECT, LEFT AS-IS
----------------------------------------------------------------

  * Battery voltage: mV = ADC * 2 * 3300 / 4096
  * PoE voltage:     mV = (max - min ADC) * 3300 * 40 / 4096
  * Link speed/duplex from PHY register 0x11 bits 15:14 / 13
  * Inch constant 2.54 (exact) in the stock conversion
  * Auto-off table 0 / 300 / 600 / 900 s

----------------------------------------------------------------
 NOT CHANGED (needs a rebuild from vendor source, or hardware)
----------------------------------------------------------------

  * Cables under 2 m read "Out of range" (PHY blind zone).
  * PoE "unstable supply" check compares byte data with 40000 and
    can never trigger (dead code; intended threshold unknown).
  * FreeRTOS task-level queue calls made from interrupt handlers
    (likely cause of rare lockups / unexpected shutdowns).
  * TIM2 interrupt above configMAX_SYSCALL_INTERRUPT_PRIORITY.
  * Fault handlers are bare while(1); the independent watchdog
    (~3.3 s) is what recovers the unit after a hard fault.
  * Update container has no CRC or signature.
  * NVP is not in the Settings menu: its five rows already fill the
    screen, so it lives on the Length screen instead.

----------------------------------------------------------------
 HOW TO FLASH
----------------------------------------------------------------

  1. Power the tester off.
  2. Hold M + Power until the firmware update screen appears.
  3. Connect USB-C; a removable drive appears.
  4. Copy LPM-10A-TX_PN1.0.bin onto that drive.
  5. Do NOT unplug during the update.
  6. Long-press Power to shut down, then power on normally.

  If the device refuses the file, rename it to exactly
  LPM-10A-TX_V2.0.7_260610.bin and copy it again - some
  bootloaders match on the filename.  The name stored inside the
  file is unchanged either way.

  First things to check on a real unit (none of this has been):
    - Text everywhere is the new bold sans font; Chinese mode too.
    - SCAN with the tone on, or FLASH blinking, for longer than the
      Auto Off setting: the unit must stay on.
    - Length screen: "NVP 69%" right of the Unit box; UP / DOWN
      change it and, after a test, the four readings follow.
    - Leave the Length screen and come back: unit and NVP kept.
    - Power off and on: unit and NVP kept.
    - Measure two cables of different length back to back; the
      second reading must not repeat the first.
    - Battery icon shows intermediate levels while discharging.
    - Change a setting ~10 times in a row; the unit must stay
      responsive (heap fix).

----------------------------------------------------------------
 HOW TO GO BACK TO STOCK
----------------------------------------------------------------

  Same procedure, copy the original LPM-10A-TX_V2.0.7_260610.bin from
  FNIRSI's official V2.0.7 package (https://www.fnirsi.com).
  The bootloader is in a separate flash region that is never
  touched, so the update screen stays reachable.  Settings written
  by the mod (NVP, unit) sit in bytes the stock firmware ignores.

----------------------------------------------------------------
 VERIFY THIS FILE
----------------------------------------------------------------

  certutil -hashfile LPM-10A-TX_PN1.0.bin SHA256
  -> 6c1c8fa726857942e476f834b24cf94782db31fc6542dfa72e1f0baa7b67b1e0
