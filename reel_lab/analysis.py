"""Technical inspection and optional CPU transcription of a local video."""
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile


def probe_video(source):
    result = subprocess.run(['ffprobe','-v','error','-show_entries',
        'format=duration:stream=index,codec_type,codec_name,width,height,avg_frame_rate,duration:stream_side_data=rotation',
        '-of','json',str(source)], check=True,capture_output=True,text=True,timeout=30)
    data = json.loads(result.stdout)
    video = next((s for s in data.get('streams',[]) if s.get('codec_type')=='video'),None)
    if not video:
        raise ValueError('No usable video stream')
    duration = float(data.get('format',{}).get('duration',0))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Invalid video duration')
    width,height = int(video.get('width',0)),int(video.get('height',0))
    rotation = next((int(d['rotation']) for d in video.get('side_data_list',[]) if 'rotation' in d),0)
    if rotation % 180 == 90: width,height = height,width
    if width<=0 or height<=0: raise ValueError('Invalid video dimensions')
    return {'duration_seconds':duration,'width':width,'height':height,
            'orientation':'portrait' if height>width else 'landscape' if width>height else 'square',
            'codec':video.get('codec_name',''), 'fps':video.get('avg_frame_rate',''),
            'has_audio':any(s.get('codec_type')=='audio' for s in data.get('streams',[]))}


def scene_cuts(source):
    # A low-resolution, bounded CPU pass; times are approximate visual transitions.
    result = subprocess.run(['ffmpeg','-nostdin','-hide_banner','-i',str(source),'-t','120',
        '-vf',"scale=320:-2,select='gt(scene,0.35)',showinfo",'-an','-f','null','-'],
        capture_output=True,text=True,check=True,timeout=180)
    return [round(float(x),3) for x in re.findall(r'pts_time:([0-9.]+)',result.stderr)[:40]]


def transcribe(source, executable, model, *, max_seconds=180):
    """Whisper.cpp CLI, CPU only. No models are downloaded by Reel Lab."""
    if not Path(model).is_file():
        raise ValueError('Whisper model file not found')
    with tempfile.TemporaryDirectory(prefix='reel-lab-whisper-') as tmp:
        wav = Path(tmp)/'source.wav'; out = Path(tmp)/'transcript'
        subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',str(source),'-t',str(max_seconds),
            '-vn','-ar','16000','-ac','1','-c:a','pcm_s16le',str(wav)],check=True,timeout=180)
        subprocess.run([str(executable),'-m',str(model),'-f',str(wav),'-ng','-otxt','-of',str(out)],
            check=True,capture_output=True,timeout=900)
        return out.with_suffix('.txt').read_text(encoding='utf-8').strip()[:12000]
