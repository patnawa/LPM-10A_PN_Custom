"""Independent Analog smoke comparison for LOCAL A/B diagnostics, not a fix claim."""
from contextlib import redirect_stdout
import hashlib
import io

from release_analog_drop import clean_strength, pair, simulate
import analog_drop_ablation as ab


def main():
    pair.CurrentPair.setUpClass()
    runner = pair.CurrentPair('test_fixture_executes_the_current_pair')
    assert runner.tx_sha == '92ebb4cd60e7b652f32ca65cfa21401c1657fa63ee1b945864fed3c74a422227'
    with redirect_stdout(io.StringIO()):
        images = {'PN1.30': bytes(clean_strength.build_candidate().data),
                  **{kind: bytes(ab.build_candidate(kind).data) for kind in ('A', 'B')}}
    assert hashlib.sha256(images['PN1.30']).hexdigest() == ab.PARENT_SHA256
    fields = ('edges', 'states', 'publications')
    comparisons = 0
    for parameters in ({'amplitude': 1200, 'knob': 4095}, {'amplitude': 30000, 'knob': 2048}):
        baseline = simulate(runner, images['PN1.30'], envelope=lambda ms: 1, end_ms=4000, **parameters)
        for kind in ('A', 'B'):
            row = simulate(runner, images[kind], envelope=lambda ms: 1, end_ms=4000, **parameters)
            assert all(row[field] == baseline[field] for field in fields), (kind, parameters)
            assert not row['long_quiet_spans'], (kind, parameters)
            comparisons += 1
            print(kind, parameters, 'exact Analog timeline matches PN1.30; max quiet ms:',
                  row['max_quiet_ms_after_1s'], flush=True)
    print(comparisons, 'independent variant comparisons passed; physical diagnosis still pending', flush=True)


if __name__ == '__main__':
    main()
