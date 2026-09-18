"""Render every LPM-10A screen three ways: English, Chinese (stock strings) and
Thai, from the real draw code of the PN build without thai-ui (the Thai text drawn by
the model that the thai-ui patch implements; verify.py proves the two agree).

    python -m thai.mockup [screen ids]       THAI_PX=13 for the 13 px font
"""
import os
import sys
import json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from thai.engine import Scene, ThaiFont      # noqa: E402

from thai.wording import TH, ASCII_TH      # noqa: E402

from thai.cells import Table                  # noqa: E402
FONTS_OUT = os.path.join(os.path.dirname(HERE), "fonts_out")
SIZE = os.environ.get("THAI_PX", "table")
if SIZE == "table":
    FONT = Table.shipped(FONTS_OUT)                # the cells exactly as the firmware carries them
    OUT = os.path.join(HERE, "out")
else:
    FONT = ThaiFont(size=int(SIZE), baseline=int(SIZE) + 1, below_lift=1)
    OUT = os.path.join(HERE, f"out{SIZE}")
os.makedirs(OUT, exist_ok=True)


def scene(lang, thai, **kw):
    return Scene(lang=lang, thai=(TH if thai else None), ascii_thai=(ASCII_TH if thai else None), font=FONT, **kw)


# ---------------------------------------------------------------- scenarios
def sc_language_picker(s):
    s.w8(0x2000013C, 3)
    s.call(0x08010B68); s.drain()
    s.call(0x08010D34); s.drain()


def sc_home(s, sel):
    s.w8(0x2000013D, sel)
    s.call(0x08015BC4); s.call(0x0800F0C0); s.call(0x0801932C); s.call(0x0800F100, 0); s.call(0x0800E6B0)
    s.drain()


def sc_cable_test_a(s, mode=0):
    s.w8(0x20000010, mode)
    s.set_state(4)
    s.call(0x0800C300); s.drain()


def sc_cable_test_b(s, retry=0):
    s.w8(0x20000010, 0)
    s.w8(0x20000012, retry)
    s.set_state(4)
    s.post(0x10); s.post(0x12); s.drain()


def sc_cable_result(s, mode=0, wires=None):
    """The wire-map result: msg 0x11 with the layout flag set runs the real result drawer
    (switch 0x0800CB68 / far end 0x0800C4E0) with the ADC stubbed; `wires` forces the
    per-wire result codes (4 = error) at the point the drawer has measured them."""
    s.w8(0x20000010, mode | 0x10); s.w8(0x20000012, 1)
    s.set_state(4)
    s.post(0x10); s.drain()
    if wires:
        for addr in (0x0800C71E, 0x0800CCA0):
            s.at[addr] = lambda uc, w=bytes(wires): uc.mem_write(0x2000023E, w)
    s.post(0x11); s.drain()


def sc_cable_result_switch(s):
    sc_cable_result(s, 0)


def sc_cable_result_farend(s):
    sc_cable_result(s, 1)


def sc_scan(s, mode=1, enable=1, phase=1):
    s.w8(0x200000D0, enable, mode, 0, 0, phase)
    s.set_state(5)
    s.post(0x09); s.post(0x0A); s.post(0x0B); s.drain()


def sc_flash_testing(s):
    s.set_state(6)
    s.w8(0x200002B4 + 1, 0)
    s.call(0x0800D47C)
    s.drain(skip=(0x1F,))


def sc_flash_note(s):
    sc_flash_testing(s)
    s.drain()
    s.call(0x0800EF40, 91, 116, 18, 0); s.drain()


def sc_length_idle(s, unit=0):
    s.w8(0x200002C0, unit)
    s.w8(0x20000C78 + 0xA6, 68); s.w8(0x20000C78 + 0xC5, 4)      # the tested unit's calibration
    s.set_state(7)
    s.post(0x19); s.drain()


def sc_length_testing(s):
    sc_length_idle(s)
    s.call(0x08019C38); s.drain()
    s.text_box(68, 175, 0x2105, 0xFFFF, 0x10, ".. ")


