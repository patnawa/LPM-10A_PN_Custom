"""Synthetic-input CPU tests for the opt-in V3.0.0 digital detector.

The actual detector and trimmed_mean run in Unicorn, without ADC/analogue
hardware. Seeded test results do not establish real-world false-alarm rates.
Run `python verify.py --digital` for these plus the full RX verifier.
"""
import math
import random
import struct

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import (
    UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R4,
    UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8,
    UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
)

BASE, ENTRY, STOP, STACK = 0x08006800, 0x08009E08, 0x00100000, 0x20001600
BUFFER, ACTIVE, GATE = 0x2000006E, 0x20000008, 0x20000068
RECENT, BEEP, GAP = 0x2000006C, 0x2000010C, 0x2000005A
SAVED = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
         UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)


def reference(samples):
    mean = (sum(samples) - min(samples) - max(samples)) // 46
    if sum(abs(x - mean) for x in samples) < 192:
        return False
    if 5 + sum(x for x in samples if x > mean) < 1000:
        return False
    bits = [int(x > mean) for x in samples]
    signature = [(0xB6B6 >> (15 - i)) & 1 for i in range(16)]
    if sum(bits[i:i + 16] == signature for i in range(33)) >= 2:
        return True
    for phase in range(8):
        errors = [int(bit != ((0xB6 >> (7 - ((i + phase) % 8))) & 1))
                  for i, bit in enumerate(bits)]
        if sum(errors) <= 4 and all(sum(errors[i:i + 16]) <= 2 for i in (0, 16, 32)):
            return True
    return False


def pattern(phase=0, low=500, high=1500, wrong=()):
    bits = [(0xB6 >> (7 - ((i + phase) % 8))) & 1 for i in range(48)]
    for i in wrong:
        bits[i] ^= 1
    return [high if bit else low for bit in bits]


class Detector:
    def __init__(self, image):
        self.uc = uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        uc.mem_map(0x08000000, 0x20000)
        uc.mem_map(0x20000000, 0x10000)
        uc.mem_map(STOP, 0x1000)
        uc.mem_write(BASE, bytes(image))
        self.steps, self.max_steps, self.overwrite = 0, 0, False
        self.bad_writes = []
        uc.hook_add(UC_HOOK_CODE, self.step)
        uc.hook_add(UC_HOOK_MEM_WRITE, self.write)

    def step(self, uc, addr, size, user):
        self.steps += 1

    def write(self, uc, access, addr, size, value, user):
        if not (STACK - 144 <= addr and addr + size <= STACK) and (addr, size) not in {
                (ACTIVE, 1), (RECENT, 2), (BEEP, 1), (GAP, 1)}:
            self.bad_writes.append((addr, size))
        if addr == ACTIVE and value == 1 and self.overwrite:
            uc.mem_write(BUFFER, bytes(128))

    def run(self, samples, active=0, gate=2, recent=0, overwrite=False):
        if len(samples) != 48 or not all(0 <= x <= 4095 for x in samples):
            raise ValueError('need 48 samples within the 12-bit ADC range')
        uc = self.uc
        uc.mem_write(BUFFER, struct.pack('<48H', *samples) + bytes([0xA5] * 32))
        uc.mem_write(ACTIVE, bytes([active]))
        uc.mem_write(GATE, struct.pack('<H', gate))
        uc.mem_write(RECENT, struct.pack('<H', recent))
        uc.mem_write(BEEP, b'\0')
        uc.mem_write(GAP, b'\0')
        uc.reg_write(UC_ARM_REG_SP, STACK)
        uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        sentinel = [0x12340000 + i for i in range(len(SAVED))]
        for reg, value in zip(SAVED, sentinel):
            uc.reg_write(reg, value)
        self.steps, self.overwrite, self.bad_writes = 0, overwrite, []
        uc.emu_start(ENTRY | 1, STOP, count=12000)
        assert uc.reg_read(UC_ARM_REG_PC) == STOP, 'did not return within instruction budget'
        assert uc.reg_read(UC_ARM_REG_SP) == STACK, 'stack imbalance'
        assert [uc.reg_read(r) for r in SAVED] == sentinel, 'callee-saved register corruption'
        assert not self.bad_writes, f'write outside owned stack / output flags: {self.bad_writes}'
        self.max_steps = max(self.max_steps, self.steps)
        found = uc.mem_read(BEEP, 1)[0] == 50
        if found:
            assert uc.mem_read(GAP, 1)[0] == 50
            assert struct.unpack('<H', uc.mem_read(RECENT, 2))[0] == 800
        return found


