#!/usr/bin/env bash
# Adapted from diagnosing-bugs/scripts/hitl-loop.template.sh.
# Manual observation capture only: no copying, flashing, uploads or file writes.
set -euo pipefail

step() {
  printf '\n>>> %s\n' "$1"
  read -r -p "    [Enter when done] " _
}

capture() {
  local var="$1" question="$2" answer
  printf '\n>>> %s\n' "$question"
  read -r -p "    > " answer
  printf -v "$var" '%s' "$answer"
}

if [[ "${1:-}" == --help ]]; then
  printf '%s\n' 'Manual RX Analog A/B capture; does not flash anything.' \
    'Use the accompanying RX-ANALOG-DROPOUT-AB-2026-09-26.md checklist.' \
    'Exit: 0 none observed, 1 dropout reported, 2 inconclusive.'
  exit 0
fi

printf '%s\n' 'LOCAL DIAGNOSTICS ONLY: neither A nor B is a confirmed fix.' \
  'Ctrl-C stops the capture. Do not disconnect RX during programming.' \
  'Read docs/RX-ANALOG-DROPOUT-AB-2026-09-26.md before starting.'
step 'Keep TX PN2.34 in Analog 817 Hz; use RX Analog and the same cable/knob/position that failed.'
capture SETUP 'Record knob, cable and test duration (at least 30s still + 30s moving; longer if needed):'
capture CONTROL 'Does PN1.30 stay stable in this exact setup? Enter stable, drops, or uncertain:'
if [[ "$CONTROL" != stable ]]; then
  printf '\nCONTROL=%s\nVERDICT=inconclusive_control\n' "$CONTROL"
  exit 2
fi

for variant in A B; do
  if [[ "$variant" == A ]]; then
    filename=APP_LPM-10RX_PN1.31A-impulse-only-update.bin
  else
    filename=APP_LPM-10RX_PN1.31B-publication-only-update.bin
  fi
  step "Install $filename from experimental/: RX off, hold SCAN, connect USB, copy with Explorer. Wait for drive disappearance, unplug, then power on."
  capture identity "After application boot, re-enter update mode without copying. Enter the fresh status filename (expected PN1.31${variant}.TXT):"
  if [[ "${identity^^}" != "PN1.31${variant}.TXT" ]]; then
    printf '\n%s_STATUS=%s\nVERDICT=inconclusive_identity\n' "$variant" "$identity"
    exit 2
  fi
  printf -v "${variant}_STATUS" '%s' "$identity"
  step 'Unplug, power on, select Analog. Hold still >=30s, then move slowly >=30s, or longer to match original failure latency.'
  capture "${variant}_STILL" 'Held still: stable, drops, or uncertain? Count unexpected silence, not normal beep gaps:'
  capture "${variant}_MOVING" 'Moving: stable, drops, or uncertain?'
  capture "${variant}_RECOVERY" 'Did sound return without touching controls? yes, no, or n/a; add duration if known:'
done

printf '\n--- Captured (owner observations, not emulated results) ---\n'
for key in SETUP CONTROL A_STATUS A_STILL A_MOVING A_RECOVERY B_STATUS B_STILL B_MOVING B_RECOVERY; do
  printf '%s=%s\n' "$key" "${!key}"
done
printf '%s\n' 'For normal use, restore APP_LPM-10RX_PN1.30-clean-strength-update.bin and confirm PN1.30.TXT.'
verdict=0
for key in A_STILL A_MOVING B_STILL B_MOVING; do
  case "${!key}" in
    stable) ;;
    drops) verdict=1 ;;
    *) printf 'VERDICT=inconclusive_observation\n'; exit 2 ;;
  esac
done
if [[ "$verdict" == 1 ]]; then
  printf 'VERDICT=diagnostic_dropout_reported\n'
else
  printf 'VERDICT=none_observed_in_this_test_not_a_fix_confirmation\n'
fi
exit "$verdict"