def sc_length_result(s, cm=(1399, 1399, 1399, 1399)):
    sc_length_idle(s)
    s.w16(0x200002B8, *cm)
    s.w8(0x200002B4, 2)
    s.post(0x1A); s.drain()


def sc_length_timeout(s):
    sc_length_testing(s)
    s.text_box(68, 175, 0x2105, 0xFFFF, 0x10, "Test timeout!!")


def sc_qc_test(s):
    s.set_state(8)
    s.post(0x0C); s.drain()


def sc_qc_uncal(s):
    sc_qc_test(s)
    s.post(0x0E); s.drain()


def sc_speed_idle(s, retry=0):
    s.w8(0x20000075, retry); s.w8(0x200002B4, 0)
    s.set_state(9)
    s.post(0x1D); s.drain()


def sc_speed_testing(s):
    sc_speed_idle(s)
    s.call(0x0801B06C); s.drain()
    s.text_box(68, 67, 0x2105, 0xFFFF, 0x10, ".. ")


def sc_speed_result(s, reg11=0x8000 | 0x2000, retries=0):
    sc_speed_idle(s, retry=1)
    s.w8(0x20000074, retries)
    s.w16(0x200002B6, reg11); s.w8(0x200002B4, 3)
    s.call(0x0801A9A8); s.drain()


def sc_speed_timeout(s):
    sc_speed_testing(s)
    s.vals["tick_step"] = 5000
    s.w8(0x200002B4 + 1, 0)
    s.call(0x0800D47C); s.drain()


# PoE task data: the 2 KB sample ring at 0x2000045D is followed by the result struct
POE_STD, POE_PROTO, POE_SPAN, POE_CLASS = 0x20000C5D, 0x20000C5F, 0x20000C60, 0x20000C62
POE_MV, POE_ADC, POE_ADC_MIN = 0x200000C0, 0x200000B4, 0x200000BE


def poe_live_cell(s):
    """The poe-screen patch's RAM cell (tick counter, partial-redraw flag, last span) of the build
    the scene runs: the reference build for the model, the full default build otherwise (a built
    image is byte-identical to it, verify.py section 2)."""
    from thai.engine import reference_build
    return reference_build(() if s.source != "reference" else ("thai-ui",)).poe["live"]


def sc_poe(s, values=True, std=2, span=1, proto=2, mv=48200, cls=4, adc=None):
    """Enter the POE screen (msg 0x13: the frame, the eight wires, "Detecting..." while no span
    is known), then, with `values`, post the task's result message 0x14 as the state machine
    does once it has classified the supply: poe_mv is the pair-to-pair spread in mV, cls the
    comparator class code (3/4/6/8), adc the four channel readings (only span 5 draws them)."""
    s.set_state(10)
    s.post(0x13); s.drain()
    if values:
        s.w16(POE_MV, mv); s.w8(POE_CLASS, cls)
        if adc:
            s.w16(POE_ADC, *adc); s.w16(POE_ADC_MIN, min(adc))
        s.w8(POE_STD, std); s.w8(POE_SPAN, span); s.w8(POE_PROTO, proto)
        s.post(0x14); s.drain()


def sc_poe_live(s, mv2=53100):
    """A live refresh: the tick hook set the partial flag and posted 0x14; only the voltage
    column is redrawn (the result rows are left as they are)."""
    sc_poe(s)
    s.w16(POE_MV, mv2)
    s.w8(poe_live_cell(s) + 1, 1)
    s.post(0x14); s.drain()


def sc_settings(s, item=1, autooff=0):
    s.w8(0x2000013E, item); s.w8(0x2000013F, 0)
    s.w8(0x20000C78 + 0xA2, autooff)
    s.set_state(11)
    s.post(0x32); s.drain()


def sc_about(s):
    s.w8(0x2000013F, 1)
    s.set_state(11)
    s.post(0x34); s.drain()


def sc_factory_reset(s, flag=2):
    sc_about(s)
    s.w8(0x2000013F, flag)
    s.post(0x35); s.drain()