def sampled_wave(phase, ratio, noise, rng):
    """Approximate five-read trimmed sampler; times in TX slot units.

    This exercises relative slot timing, not the electrical envelope or the
    real ADC pipeline / preempting battery conversions.
    """
    out = []
    for i in range(48):
        readings = []
        for sub in range(5):
            t = phase + (i + 0.6 + sub * 0.1) * ratio
            bit = (0xB6 >> (7 - (math.floor(t) % 8))) & 1
            readings.append(max(0, min(4095, 1000 + bit * 300 + rng.randint(-noise, noise))))
        out.append((sum(readings) - min(readings) - max(readings)) // 3)
    return out


def run_checks(stock, mod, check):
    old, new = Detector(stock), Detector(mod)
    clean = [pattern(p, low, high) for p in range(8)
             for low, high in ((0, 1000), (500, 1500), (3000, 3100), (0, 4095))]
    check(all(old.run(x) and new.run(x) for x in clean),
          '32 clean patterns: all eight bit phases and four ADC/DC ranges retain detection')
    corrupted = [pattern(p, wrong=(8, 24, 40)) for p in range(8)]
    old_hits = sum(old.run(x) for x in corrupted)
    new_hits = sum(new.run(x) for x in corrupted)
    check(new_hits == 8 and old_hits < new_hits,
          'three distributed bad bits: eight phases recovered', f'stock {old_hits}/8, candidate {new_hits}/8')
    cases = [pattern(p, wrong=(i,)) for p in range(8) for i in range(48)]
    check(all(new.run(x) and reference(x) for x in cases),
          '384 single-bit corruptions accepted at every phase and sample position')
    cases = [pattern(p, wrong=w) for p in range(8) for w in
             ((0, 1, 16, 32), (0, 1, 2), (0, 1, 16, 17, 32), (0, 1, 16, 17, 32, 33))]
    check(all(new.run(x) == reference(x) for x in cases)
          and all(reference(pattern(p, wrong=(0, 1, 16, 32))) for p in range(8)),
          'bounded correlation errors plus retained stock exact-match fallback agree with model')
    contrasts = [pattern(p, 2000, 2000 + d) for p in range(8) for d in (0, 1, 4, 8, 9, 10, 16)]
    check(all(new.run(x) == reference(x) for x in contrasts)
          and not new.run(pattern(0, 2000, 2001)) and new.run(pattern(0, 2000, 2016)),
          'DC-independent contrast floor rejects a one-count imitation, accepts 16-count contrast')

    impostors = [[1500 if ((code >> (7 - (i % 8))) & 1) else 500 for i in range(48)]
                 for code in range(256)]
    hits = [i for i, x in enumerate(impostors) if new.run(x)]
    check(len(hits) == 8 and all(reference(x) == new.run(x) for x in impostors),
          'all 256 repeating 8-bit words: only the eight rotations of B6 accepted')
    negatives = [[level] * 48 for level in (0, 1, 1000, 2048, 4095)]
    negatives += [[500 + i * 50 for i in range(48)], [3000 - i * 50 for i in range(48)]]
    negatives += [[1500 if i == spike else 500 for i in range(48)] for spike in range(48)]
    negatives += [pattern()[:16] + [500] * 32]
    check(not any(new.run(x) for x in negatives),
          'DC, ramps, every single-spike position and a lone 16-bit burst rejected')

    tones = [[round(2000 + 1000 * math.sin(2 * math.pi * (hz * i * 0.005003125 + p / 16)))
              for i in range(48)]
             for hz in (10, 25, 50, 60, 100, 200, 825) for p in range(16)]
    check(not any(new.run(x) for x in tones),
          '112 synthetic single-tone windows (including 50/60 Hz and 825 Hz) rejected')

    rng = random.Random(0xB6B6)
    noise_windows = [[rng.randrange(4096) for _ in range(48)] for _ in range(1024)]
    noise_windows += [[500 + 1000 * rng.randrange(2) for _ in range(48)] for _ in range(1024)]
    answers = [new.run(x) for x in noise_windows]
    check(not any(answers) and answers == [reference(x) for x in noise_windows],
          '2048 seeded noise-only windows: no detection, CPU agrees with independent model')

    waveforms = [sampled_wave(p / 8, ratio, noise, rng)
                 for ratio in (0.98, 0.990718, 1.0, 1.01, 1.02)
                 for p in range(64) for noise in (0, 100)]
    answers = [new.run(x) for x in waveforms]
    old_answers = [old.run(x) for x in waveforms]
    stock_hits = sum(old_answers)
    check(answers == [reference(x) for x in waveforms]
          and all(new_hit or not old_hit for new_hit, old_hit in zip(answers, old_answers)),
          '640 synthetic phase / clock-offset / noise windows: model agreement and detection comparison',
          f'stock {stock_hits}/640, candidate {sum(answers)}/640; not a hardware range test')

    check(not new.run(pattern(), active=1) and new.uc.mem_read(ACTIVE, 1)[0] == 1,
          'in-progress sample window is neither consumed nor restarted')
    check(not new.run(pattern(), gate=1) and new.uc.mem_read(ACTIVE, 1)[0] == 0,
          'existing PA2 gate still suppresses detection below 2')
    check(new.run(pattern(), overwrite=True),
          'ISR may overwrite shared buffer after re-arm: detection uses completed stack snapshot')
    check(not new.run([500] * 48, recent=321)
          and struct.unpack('<H', new.uc.mem_read(RECENT, 2))[0] == 321
          and new.uc.mem_read(ACTIVE, 1)[0] == 1,
          'rejected window re-arms sampling without extending or clearing existing signal hold')
    check(new.max_steps < 12000, 'bounded execution, ABI, <=144-byte stack footprint and write ownership',
          f'max observed {new.max_steps} instructions; not measured CPU cycles')
    spans = ((0x080072A4, 0x08007320), (0x080075F8, 0x08007724), (0x0800AC1C, 0x0800AD98))
    check(all(len(stock[a - BASE:b - BASE]) == b - a
              and stock[a - BASE:b - BASE] == mod[a - BASE:b - BASE] for a, b in spans),
          'ADC access, trimmed sampler and TIM5 sampler/speaker interrupt untouched')
