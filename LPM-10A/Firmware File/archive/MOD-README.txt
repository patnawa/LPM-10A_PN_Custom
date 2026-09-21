================================================================
 LPM-10A PN Custom firmware  PN 2.4   (UNOFFICIAL build)
================================================================

File      : LPM-10A-TX_PN2.4.bin
Version   : PN 2.4  (Settings > About shows "Software:PN 2.4")
Input hash: sha256 29081ccbbd929a884c7c81fb309aa2894ce2ab84e061918538b3ead8e632940b
Result    : sha256 07428e667d765e25d404699ddd45021eb24dc83f45fe6144c2026a5f868f9176
Size      : 393216 bytes = stock + one 4 KB flash page (see below)
Changed   : 8514 bytes differ from stock: the three font tables
            (8132 bytes, rewritten in place; the Chinese table now
            holds 118 Thai cells and, in its 53 unused slots, the Thai
            strings and drawers), 1304 bytes of new code in the unused
            tail of the last flash sector and the appended page
            (payload_len in the header grows by 1304), 114 in the dead
            body of the stock length_convert (reused as code), 4 in
            the header length fields, and the hooks, string stubs and
            strings.  The image name stored inside the file is left
            as stock because the bootloader checks it.

            The file is longer than stock for the first time: the
            872-byte code tail was full, so the build appends one
            4 KB page of zeros (the unit FNIRSI's own file is padded
            to) and uses 432 bytes of it (the PoE and FLASH code).
            The header has no size field beyond the payload length,
            and the bootloader accepted the longer file on the tested
            unit on 2026-09-18 (PN 2.3 flashed and ran).

NOT AN OFFICIAL FNIRSI RELEASE.  Verified by disassembly and CPU
emulation (sdk/verify.py, 235 checks).  PN 2.2 was flashed to a real
unit on 2026-09-18 and every function was tested there, the Thai
interface, the Cable Test fixes and the blind-pair text included.
PN 2.3 was flashed the same day: the bootloader took the longer file,
but its port blink stopped after three or four cycles; PN 2.4 fixed
it and its FLASH passed on the unit the same day (the blink keeps
going, the tester's LED shows orange during the session).  The PoE
screen's supply paths could not be tested (no PoE switch or injector
at hand) and stay emulation-verified only.  Use at your own risk.
Rebuild or audit it yourself with sdk/.

This file only updates the transmitter.  A separate receiver build,
APP_LPM-10RX_PN1.0.bin (see RX-README.txt), exists but must not be
flashed until its update procedure is confirmed; until then keep the
stock receiver firmware from FNIRSI's package.  FNIRSI's own files
(the stock TX and RX images) are not distributed with this mod.

Every measurement formula in the firmware was traced and checked;
see FORMULA-AUDIT.md for the full list with verdicts.

----------------------------------------------------------------
 CHANGES  (PN 2.4, 2.3, 2.2, 2.1, 2.0, 1.3, 1.2, 1.1: 2026-09-18; PN 1.0 2026-09-17)
----------------------------------------------------------------

[FIXED]   FLASH: the blink stopped after three or four cycles (PN 2.4).
        Seen on the unit with PN 2.3.  That blink waited for the link
        without a limit and wrote the PHY's power-up once; if the link
        did not come back (a power-up write the PHY ignored while it
        was still entering power-down, a switch that suspends a
        flapping port, anything) it waited for ever.  Now, while it
        waits, it re-asserts the power-up every 500 ms (stock wrote it
        every second too) and, if the link is still not back 4 s
        after the power-up, power-cycles the PHY again, so the blink
        can never stall; the power-down lasts 1 s, as stock's did.