def sc_lowbatt(s, ctr=25):
    sc_home(s, 4)
    s.vals["mv"] = 3100; s.vals["shutdown"] = 1
    s.call(0x0800E834); s.drain()
    s.w8(0x2000003D, ctr)
    s.call(0x0800DCF0); s.drain()


def sc_dots(s, which):
    sc_speed_idle(s)
    s.call(0x0801B06C); s.drain()
    s.text_box(68, 67, 0x2105, 0xFFFF, 0x10, which)


def sc_length_result_unit(s, unit):
    sc_length_idle(s, unit=unit)
    s.w16(0x200002B8, 1399, 1399, 1399, 1399)
    s.w8(0x200002B4, 2)
    s.post(0x1A); s.drain()


SCREENS = [
    ("language_picker", "Language picker (first boot)", sc_language_picker, {}),
    ("home_1", "Home, page 1", sc_home, dict(sel=4)),
    ("home_2", "Home, page 2", sc_home, dict(sel=8)),
    ("cable_test_mode", "Cable Test: mode selector", sc_cable_test_a, dict(mode=1)),
    ("cable_test_armed", "Cable Test: ready", sc_cable_test_b, {}),
    ("cable_test_result_switch", "Cable Test: result (switch)", sc_cable_result_switch, {}),
    ("cable_test_result_farend", "Cable Test: result (far end)", sc_cable_result_farend, {}),
    ("scan", "SCAN", sc_scan, {}),
    ("flash_testing", "FLASH: testing", sc_flash_testing, {}),
    ("flash_note", "FLASH: link up", sc_flash_note, {}),
    ("length_idle", "Length: ready", sc_length_idle, {}),
    ("length_testing", "Length: testing", sc_length_testing, {}),
    ("length_result", "Length: result", sc_length_result, {}),
    ("length_out_of_range", "Length: out of range", sc_length_result, dict(cm=(0, 0, 0, 0))),
    ("length_blind_pairs", "Length: 1 m cable, three pairs blind", sc_length_result, dict(cm=(0, 0, 215, 0))),
    ("length_timeout", "Length: timeout", sc_length_timeout, {}),
    ("qc_test", "QC Test", sc_qc_test, {}),
    ("qc_test_uncalibrated", "QC Test: not calibrated", sc_qc_uncal, {}),
    ("speed_idle", "SPEED: ready", sc_speed_idle, {}),
    ("speed_testing", "SPEED: testing", sc_speed_testing, {}),
    ("speed_result", "SPEED: result", sc_speed_result, {}),
    ("speed_timeout", "SPEED: connect timeout", sc_speed_timeout, {}),
    ("poe_detecting", "POE: detecting", sc_poe, dict(values=False)),
    ("poe", "POE: 802.3at, 48.2 V", sc_poe, {}),
    ("poe_none", "POE: no supply after 3.5 s", sc_poe, dict(std=0, span=0, mv=0)),
    ("settings", "Settings", sc_settings, {}),
    ("about", "About", sc_about, {}),
    ("factory_reset", "Factory reset", sc_factory_reset, {}),
    ("lowbatt", "Low battery", sc_lowbatt, {}),
]

