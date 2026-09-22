"""Queued Length labels, counters and animation must belong to their visit."""
import contextlib
import io
import struct
import unittest

from thai.engine import Scene
from thai.mockup import sc_home, sc_length_idle


class LengthMessageGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import length_integrity
        import qc_classic
        with contextlib.redirect_stdout(io.StringIO()):
            cls.img = length_integrity.build_candidate()
            cls.parent = qc_classic.build_candidate()
        cls.data = bytes(cls.img.data)

    def scene(self, lang=1):
        s = Scene(image=self.data, lang=lang)
        sc_length_idle(s)
        state = self.img.length_lifecycle['state']
        s.uc.mem_write(state+4, bytes(s.uc.mem_read(state, 4)))
        return s

    def pending_progress(self, s):
        s.w8(0x200002B4, 1)
        s.call(self.img.length_progress['hook'], stack=tuple([0]*12))
        pending, s.msgs = s.msgs, []
        return pending

    def test_queued_testing_label_and_counter_cannot_overwrite_home(self):
        for lang in (1, 2):
            with self.subTest(lang=lang):
                s = self.scene(lang)
                pending = self.pending_progress(s)
                self.assertTrue(pending)
                s.set_state(2)
                sc_home(s, 3)
                before = [row[:] for row in s.fb]
                s.msgs.extend(pending)
                s.drain()
                changed = sum(a != b for old, new in zip(before, s.fb)
                              for a, b in zip(old, new))
                self.assertEqual(changed, 0, 'old Length GUI messages painted the Home screen')

    def test_parent_negative_control_paints_home_after_real_exit(self):
        s = Scene(image=bytes(self.parent.data), lang=1)
        sc_length_idle(s)
        pending = self.pending_progress(s)
        s.set_state(2)
        sc_home(s, 3)
        before = [row[:] for row in s.fb]
        s.msgs.extend(pending)
        s.drain()
        self.assertGreater(sum(a != b for old, new in zip(before, s.fb)
                               for a, b in zip(old, new)), 17000)

    def test_testing_frame_matches_parent_in_english_and_thai(self):
        for lang in (1, 2):
            with self.subTest(lang=lang):
                s = self.scene(lang)
                pending = self.pending_progress(s)
                s.msgs.extend(pending)
                s.drain()
                old = Scene(image=bytes(self.parent.data), lang=lang)
                sc_length_idle(old)
                old.w8(0x200002B4, 1)
                old.call(self.parent.length_progress['hook'], stack=tuple([0]*12))
                old.drain()
                self.assertTrue(s.fb == old.fb, 'first Testing frame changed appearance')

    def test_queued_progress_cannot_overwrite_a_reentered_length_screen(self):
        s = self.scene()
        pending = self.pending_progress(s)
        s.set_state(2)
        s.call(0x08012EE4, 7)  # actual entry resets the visit, unit and reference
        s.drain()
        before = [row[:] for row in s.fb]
        s.msgs.extend(pending)
        s.drain()
        self.assertTrue(s.fb == before)

    def test_text_is_copied_inline_and_never_uses_a_child_heap_pointer(self):
        s = self.scene()
        payload = self.pending_progress(s)
        self.assertEqual([mid for mid, _ in payload], [0x41, 0x40, 0x40])
        self.assertEqual([len(data) for _, data in payload], [4, 40, 40])
        self.assertEqual(payload[-1][1][16:20], b'1/4\0')
        s.uc.mem_write(self.img.length_progress['cell'], b'4/4\0')
        s.msgs.extend(payload)
        s.log.clear()
        s.drain()
        self.assertIn('1/4', [text for kind, text, *_ in s.log if kind == 'ascii'])

    def test_late_producer_and_oversized_or_unsupported_text_post_nothing(self):
        s = self.scene()
        text = self.img.length_message_guard['text']
        pointer = 0x2000D000
        for raw, mode in ((b'x'*23+b'\0', 0x10), (b'x\0', 0x20)):
            s.uc.mem_write(pointer, raw)
            s.call(text, 68, 175, 0x2105, 0xFFFF, stack=(mode, pointer))
            self.assertEqual(s.msgs, [])
        s.set_state(2)
        s.uc.mem_write(pointer, b'Test timeout!!\0')
        s.call(text, 68, 175, 0x2105, 0xFFFF, stack=(0x10, pointer))
        self.assertEqual(s.msgs, [])

    def test_dots_and_timeout_render_like_original_and_ignore_stale_epochs(self):
        for text in ('.  ', '.. ', '...', '   ', 'Test timeout!!'):
            with self.subTest(text=text):
                s = self.scene()
                pointer = 0x2000D000
                s.uc.mem_write(pointer, text.encode()+b'\0')
                s.call(self.img.length_message_guard['text'], 68, 175, 0x2105, 0xFFFF,
                       stack=(0x10, pointer))
                pending, s.msgs = s.msgs, []
                self.assertEqual(len(pending), 1)
                s.msgs.extend(pending)
                s.drain()
                expected = self.scene()
                expected.text_box(68, 175, 0x2105, 0xFFFF, 0x10, text)
                self.assertTrue(s.fb == expected.fb)
                # A newer diagnostic generation must reject even a same-screen message.
                state = self.img.length_lifecycle['state']
                epoch = struct.unpack('<I', s.uc.mem_read(state, 4))[0]
                s.uc.mem_write(state, struct.pack('<I', (epoch+1) & 0xFFFFFFFF))
                s.fb = [[0]*240 for _ in range(320)]
                s.msgs.extend(pending)
                s.drain()
                self.assertFalse(any(any(row) for row in s.fb))


if __name__ == '__main__':
    unittest.main()