[CHANGED] FLASH (port blink): a regular blink timed from the link (PN 2.3).
        Stock powered the PHY up for 4 s and down for 1 s on a fixed
        counter that never looked at the link.  Every power-down costs
        the switch its re-link (its break_link_timer of 1.2..1.5 s,
        then auto-negotiation: 2..3 s in all), taken out of the 4 s
        window, so the port LED was lit for whatever was left, and on
        a slow switch not at all.  Now the tester waits for the link,
        holds it 1.5 s from the tick that saw it, drops it and waits
        for it again: the LED on 1.5..2 s every cycle whatever the
        switch, off for the switch's own re-link (about 2..3 s), a
        regular cycle of 4..5 s.  Not faster than stock, but the
        same every time.  These figures come from the code and the
        standard, not from a measurement yet.  The green dot on the
        screen follows within 0.3 s (was 0.8), and the note reads
        "Watch the port / LED on the switch: / it blinks when linked".
        Stock's 10BASE-T only negotiation (the fastest-linking speed)
        is kept.

[FIXED]   Auto Off is now really held during a FLASH blink (PN 2.3).
        PN 1.0 .. 2.2 compared the screen state with 8, which is the
        QC Test screen, not FLASH (6): the symbol table had the two
        swapped, so the hold worked for the SCAN tone only and a port
        blink left running still switched the unit off at 5 / 10 / 15
        min, contrary to what these notes said.  Found by the review
        of the FLASH change; verify.py now tests the right state and
        checks that QC Test is not held.

[FIXED]   PoE screen: live voltage, "Detecting...", "No PoE" (PN 2.3).
        Stock drew the pair voltage once per detection, from the
        sample a tick or two after the first one above 40 V (the
        rising edge), and not again while the screen was shown; and with no
        supply the screen stayed blank, because its 3.5 s "no PoE"
        timeout fires once per power-on (usually before the screen
        is opened) and was never re-armed.  Now the voltage column
        is redrawn every 0.5 s while a supply is present (the result
        rows are not touched, so nothing blinks; every wire of a
        redraw shows one latched sample, so the two wires of a pair
        always agree), it clears the moment the supply goes, the Standard row
        says "Detecting..." on entry and "No PoE" after 3.5 s without
        a supply, every visit (Thai: "กำลังตรวจหา..." / "ไม่พบ PoE"),
        and the value reads "Yes" / "No" instead of "Standar" /
        "UnStandar".  Measurement and classification are unchanged.
        Correction to earlier notes: stock did print the voltage as
        a number ("48.2V"); there never was a bar.

[CHANGED] Length: a pair the PHY could not time reads "< 2 m" (PN 2.2).
        The cable diagnostic cannot time an echo from inside its
        blind zone (about 2 m) and returns 0 for that pair; stock and
        PN 2.1 printed "1-2 = 0.0 m" next to the pairs that did read,
        which looks like a fault.  Seen with a 1 m cable: three pairs
        blind, pair 4-5 a raw 2.2 m (1.7 m after Zero and NVP).  A
        blind pair now prints "< 2 m" ("< 200 cm", "< 7 ft"; Thai
        "< 2 เมตร").  All four blind still says "Out of range".  On a
        long cable a "< 2 m" pair beside pairs reading the full
        length is a pair open within the first two metres.

[FIXED]   Cable Test: Back returns to the Switch / Far end choice (PN 2.1).
        Stock's Back key left the screen from every step; from the
        armed wiremap layout or a result it now goes back to the mode
        selector, and from the selector to Home.  Every other screen's
        Back is unchanged.  Reported from the PN 2.0 hardware test.

[FIXED]   Cable Test: "Result error!!" was hidden under the button (PN 2.1).
        Stock painted the red error line at y 284 and then drew the
        Test Retry button over it; only an "R" and a "!" peeked out.
        The line now sits at y 271, between the wiremap panel and the
        button, and the button (with its Test Start / Test Retry
        label) moved 9 px down to make room.  In Thai the line reads
        ผลลัพธ์ผิดพลาด!!.

