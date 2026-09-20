"""Extract timestamped overview frames from the owner's local diagnostic clip."""
import hashlib
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw

SOURCE = Path(r'C:\Users\Alpha\Desktop\5da1ebc8-1c14-45a7-ae03-b1cc9fb00ba2.mp4')
OUT = Path(__file__).resolve().parent / 'results/clip-5da1ebc8'
TRANSITION_FRAMES = [*range(40, 46), *range(241, 247), *range(429, 435)]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    metadata = json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(SOURCE)]))
    metadata['source_sha256'] = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    (OUT / 'video_metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    sheet = Image.new('RGB', (4*270, 4*506), '#1c2028')
    draw = ImageDraw.Draw(sheet)
    for second in range(16):
        target = OUT / f'video_frame_{second:02d}.png'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(second), '-i', str(SOURCE),
                        '-frames:v', '1', str(target)], check=True)
        with Image.open(target) as frame:
            frame = frame.convert('RGB').resize((270, 480))
            x, y = (second % 4)*270, (second // 4)*506
            sheet.paste(frame, (x, y+26))
            draw.text((x+8, y+6), f'Seek {second:.1f} s', fill='white')
    sheet.save(OUT / 'video_overview.png')
    pts = json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_frames',
        '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', str(SOURCE)]))
    (OUT / 'video_frame_pts.json').write_text(json.dumps(pts, indent=2), encoding='utf-8')
    transitions = []
    detail = Image.new('RGB', (6*240, 3*322), '#1c2028')
    detail_draw = ImageDraw.Draw(detail)
    for i, index in enumerate(TRANSITION_FRAMES):
        target = OUT / f'video_index_{index:03d}.png'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(SOURCE),
                        '-vf', f'select=eq(n\\,{index})', '-frames:v', '1', str(target)], check=True)
        stamp = float(pts['frames'][index]['best_effort_timestamp_time'])
        transitions.append({'frame': index, 'pts': stamp, 'file': target.name})
        with Image.open(target) as frame:
            # Retain full frames; crop only the display overview for reading.
            frame = frame.convert('RGB').crop((0, 350, 450, 910)).resize((240, 299))
            x, y = (i % 6)*240, (i // 6)*322
            detail.paste(frame, (x, y+23))
            detail_draw.text((x+5, y+5), f'n{index} {stamp:.3f}s', fill='white')
    detail.save(OUT / 'video_digital_to_analog_frames.png')
    (OUT / 'video_digital_to_analog_frames.json').write_text(
        json.dumps(transitions, indent=2), encoding='utf-8')
    print(OUT / 'video_overview.png')


if __name__ == '__main__':
    main()
