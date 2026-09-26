"""Existing functional contracts rerun against the integrated PN2.34 image.

These suites cover the shared key, state-transition and GUI hooks composed by
Cable Test. Historical tests continue to build their own immutable releases.
"""
import contextlib
import io
from functools import lru_cache
import unittest

import test_length_audit_lifecycle as length
import test_length_message_guard as text
import test_qc_gate_timing as qc
import test_speed_partner_validity as speed
import test_tone_alignment as tone
import test_tone_pn226_lifecycle as keys


@lru_cache(maxsize=1)
def candidate():
    import cable_session
    with contextlib.redirect_stdout(io.StringIO()):
        return cable_session.build_candidate()


class CurrentImage:
    @classmethod
    def setUpClass(cls):
        cls.img = candidate()
        cls.data = bytes(cls.img.data)


class CurrentLength(CurrentImage, length.LengthLifecycle):
    pass


class CurrentLengthMessages(CurrentImage, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import cable_safe
        with contextlib.redirect_stdout(io.StringIO()):
            cls.parent = cable_safe.build_candidate()

    scene = text.LengthMessageGuard.scene
    pending_progress = text.LengthMessageGuard.pending_progress
    test_queued_progress_after_home = text.LengthMessageGuard.test_queued_testing_label_and_counter_cannot_overwrite_home
    test_queued_progress_after_reentry = text.LengthMessageGuard.test_queued_progress_cannot_overwrite_a_reentered_length_screen
    test_testing_frame_matches_parent = text.LengthMessageGuard.test_testing_frame_matches_parent_in_english_and_thai
    test_text_payload_and_current_progress = text.LengthMessageGuard.test_text_is_copied_inline_and_never_uses_a_child_heap_pointer
    test_invalid_or_late_text = text.LengthMessageGuard.test_late_producer_and_oversized_or_unsupported_text_post_nothing
    test_dots_timeout_and_stale_epoch = text.LengthMessageGuard.test_dots_and_timeout_render_like_original_and_ignore_stale_epochs


class CurrentQC(CurrentImage, qc.QCGateTiming):
    pass


class CurrentSpeed(CurrentImage, unittest.TestCase):
    scene = speed.SpeedPartnerValidity.scene
    value = speed.SpeedPartnerValidity.value
    test_valid_abilities = speed.SpeedPartnerValidity.test_valid_abilities_and_no_autoneg_are_unchanged
    test_unknown_clears_and_recovers = speed.SpeedPartnerValidity.test_unknown_clears_previous_wide_value_and_recovers
    test_retry_and_error = speed.SpeedPartnerValidity.test_retry_and_error_do_not_show_unknown
    test_screen_rebuild = speed.SpeedPartnerValidity.test_screen_rebuild_uses_checked_partner_value_in_both_languages
    test_failed_read_then_recovery = speed.SpeedPartnerValidity.test_failed_read_after_valid_result_and_next_read_recover_without_stale_abilities


class CurrentTone(CurrentImage, unittest.TestCase):
    machine = tone.ToneAlignment.machine
    test_analog_period_and_duty = tone.ToneAlignment.test_alignment_repeats_33_cycles_every_400_ticks_at_half_duty
    test_phase_boundaries = tone.ToneAlignment.test_every_valid_phase_and_invalid_halfword_recover_without_legacy_state
    test_residue_classes = tone.ToneAlignment.test_all_five_phase_residue_classes_have_same_period_and_duty
    test_disabled_phase = tone.ToneAlignment.test_disabled_direct_entry_does_not_advance_even_invalid_phase
    test_pause_resume_mode_and_exit = tone.ToneAlignment.test_pause_resume_mode_switch_and_home_exit_preserve_cursor
    test_inactive_unknown_and_spurious_irq = tone.ToneAlignment.test_inactive_screen_unknown_mode_and_spurious_irq_leave_phase_untouched
    test_analog_ram_and_interrupts = tone.ToneAlignment.test_analog_only_ram_write_abi_and_interrupt_mask_contract


class CurrentToneKeys(CurrentImage, unittest.TestCase):
    machine = keys.ToneLifecycle.machine
    press = keys.ToneLifecycle.press
    assert_next_tick = keys.ToneLifecycle.assert_next_tick
    test_real_keys = keys.ToneLifecycle.test_real_keys_cover_cold_entry_pause_mode_right_exit_and_reentry

    def test_gui_both_modes_and_languages_match_pn233(self):
        import cable_safe
        from thai.engine import Scene
        from thai.mockup import sc_scan
        with contextlib.redirect_stdout(io.StringIO()):
            parent = bytes(cable_safe.build_candidate().data)
        for language in (1, 2):
            for mode in (1, 2):
                for enabled in (0, 1):
                    with self.subTest(language=language, mode=mode, enabled=enabled):
                        old = Scene(image=parent, lang=language)
                        new = Scene(image=self.data, lang=language)
                        sc_scan(old, mode=mode, enable=enabled)
                        sc_scan(new, mode=mode, enable=enabled)
                        self.assertEqual(new.fb, old.fb)
                        labels = {item[1] for item in new.log}
                        self.assertIn('Digital 454 kHz', labels)
                        self.assertIn('Analog 817 Hz', labels)


if __name__ == '__main__':
    unittest.main()