[NEW]     Thai user interface (PN 2.0).
        The second language is Thai instead of Chinese, on every
        screen: Settings > Language offers English / ไทย.  Sarabun
        (SIL Open Font License) rendered into 16x16 cells, one per
        consonant cluster, 13 px, drawn proportionally.  The Chinese
        glyph table now holds the 118 Thai cells; every Chinese
        string in the firmware became a 3-byte redirect to its Thai
        text; the messages stock only had in English ("Result
        error!!", "Test timeout!!", "Error!!", "OFF") have Thai
        versions too.  English is byte-for-byte PN 1.3 (proved by
        emulation: all 26 screens identical).  The first-boot
        language picker is back (English / ไทย) and also appears after
        a Factory Reset; PN 1.x skipped it, which left a factory-reset
        unit in Chinese.  docs/THAI-UI.md shows every screen.

[CHANGED] Version reported as PN 2.4.

[CHANGED] SCAN modes named by what they transmit (PN 1.3).
        "Noiseless" ("Silent" since PN 1.0) is now "Digital": the
        454 kHz carrier keyed in the 16-slot 0xB6B6 pattern, 5.05 ms
        per slot, which the LPM-10RX probe decodes in its digital
        mode.  "Normal" is now "825 Hz": the carrier keyed on and off
        at 825 Hz, a plain tone for any analogue probe.  Labels only;
        the signals are unchanged.

[CHANGED] Length test averages four CSD runs (PN 1.2).
        The PHY's cable diagnostic scatters by about +/-0.3 m from
        run to run at 14 m (measured: 14.4 / 14.6 / 15.0 / 14.8 on the
        same cable).  Zero and NVP correct the mean, not the scatter.
        Each Test Start now runs the diagnostic four times and shows,
        per pair, the mean of the runs in which that pair produced a
        reading; the scatter halves.  The test takes four times
        longer; the 20 s timeout is restarted for every run, so a slow
        diagnostic cannot time the whole test out.
        Stock ran once, or twice when the four pairs disagreed.
        The number of runs is a build-time constant (AVG_RUNS in
        sdk/patches.py).

[CHANGED] Version reported as PN 1.2 (superseded by PN 1.3).

[ADDED] Zero calibration for length measurement (PN 1.1).
        The PHY's reading includes its own signal path.  On the unit
        tested, at NVP 69 %, a 2.9 m cable read 3.1..3.7 m over two
        sessions and a 14 m cable 14.4..15.0 m: an offset of roughly
        +0.4..0.6 m that NVP (a factor) cannot remove.
        The Length screen now shows "ZERO 0.0m" left of the Unit box.
        Hold OK for about a second to swap which value UP / DOWN
        adjust (the active one is white, the other grey; a short OK
        press still starts a test); Zero runs 0.0..2.0 m in 0.1 m
        steps.  Readings are redrawn at once.  Saved with the
        other settings; Factory Reset returns to 0.0 m.

          length = (raw - Zero) x NVP / 69

        Calibrate: short cable (3 m) -> set Zero; long cable (15 m+)
        -> set NVP; re-check the short one.  On the unit tested expect
        Zero around 0.4 m and NVP around 68 %.

        Below about 2 m the PHY's value is unreliable (1 m came back
        as 2.4 m or as "Out of range"); the stock blind zone, which
        discards raw readings of 2 m or less before the Zero is
        subtracted, stays.

[CHANGED] The About screen shows this project's address (PN 1.1), github.com/patnawa/LPM-10A_PN_Custom, on the
        line where the vendor site was (6x12 font so it fits).

[FIXED] Auto Off switched the unit off in the middle of a cable trace.
        The idle timer kept counting while the SCAN tone or the FLASH
        port-blink was running, so with Auto Off at 5 / 10 / 15 min
        the tester powered itself down mid-trace.  The timer is now
        held, and restarted, while a tone or blink session is active.
        Everywhere else Auto Off behaves exactly as stock.  (The blink
        half only works from PN 2.3, see above.)

        Correction: mod 1 claimed stock never reset Auto Off on key
        presses.  That was wrong - stock does, on every key event -
        and that redundant patch has been removed.

From mod 3:


