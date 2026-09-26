"""Owner Analog-drop diagnosis: real RX timers/analyzer/speaker, modeled link.

Run from any directory. No firmware is written. Compare exact released PN1.30
and PN1.31; optional TIM1/TIM5 delivery pauses and resumes the real analyzer at
an instruction boundary, respecting PRIMASK. The injected millisecond advances
the same sampling clock used by the outer loop. This is not a hardware replay.
"""
from pathlib import Path
import argparse
import contextlib
import hashlib
import io
import json
import sys

SDK = Path(__file__).resolve().parents[3] / 'LPM-10A' / 'Firmware File' / 'rx-sdk'
sys.path.insert(0, str(SDK))

from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_PRIMASK, UC_ARM_REG_SP
import auto_range
import clean_strength
import rx_resilient
from test_rx_isolate import FieldCPU, Streams, T1_CYCLES, T5_CYCLES, TIM1, PWM
from test_rx_followup import ANALYZERS, GRADE
from test_scan_acquisition_timing import TIMER_COUNTER
from verify_control import SP, STOP
from verify_digital import ACTIVE, RECENT


class Runner(Streams):
    def probe(self, data, *, knob, amplitude, end_ms, irq_point=None, step=None, limit=2400):
        c = FieldCPU(data, mode=1, knob=knob, limit=limit)
        c.amplitude = lambda tick: amplitude if step is None or tick*T5_CYCLES/64000 < 700 else step
        self.boundary(c)
        edges, levels, publications = [], [], []
        sound, interrupted, ticks = False, 0, 0

        def milliseconds():
            return c.read(TIMER_COUNTER, 4)*T5_CYCLES/64000

        def tick():
            nonlocal ticks
            self.assertEqual(c.uc.reg_read(UC_ARM_REG_PRIMASK), 0)
            before = c.read(auto_range.STATE)
            ticks += 1
            count = ticks*T1_CYCLES//T5_CYCLES-c.read(TIMER_COUNTER, 4)
            self.timers(c, count)
            self.execute(c, TIM1, stack=SP-0x500, budget=10000)
            if c.read(auto_range.STATE) != before:
                levels.append((round(milliseconds(), 3), before, c.read(auto_range.STATE)))

        def analyze():
            nonlocal interrupted
            if irq_point is None:
                self.execute(c, ANALYZERS[1], budget=150000)
                return
            pending, stopped = False, []
            def pause(uc, address, size, user):
                nonlocal pending
                if address == irq_point:
                    pending = True
                if pending and not uc.reg_read(UC_ARM_REG_PRIMASK):
                    stopped.append(address)
                    uc.emu_stop()
            h = c.uc.hook_add(UC_HOOK_CODE, pause)
            c.uc.reg_write(UC_ARM_REG_SP, SP)
            c.uc.reg_write(UC_ARM_REG_LR, STOP|1)
            try:
                c.uc.emu_start(ANALYZERS[1]|1, STOP, count=150000)
            finally:
                c.uc.hook_del(h)
            if stopped:
                self.assertEqual(len(stopped), 1)
                saved = c.uc.context_save()
                tick()
                c.uc.context_restore(saved)
                c.uc.emu_start(stopped[0]|1, STOP, count=150000)
                interrupted += 1
            self.assertEqual(c.uc.reg_read(UC_ARM_REG_PC), STOP)
            self.assertEqual(c.uc.reg_read(UC_ARM_REG_SP), SP)

        def pwm(uc, access, address, size, value, user):
            nonlocal sound
            active = value != 800
            if active != sound:
                edges.append((milliseconds(), active))
                sound = active

        hook = c.uc.hook_add(UC_HOOK_MEM_WRITE, pwm, begin=PWM, end=PWM+1)
        try:
            while milliseconds() < end_ms:
                tick()
                self.boundary(c)
                if not c.read(ACTIVE):
                    analyze()
                    publications.append((round(milliseconds(), 3), c.read(GRADE), c.read(RECENT, 2)))
        finally:
            c.uc.hook_del(hook)
        if irq_point is not None:
            self.assertGreater(interrupted, 0, 'requested instruction was never reached')
        row = dict(edges=edges, levels=levels, publications=publications, end_ms=milliseconds())
        # Include no-sound and end-of-run silence. Only the first400ms are
        # settling time; silence crossing that boundary must still be counted.
        transitions = [(0.0, False), *edges, (milliseconds(), False)]
        gaps = [(b-max(a, 400), max(a, 400), b)
                for (a, on), (b, _) in zip(transitions, transitions[1:])
                if not on and b > max(a, 400)]
        return dict(sound_ms=round(self.sounding(row, 400, end_ms), 3),
                    longest_quiet_ms=round(max((x[0] for x in gaps), default=0), 3),
                    largest_gaps=sorted(gaps, reverse=True)[:3], gains=levels,
                    accepted=sum(recent > 500 for _, _, recent in publications),
                    rejected=sum(recent <= 500 for _, _, recent in publications),
                    first_edges=edges[:4], last_edges=edges[-4:], interrupts=interrupted)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--knob', type=int, default=4095)
    p.add_argument('--amp', type=float, nargs='+', default=[30, 100, 300, 900, 2000, 10000, 30000])
    p.add_argument('--end', type=int, default=1600)
    p.add_argument('--irq', type=lambda x: int(x, 0))
    p.add_argument('--step', type=float)
    p.add_argument('--limit', type=float, default=2400, help='modeled front-end peak-to-peak limiter before ADC rail clipping')
    p.add_argument('--max-quiet', type=float, help='fail if either build exceeds this post-settle silent interval in milliseconds')
    args = p.parse_args()
    with contextlib.redirect_stdout(io.StringIO()):
        images = [('PN1.30', bytes(clean_strength.build_candidate().data)),
                  ('PN1.31', bytes(rx_resilient.build_candidate().data))]
    runner = Runner()
    for amplitude in args.amp:
        rows = []
        for name, data in images:
            row = runner.probe(data, knob=args.knob, amplitude=amplitude, end_ms=args.end,
                               irq_point=args.irq, step=args.step, limit=args.limit)
            rows.append(row)
            print(json.dumps(dict(version=name, sha256=hashlib.sha256(data).hexdigest(),
                                  knob=args.knob, amplitude=amplitude, irq=args.irq, **row)), flush=True)
        print('IDENTICAL', rows[0] == rows[1], flush=True)
        if args.max_quiet is not None:
            for (name, _), row in zip(images, rows):
                if row['longest_quiet_ms'] > args.max_quiet:
                    raise AssertionError(f'{name}: silent interval {row["longest_quiet_ms"]} exceeds {args.max_quiet}ms')


if __name__ == '__main__':
    main()