# More states of the same screens: not in the docs sheets, but part of the verify.py
# comparison so that every string, every hook entry and every stub is drawn at least once.
EXTRA_SCREENS = [
    ("cable_result_switch_error", "Cable Test: switch result with a bad wire", sc_cable_result, dict(mode=0, wires=[4, 1, 1, 1, 1, 1, 1, 1, 1])),
    ("cable_result_farend_error", "Cable Test: far-end result with bad wires", sc_cable_result, dict(mode=1, wires=[1, 4, 2, 3, 1, 1, 1, 1, 1])),
    ("cable_test_mode0", "Cable Test: mode selector, Switch", sc_cable_test_a, dict(mode=0)),
    ("cable_test_retry", "Cable Test: ready, retry label", sc_cable_test_b, dict(retry=1)),
    ("home_sel5", "Home page 1, tile 2", sc_home, dict(sel=5)),
    ("home_sel9", "Home page 2, tile 2", sc_home, dict(sel=9)),
    ("scan_mode2", "SCAN: 825 Hz selected", sc_scan, dict(mode=2)),
    ("scan_off", "SCAN: tone off", sc_scan, dict(enable=0)),
    ("length_idle_cm", "Length: ready, cm", sc_length_idle, dict(unit=1)),
    ("length_idle_ft", "Length: ready, ft", sc_length_idle, dict(unit=2)),
    ("length_result_cm", "Length: result in cm", sc_length_result_unit, dict(unit=1)),
    ("length_result_ft", "Length: result in ft", sc_length_result_unit, dict(unit=2)),
    ("dots0", "SPEED: testing, no dots", sc_dots, dict(which="   ")),
    ("dots1", "SPEED: testing, one dot", sc_dots, dict(which=".  ")),
    ("dots3", "SPEED: testing, three dots", sc_dots, dict(which="...")),
    ("speed_half_1000", "SPEED: 1000 half", sc_speed_result, dict(reg11=0x8000)),
    ("speed_full_100", "SPEED: 100 full", sc_speed_result, dict(reg11=0x4000 | 0x2000)),
    ("speed_half_100", "SPEED: 100 half", sc_speed_result, dict(reg11=0x4000)),
    ("speed_10", "SPEED: 10 half", sc_speed_result, dict(reg11=0x2000)),
    ("speed_error", "SPEED: Error!!", sc_speed_result, dict(reg11=0xC000, retries=1)),
    ("poe_unstd_mid", "POE: non-standard, mid-span", sc_poe, dict(std=1, span=3, proto=0, mv=24100)),
    ("poe_std_mid", "POE: standard, mid-span (802.3at)", sc_poe, dict(std=2, span=4, proto=2, cls=4, mv=54000)),
    ("poe_std_end2", "POE: standard, end-span reversed", sc_poe, dict(std=2, span=2, proto=1, cls=3, mv=47900)),
    ("poe_both", "POE: both pair sets powered (span 5)", sc_poe, dict(std=2, span=5, proto=3, cls=6, mv=52000,
                                                                     adc=(1620, 30, 1590, 25))),
    ("poe_live", "POE: live refresh, 53.1 V", sc_poe_live, {}),
    ("settings_5min", "Settings: Auto Off 5 min", sc_settings, dict(item=4, autooff=1)),
    ("settings_10min", "Settings: Auto Off 10 min", sc_settings, dict(item=4, autooff=2)),
    ("settings_15min", "Settings: Auto Off 15 min", sc_settings, dict(item=4, autooff=3)),
    ("settings_item0", "Settings: no row selected", sc_settings, dict(item=0)),
    ("settings_item2", "Settings: Light selected", sc_settings, dict(item=2)),
    ("factory_reset_yes", "Factory reset: YES selected", sc_factory_reset, dict(flag=3)),
    ("lowbatt_5", "Low battery: 5 s left", sc_lowbatt, dict(ctr=5)),
]
ALL_SCREENS = SCREENS + EXTRA_SCREENS


def render(ids=None, langs=("en", "zh", "th"), screens=None):
    report = {}
    for sid, title, fn, kw in (screens or SCREENS):
        if ids and sid not in ids:
            continue
        for tag in langs:
            lang, thai = {"en": (1, False), "zh": (2, False), "th": (2, True)}[tag]
            s = scene(lang, thai)
            try:
                fn(s, **kw)
                err = None
            except Exception as e:                       # keep going, note the failure
                err = repr(e)
            s.image(2).save(os.path.join(OUT, f"{sid}_{tag}.png"))
            report[f"{sid}_{tag}"] = dict(err=err, missing=s.missing,
                                          text=[(k, t, x, y) for k, t, x, y, fg, ex in s.log if k != "ascii" or tag == "en"])
            print(sid, tag, "ERR " + err if err else "ok", s.missing or "")
    json.dump(report, open(os.path.join(OUT, "report.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return report


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ids = sys.argv[1:] or None
    render(ids, screens=ALL_SCREENS if ids else SCREENS)
