"""Model-only tradeoff test: reject isolated Analog indications by confirmation.

Uses the independent mathematical DFT audit, not measured front-end noise.
These policies are NOT in PN 1.11. A lower synthetic false-indication count
does not justify accepting missed brief/weak real signals without device data.
"""
import argparse
import json
import math
import random

from rx_analog_performance_audit import classify, sine, TX_HZ, SAMPLE_HZ

FRAME_MS=64000/SAMPLE_HZ


def decisions(margins, policy):
    previous=False
    result=[]
    for margin in margins:
        eligible=margin>10
        if policy=='one_window': accepted=eligible
        elif policy=='two_windows': accepted=eligible and previous
        elif policy=='strong_or_two': accepted=eligible and (margin>200 or previous)
        else: raise ValueError(policy)
        result.append(accepted)
        previous=eligible
    return result


def summarize(margins):
    result={}
    for policy in ('one_window','two_windows','strong_or_two'):
        outputs=decisions(margins,policy)
        indices=[i for i,value in enumerate(outputs) if value]
        result[policy]={'accepted_windows':len(indices),
                        'first_accepted_frame':indices[0] if indices else None}
    return result


def benchmark(noise_windows=4096):
    noise=[]
    for magnitude in (50,100,200,400,800,1600):
        rng=random.Random(0x825C0F+magnitude)
        margins=[classify([2048+rng.randint(-magnitude,magnitude) for _ in range(64)])['margin']
                 for _ in range(noise_windows)]
        noise.append({'uniform_half_range':magnitude,'frames':len(margins),
                      'max_margin':max(margins),'policies':summarize(margins)})
    tones=[]
    for amplitude in (12,15,25,50,100,300,1000):
        for span in (1,2,4,16):
            first=[]
            for phase in range(16):
                margins=[-100]
                for frame in range(span):
                    angle=phase*2*math.pi/16+frame*64*TX_HZ/SAMPLE_HZ*2*math.pi
                    margins.append(classify(sine(amplitude=amplitude,phase=angle))['margin'])
                margins.extend([-100,-100])
                first.append(summarize(margins))
            tones.append({'amplitude':amplitude,'present_frames':span,
                          'present_ms':span*FRAME_MS,'phase_cases':16,
                          'detected_cases':{policy:sum(r[policy]['accepted_windows']>0 for r in first)
                            for policy in ('one_window','two_windows','strong_or_two')}})
    fading=[]
    for amplitude in (15,25,50,100,300):
        for noise_ratio in (0.5,1,2,4):
            rng=random.Random(0xFAD000+amplitude+int(noise_ratio*10))
            margins=[classify(sine(amplitude=amplitude,
                phase=frame*64*TX_HZ/SAMPLE_HZ*2*math.pi,
                noise=round(amplitude*noise_ratio),rng=rng))['margin'] for frame in range(128)]
            fading.append({'amplitude':amplitude,'uniform_noise_ratio':noise_ratio,
                           'frames':128,'policies':summarize(margins)})
    # Identical observations cannot establish whether the one-frame tone was
    # a desired short visit or an unrelated transient at the target frequency.
    weak_single=next(r for r in tones if r['amplitude']==25 and r['present_frames']==1)
    assert weak_single['detected_cases']['one_window']==16
    assert weak_single['detected_cases']['two_windows']==0
    assert weak_single['detected_cases']['strong_or_two']==0
    return {'scope':__doc__,'frame_ms':FRAME_MS,'noise':noise,'tone_bursts':tones,
            'noisy_sustained_tones':fading,
            'decision':'Do not deploy unconditional confirmation without real sweep/noise evidence; '
                       'it suppresses isolated weak legitimate visits as well as noise.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--noise-windows',type=int,default=4096)
    args=parser.parse_args()
    print(json.dumps(benchmark(args.noise_windows),indent=2))
