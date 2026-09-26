"""Independent read-only RX artifact/new-tail audit after Analog dropout A/B.

Host image integrity and a simulated absent tail cannot verify real flash.
Only in-memory copies have their appended bytes replaced; no release is edited.
"""
import contextlib
import hashlib
import io
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
SDK = ROOT / 'LPM-10A/Firmware File/rx-sdk'
sys.path.insert(0, str(SDK))

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ
import clean_strength as strength
import rx_resilient
import test_rx_publication_commit as publication
import test_rx_followup as followup
import level_display
from lpm10rx import symbols
from lpm10rx.container import wrap, unwrap
from verify_digital import RECENT, ACTIVE
from verify_control import BEEP


class LayoutAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.old = strength.build_candidate()
            cls.img = rx_resilient.build_candidate()
            publication.PublicationCommit.setUpClass()
        cls.old_data, cls.data = bytes(cls.old.data), bytes(cls.img.data)

    def test_published_containers_payloads_and_direct_tail_caller(self):
        base = symbols.APP_BASE
        for version, data, expected_hash in (
            ('PN1.30', self.old_data, rx_resilient.PARENT_SHA256),
            ('PN1.31', self.data, '3e03d8ac13884a0fb3ad752b551ad346eb8e77e11998d7be9ca599923752094c'),
        ):
            packed = wrap(data)
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected_hash)
            self.assertEqual(unwrap(packed)[1], data)
            self.assertLess(base + len(data), symbols.EXTEND_LIMIT)
            print(version, 'raw', len(data), 'container', len(packed),
                  'flash-end-exclusive', hex(base + len(data)),
                  'header', tuple(hex(v) for v in struct.unpack_from('<III', packed, 0x20)))
        self.assertEqual((rx_resilient.DIRECTORY / rx_resilient.OUTPUT).read_bytes(), self.data)
        self.assertEqual((rx_resilient.DIRECTORY / rx_resilient.UPDATE).read_bytes(), wrap(self.data))
        # Decode every halfword-aligned potential instruction, not a linear
        # disassembly beginning with non-code vector-table data.
        low, high = base + len(self.old_data), base + len(self.data)
        decoder = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
        inbound = []
        for offset in range(0, len(self.data) - 3, 2):
            ins = next(decoder.disasm(self.data[offset:offset+4], base + offset), None)
            if ins and ins.mnemonic in ('bl', 'b.w', 'b') and ins.op_str.startswith('#'):
                target = int(ins.op_str[1:], 0)
                if low <= target < high:
                    inbound.append((ins.address, ins.mnemonic, target))
        self.assertEqual(inbound, [(0x08009EFA, 'bl', low)])
        print('Only potential direct branch into appended code: Digital',
              [(hex(a), op, hex(t)) for a, op, t in inbound])

    def test_analog_has_no_new_tail_dependency_in_fresh_or_sustained_feedback(self):
        h = publication.PublicationCommit()
        h.img = self.img
        base = symbols.APP_BASE
        tail = base + len(self.old_data)
        cases = 0
        for sustained in (False, True):
            for kind in ('normal', 'clipped', 'rejected'):
                outputs = []
                for fill in (None, 0, 255):
                    h.data = self.data if fill is None else (
                        self.data[:len(self.old_data)] + bytes([fill]) * (len(self.data)-len(self.old_data)))
                    cpu = h.ready(1, sustained=sustained,
                                  clipped=kind == 'clipped', rejected=kind == 'rejected')
                    hits = []
                    cpu.uc.hook_add(UC_HOOK_CODE,
                        lambda uc, a, s, u: hits.append(('execute', a)),
                        begin=tail, end=base+len(self.data)-1)
                    cpu.uc.hook_add(UC_HOOK_MEM_READ,
                        lambda uc, access, a, s, v, u: hits.append(('read', a)),
                        begin=tail, end=base+len(self.data)-1)
                    h.analyze(cpu)
                    self.assertEqual(hits, [])
                    outputs.append(tuple(cpu.read(address, size) for address, size in (
                        (followup.GRADE, 1), (RECENT, 2), (level_display.AVERAGE, 4),
                        (level_display.AVERAGE+4, 1), (ACTIVE, 1), (BEEP, 1),
                        (strength.LAST_DISPLAYED, 4))))
                    cases += 1
                self.assertEqual(outputs[0], outputs[1])
                self.assertEqual(outputs[0], outputs[2])
        print(cases, 'real Analog analyzer cases: full/zero/erased-FF tails identical; no tail access')


if __name__ == '__main__':
    unittest.main(verbosity=2)
