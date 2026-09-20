"""Run component contracts against the complete PN 1.11 profile.

These adapters deliberately run the real integrated bytes, including reused
DFT helper space and the Analog tail holding the Digital overlap routine.
"""
import hashlib
import unittest

import analog_fast
import analog_feedback
import digital_tracking
import test_roadmap
import test_rx_analog_feedback as analog_tests
import test_rx_analog_feedback_races as race_tests
import test_rx_digital_overlap as overlap_tests
import test_rx_digital_tracking as digital_tests
import test_rx_followup as followup
import test_rx_robust
import tracking_fixes
from lpm10rx.image import PatchError


def candidate():
    img = test_rx_robust.candidate()
    tracking_fixes.apply(img)
    return img


def setup(cls):
    cls.previous = bytes(test_rx_robust.candidate().data)
    cls.img = candidate()
    cls.data = bytes(cls.img.data)


def scope(test):
    allowed = ((analog_fast.LOOP, analog_fast.TAIL_END),
               (analog_feedback.ANALYZER, analog_feedback.ANALYZER_END),
               (analog_feedback.SPEAKER_DISPATCH, analog_feedback.SPEAKER_END),
               (digital_tracking.DETECTOR, digital_tracking.PUBLISH),
               (digital_tracking.LOCAL, digital_tracking.LOCAL_END),
               (digital_tracking.ESTIMATOR, digital_tracking.ESTIMATOR_END))
    changed = [0x08006800+i for i,(a,b) in enumerate(zip(test.previous,test.data)) if a!=b]
    test.assertTrue(changed)
    test.assertEqual(len(test.data),26152)
    test.assertTrue(all(any(lo<=address<hi for lo,hi in allowed) for address in changed))
    # Reconstruct sequential patch log from the exact stock and check every
    # predecessor byte. Preserves vectors, UID binding and all unrelated code.
    data=bytearray(test.img.original)
    for address,old,new,why,kind in test.img.log:
        offset=address-0x08006800
        test.assertEqual(bytes(data[offset:offset+len(old)]),old,why)
        data[offset:offset+len(new)]=new
    test.assertEqual(bytes(data),test.data)
    img=test_rx_robust.candidate()
    img.data[0x100]^=1
    before=bytes(img.data)
    with test.assertRaises(PatchError): tracking_fixes.apply(img)
    test.assertEqual(bytes(img.data),before)


class TrackingAnalog(analog_tests.AnalogFeedback):
    setUpClass=classmethod(setup)
    def test_scope_and_parent_guards(self): scope(self)


class TrackingDigital(digital_tests.DigitalTracking):
    setUpClass=classmethod(setup)
    def test_scope_guards_and_size(self): scope(self)


class TrackingOverlap(overlap_tests.DigitalOverlap):
    setUpClass=classmethod(setup)


class TrackingRaces(race_tests.AnalogFeedbackRaces):
    setUpClass=classmethod(setup)


class TrackingControl(unittest.TestCase):
    setUpClass=classmethod(setup)
    cpu=test_rx_robust.Robust.cpu
    execute=followup.Followup.execute
    boundary=followup.Followup.boundary
    acquire=followup.Followup.acquire
    adc=test_roadmap.Roadmap.adc
    test_mode_changes=followup.Followup.test_all_directed_mode_changes_discard_partial_and_completed_windows
    test_mains_clear_rearm=followup.Followup.test_mains_publishes_rearm_after_clear_and_first_tim5_sample_survives
    test_gate_pulse=followup.Followup.test_gate_close_open_pulse_remains_latched_until_fresh_acquisition
    test_gate_thresholds=followup.Followup.test_gate_publisher_threshold_matrix_and_gain_result
    test_boundary_mask=followup.Followup.test_mode_boundary_restores_mask_and_preserves_active_confirmation
    test_key_led_battery=followup.Followup.test_key_led_and_battery_shadow_match_previous_release
    test_startup_ownership=followup.Followup.test_startup_discards_unowned_samples_before_first_analysis
    test_startup_timer_race=followup.Followup.test_actual_startup_mode_switch_with_stale_analog_samples_and_timer_preemption
    test_housekeeping=followup.Followup.test_timer_housekeeping_main_watchdog_and_physical_power_key
    test_key_debounce=followup.Followup.test_key_debounce_release_and_mode_sequence
    test_adc_wait=test_roadmap.Roadmap.test_adc_waits_for_selected_channel_and_restores_mask
    test_adc_timeout=test_roadmap.Roadmap.test_adc_timeout_never_returns_stale_or_false_battery_data


if __name__ == '__main__':
    unittest.main()
