"""Read-only, hash-pinned TX PN2.26 waveform/timer/performance audit.

    python docs/experiments/tx_pn226_waveform_audit.py
    python docs/experiments/tx_pn226_waveform_audit.py --json result.json

Reuse the established real-Thumb carrier/GPIO/clock harness. Register models
do not oscillate the hardware timer or simulate analog voltage, coupling,
loaded output power, flash wait states, or NVIC latency. All reported times
are nominal programmed timer-grid times, never measured electrical timing.
The delayed-service probe is explicit fault injection, not evidence that
interrupts are actually delayed on the owner's device. The Analog accumulator
experiment changes emulator memory only; no firmware file is patched.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct

from tx_tone_performance_audit import AuditMachine, clock_configuration, irq_cost
from lpm10a.thumb import assemble
from test_scan_hardware import TIM1_EXPECTED, requested_wave
from verify_scan import DIGITAL
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_PRIMASK

ROOT = Path(__file__).resolve().parents[2]
FIRMWARE = ROOT/'LPM-10A'/'Firmware File'
ARTIFACT = FIRMWARE/'experimental'/'LPM-10A-TX_PN2.26-qc-display.bin'
SHA256 = 'c77579f018bb820532b3c5974ae63fbf04c4e60359188f7e39a8a8f9a1533df8'
PARENT = FIRMWARE/'experimental'/'LPM-10A-TX_PN2.14-tone-recovery.bin'
PARENT_SHA256 = 'a7402de6f18e39df55bbe53f5641efd5135f0de4d81f9407515cf9d8710c5527'
GPIO_INIT_START, GPIO_INIT_END = 0x080159CC, 0x08015B04
TIM2_SR, TIM2_DIER = 0x40000010, 0x4000000C
ANALOG_ENTRY, ANALOG_PHASE = 0x08014344, 0x200000DE

# What-if only: overwrite mapped emulator flash, never the input byte buffer.
# Reuse the old Analog 16-bit counter. Preserve the existing disabled path,
# carrier gate, hardware timers and all other software clients of TIM2.
ACCUMULATOR_SOURCE = f'''
    push {{r4, lr}}
    ldr r0, =0x200000D0
    ldrb r0, [r0]
    cbnz r0, enabled
    bl 0x0801A6B0
    pop {{r4, pc}}
enabled:
    ldr r4, ={ANALOG_PHASE:#x}
    ldrh r0, [r4]
    movw r1, #2000
    cmp r0, r1
    blo valid
    movs r0, #0
valid:
    adds r0, #165
    cmp r0, r1
    blo stored
    subs r0, r0, r1
stored:
    strh r0, [r4]
    movw r1, #1000
    cmp r0, r1
    movs r0, #0
    blo output
    movs r0, #1
output:
    bl 0x0801464C
    pop {{r4, pc}}
    .pool
'''


def pinned(path, expected):
    data = path.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    assert actual == expected, f'{path.name}: expected {expected}, got {actual}'
    return data


def region(data, address, size):
    offset, length = struct.unpack_from('<II', data, 0x20)
    relative = address-0x0800A000
    assert 0 <= relative <= relative+size <= length
    return data[offset+relative:offset+relative+size]


def unchanged_tone_code(data):
    parent = pinned(PARENT, PARENT_SHA256)
    # Exact established waveform/control paths. The RIGHT-key call site still
    # selects the PN2.14 cache-repair wrapper; its lifecycle is audited elsewhere.
    ranges = {
        'digital_and_analog_generators': (0x08014300,0x16C),
        'scan_gate_dispatch_and_carrier_timer_init': (0x0801464C,0x160),
        'carrier_gpio_routines': (0x0801A60C,0x118),
        'generic_gpio_init': (GPIO_INIT_START,GPIO_INIT_END-GPIO_INIT_START),
        'tim2_init': (0x08016598,0x6C),
        'tim2_irq': (0x08018370,0x5C),
        'right_key_call_site': (0x0801446C,0x2C),
    }
    answer = {}
    for name,(address,size) in ranges.items():
        actual, previous = region(data,address,size), region(parent,address,size)
        assert actual == previous, f'PN2.26 changed the PN2.14 {name}'
        answer[name] = {'address':hex(address),'bytes':size,
                        'sha256':hashlib.sha256(actual).hexdigest()}
    return answer


def cadence(data, mode):
    period = 800 if mode == 1 else 12
    machine = AuditMachine(data,mode,clocks=True)
    original_timer = machine.timer_configuration()
    observed = []
    for tick in range(period*2):
        machine.timer_tick(tick)
        actual = machine.carrier_pins_selected()
        assert actual == requested_wave(mode,tick), (mode,tick,actual)
        observed.append(actual)
    assert machine.timer_configuration() == original_timer == TIM1_EXPECTED
    assert observed[:period] == observed[period:]
    answer = {'observed_ticks':len(observed),'counter_period_ticks':period,
              'carrier_enabled_ticks_per_period':sum(observed[:period]),
              'envelope_duty':sum(observed[:period])/period,
              'timer_configuration_changed_during_modulation':False}
    if mode == 1:
        assert machine.r32(DIGITAL) == 800
        assert observed[:400] == observed[400:800]
        answer.update(chip_ticks=50,chip_us=5050,
                      eight_chip_pattern='10110110',code_repeat_us=40400,
                      counter_wrap_us=80800)
    else:
        answer.update(half_cycle_ticks=6,half_cycle_us=606,period_us=1212)
    return answer


def edge_cost(data, mode):
    """Attribute the already measured transition work without changing it."""
    machine = AuditMachine(data,mode,clocks=True)
    rows, masked_run, max_masked = [], 0, 0
    for tick in range(1001):
        visits = Counter()
        def instruction(uc,address,size,user):
            nonlocal masked_run,max_masked
            visits[address] += 1
            if uc.reg_read(UC_ARM_REG_PRIMASK):
                masked_run += 1
                max_masked = max(max_masked,masked_run)
            else:
                masked_run = 0
        hook = machine.uc.hook_add(UC_HOOK_CODE,instruction)
        before, edge_start = machine.instructions,len(machine.edge_writes)
        try:
            machine.timer_tick(tick)
        finally:
            machine.uc.hook_del(hook)
        writes = machine.edge_writes[edge_start:]
        if writes:
            gpio_cost = sum(n for address,n in visits.items()
                            if GPIO_INIT_START <= address < GPIO_INIT_END)
            assert visits[GPIO_INIT_START] == 2
            assert len(writes) == 2 and gpio_cost == 242
            assert writes[1][0]-writes[0][0] == 126
            rows.append((machine.instructions-before,gpio_cost))
    assert rows
    return {'profiled_ticks':1001,'transition_calls':len(rows),
            'gpio_init_calls_per_transition':2,
            'gpio_init_instructions_per_transition':242,
            'inter_pin_configuration_separation_instructions':126,
            'transition_irq_instruction_counts':sorted({n for n,_ in rows}),
            'max_contiguous_primask_instructions_in_modeled_irq':max_masked,
            'opportunity':'Specialized GPIO updates can avoid generic pin-selection loops; preserve unrelated CRH fields, complementary output setup and vendor OFF polarity. Electrical transitions would need measurement.'}


def delayed_service(data, mode):
    """One pending update flag cannot encode several withheld timer events."""
    start, withheld, expected_first = (45,8,50) if mode == 1 else (4,2,6)
    machine = AuditMachine(data,mode,clocks=True)
    states = []
    services = 0
    for tick in range(100):
        # Set the modeled update flag for every hardware-grid event; deliberately
        # withhold CPU service for the named interval. Repeated flag sets merge.
        machine.w32(TIM2_DIER,1)
        machine.w32(TIM2_SR,1)
        if not start <= tick < start+withheld:
            machine.timer_tick(tick)
            services += 1
            assert machine.r32(TIM2_SR)&1 == 0
        states.append(machine.carrier_pins_selected())
    first_change = next(i for i in range(1,len(states)) if states[i] != states[0])
    assert first_change == expected_first+withheld
    return {'fault_injection_only':True,'hardware_grid_ticks':len(states),
            'serviced_irqs':services,'withheld_at_tick':start,'withheld_ticks':withheld,
            'first_edge_expected_tick':expected_first,'first_edge_observed_tick':first_change,
            'injected_edge_delay_us':withheld*101,
            'interpretation':'Modulation advances once per serviced IRQ. Coalesced timer events stretch its phase; this probe does not establish that a real IRQ deadline is missed.'}


def shared_timer_clients(data):
    machine = AuditMachine(data,2,clocks=True)
    machine.call(0x080189C4)  # main's real priority-group/USB IRQ setup
    machine.call(0x08016598)  # real TIM2 initialization after grouping
    assert machine.r32(0xE000ED0C) == 0x05FA0500
    assert machine.r8(0xE000E41C) == 0x10
    return {
        'tim2_irq28_priority_byte':hex(machine.r8(0xE000E41C)),
        'aircr_after_actual_application_group_setup':hex(machine.r32(0xE000ED0C)),
        'priority_setup_path':'main0x0801BBB4 ->0x080189C4 ->grouping0x500; TIM2 init0x08016598 ->NVIC_Init0x08017DB0, preemption0/subpriority1',
        'ordinary_rtos_critical_mask':'vPortEnterCritical0x0801C6B4 sets BASEPRI0xBF at0x0801C6B8, which does not mask TIM2 priority0x10; PRIMASK is separate.',
        'watchdog':'IRQ0x08018398 calls heartbeat wrapper0x08068558 every1000 interrupts using0x200001A4;101ms at current ARR100,102ms if ARR101.',
        'local_buzzer':'IRQ0x080183BC calls0x0800F9CC every5 interrupts using0x200001A8;505us currently,510us at ARR101. F9CC reads key-feedback timestamp/count0x20000150/154 and volume settings+0xA4, writes TIM3_CCR3=0x4000043C and flips0x2000017A. Older symbols call it backlight_dim_update.',
        'independent_of_tim2_arr':'SysTick0x08018298/tick hook0x0801BC70 provide0x200001A0 milliseconds; RTOS delays and hardware TIM1 carrier are independent.',
    }


def analog_accumulator_experiment(data):
    machine = AuditMachine(data,2,clocks=True)
    source = assemble(ANALOG_ENTRY,ACCUMULATOR_SOURCE)
    machine.uc.mem_write(ANALOG_ENTRY,source)
    before_timer = machine.timer_configuration()
    counts,states = [],[]
    for tick in range(1600):
        before = machine.instructions
        machine.timer_tick(tick)
        states.append(machine.carrier_pins_selected())
        counts.append(machine.instructions-before)
        assert states[-1] == int(((tick+1)*165%2000)>=1000)
    assert all(states[i:i+400] == states[:400] for i in range(0,1600,400))
    assert sum(states[:400]) == 200
    assert machine.timer_configuration() == before_timer == TIM1_EXPECTED
    assert (machine.r32(0x40000028),machine.r32(0x4000002C)) == (71,100)
    # Capture complete circular runs; first/last runs join at the period edge.
    edges = [i for i in range(400) if states[i] != states[(i-1)%400]]
    lengths = Counter((edges[(i+1)%len(edges)]-start)%400
                      for i,start in enumerate(edges))
    assert lengths == {6:62,7:4}
    assert len(edges) == 66
    return {
        'in_memory_what_if_only':True,'production_artifact_unchanged':True,
        'routine_bytes':len(source),'existing_phase_halfword':hex(ANALOG_PHASE),
        'tim2_tick_us_unchanged':101,'frequency_hz':33/(400*101e-6),
        'cycles_per400ticks':33,'envelope_duty':0.5,
        'half_cycle_tick_histogram_per400ticks':dict(sorted(lengths.items())),
        'half_cycle_us':[606,707],
        'instructions':{'min':min(counts),'max':max(counts),'mean':sum(counts)/len(counts)},
        'observed_trace_first400ticks':''.join(map(str,states[:400])),
        'tradeoff':'Mean frequency approaches the RX DFT bin without changing Digital/watchdog/buzzer timing, but 6/7-tick half-cycles add101us deterministic edge quantization instead of the existing steady6-tick cadence. Not validated on a device or older receivers.',
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json',type=Path,help='write this new audit result, never firmware')
    args = parser.parse_args(argv)
    if args.json and args.json.suffix.lower() != '.json':
        parser.error('--json output must have a .json extension')
    data = pinned(ARTIFACT,SHA256)
    clocks = clock_configuration(data)
    clocks['nominal_timer_oc1_duty'] = 158/317
    result = {
        'artifact':str(ARTIFACT.relative_to(ROOT)), 'sha256':SHA256,
        'parent_tone_sha256':PARENT_SHA256,
        'scope':'Exact published PN2.26 actual Thumb code; peripheral register/IRQ-arrival model, no electrical or instruction-cycle simulation.',
        'clocks':clocks,
        'cadence':{str(m):cadence(data,m) for m in (1,2)},
        'irq':{str(m):irq_cost(data,m) for m in (1,2)},
        'unchanged_since_pn214':unchanged_tone_code(data),
        'edge_cost':{str(m):edge_cost(data,m) for m in (1,2)},
        'delayed_service_fault_injection':{str(m):delayed_service(data,m) for m in (1,2)},
        'shared_tim2_clients':shared_timer_clients(data),
        'analog_phase_accumulator_experiment':analog_accumulator_experiment(data),
        'electrical_gain_claim':'None: no output amplitude/power or cable-coupling measurement is available.',
    }
    assert pinned(ARTIFACT,SHA256) == data
    output = json.dumps(result,indent=2)+'\n'
    if args.json:
        args.json.write_text(output,encoding='utf-8')
    print(output,end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
