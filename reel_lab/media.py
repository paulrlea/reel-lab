import hashlib
import json
from pathlib import Path
import subprocess


def fingerprint(path):
    with Path(path).open('rb') as f:
        h = hashlib.sha256()
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
        return h.hexdigest()


def render(source, target, start=0, duration=30):
    if start < 0 or not 3 <= duration <= 90:
        raise ValueError('Start must be nonnegative; duration must be 3–90 seconds')
    source, target = Path(source), Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix('.partial.mp4')
    subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(start), '-i', str(source), '-t', str(duration), '-map', '0:v:0', '-map', '0:a:0?', '-vf', 'scale=1080:1920:force_original_aspect_ratio=decrease:force_divisible_by=2,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30', '-c:v', 'libx264', '-preset', 'fast', '-crf', '23', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', '-ac', '2', '-movflags', '+faststart', str(temp)], check=True)
    probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(temp)], check=True, capture_output=True, text=True)
    if float(json.loads(probe.stdout)['format']['duration']) < 3 or temp.stat().st_size > 300_000_000:
        raise ValueError('Rendered video must be at least 3 seconds and under 300 MB')
    temp.replace(target)
    return target