[ADDED] NVP calibration for length measurement (PN 1.0).
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
        (Superseded in PN 1.1 by the two-cable Zero + NVP procedure
        above.)

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
    can never trigger (dead code; the window it looks at would flag
    every supply once the units were consistent, so the intent is
    not recoverable).
  * FreeRTOS task-level queue calls made from interrupt handlers
    (likely cause of rare lockups / unexpected shutdowns).
  * TIM2 interrupt above configMAX_SYSCALL_INTERRUPT_PRIORITY.
  * Fault handlers are bare while(1); the independent watchdog
    (~3.3 s) is what recovers the unit after a hard fault.
  * Update container has no CRC or signature.
  * NVP and Zero are not in the Settings menu: its five rows already
    fill the screen, so they live on the Length screen instead.

----------------------------------------------------------------
 HOW TO FLASH
----------------------------------------------------------------

  1. Power the tester off.
  2. Hold M + Power until the firmware update screen appears.
  3. Connect USB-C; a removable drive appears.
  4. Copy LPM-10A-TX_PN2.4.bin onto that drive.
  5. Do NOT unplug during the update.
  6. Long-press Power to shut down, then power on normally.

  If the device refuses the file, rename it to exactly
  LPM-10A-TX_V2.0.7_260610.bin and copy it again - some
  bootloaders match on the filename.  The name stored inside the
  file is unchanged either way.

  Checked on a real unit up to PN 2.2 (2026-09-18): the bootloader
  accepted the file under its own name; every item below passed, and
  Zero 0.4 m / NVP 68 % read a 2.9 m cable right.  PN 2.3: the
  bootloader accepted the 4 KB longer file and the unit runs; its
  FLASH stopped after three or four cycles; PN 2.4's FLASH passed
  (the blink keeps going, the tester's LED orange).  The PoE items
  with a supply could not be checked: no PoE switch or injector was
  available.  Still to check:
    - PoE screen without a cable: "Detecting..." in the Standard row,
      then "No PoE" and a blue LED after about 3.5 s; leave and
      re-enter: the same again (stock stayed blank).
    - PoE screen on a PoE switch port: the result within a second or
      two (Standard : Yes, END or MID, IEEE 802.3AF/AT/BT, Class
      3/4/6/8), the two powered wires reading e.g. 48.2V and updating
      every half second, the return pair 0.0V, the result rows steady,
      both wires of the pair always the same.  Unplug: "No PoE" at once.
    - A passive 12 / 24 V injector, if available: Standard : No,
      "--" for protocol and class.
    - FLASH on a switch port: after "Testing", the note "Watch the
      port / LED on the switch: / it blinks when linked"; the port's
      link LED on about 1.5..2 s, then off about 2..3 s while the
      switch re-links, the same on time every cycle; note the times
      you see (gigabit and 100 Mb switch if both are at hand).  On a
      managed switch the LED may show amber (spanning tree).
      [PN 2.4: passed]
    - FLASH left blinking for longer than Auto Off: the unit stays on
      (PN 1.0 .. 2.2 held Auto Off in SCAN only).
    - A 1 m cable reads "< 2 m" on the blind pairs (or "Out of
      range" when all four are blind), never "0.0 m".
    - Cable Test: Back returns to the Switch / Far end choice from
      the wiremap layout and from a result; the red error line is
      readable above the button.
    - Settings > Language (ภาษา): English / ไทย; every screen follows.
    - In Thai walk through every screen (docs/THAI-UI.md shows what
      to expect): nothing overlaps, tone marks and vowels sit right,
      the Length "กำลังทดสอบ" has its dots to the right, results say
      เมตร / ซม. / ฟุต, no cable gives "เกินช่วงการวัด".
    - Back in English every screen is exactly as PN 1.3.
    - Text everywhere is the new bold sans font.
    - SCAN with the tone on, or FLASH blinking, for longer than the
      Auto Off setting: the unit must stay on; the probe still hears it.
    - Length screen: "ZERO 0.0m" left of the Unit box, "NVP 69%"
      right of it; UP / DOWN change the white one, OK long press
      swaps them, and after a test the four readings follow.
    - Leave the Length screen and come back: unit, NVP, Zero kept.
    - Power off and on: unit, NVP, Zero kept.
    - Measure two cables of different length back to back; the
      second reading must not repeat the first.
