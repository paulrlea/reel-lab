"""Render validated plans using an allowlisted FFmpeg pipeline."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap

from .analysis import probe_video
from .media import fingerprint


VERTICAL = ('scale=1080:1920:force_original_aspect_ratio=decrease:force_divisible_by=2,'
            'pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p')


def _run(args, cwd=None):
    subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',*args],
                   cwd=cwd,check=True,timeout=900)


def _font():
    for path in (Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/'arial.ttf',
                 Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
                 Path('/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf'),
                 Path('/System/Library/Fonts/Supplemental/Arial.ttf')):
        if path.is_file(): return path
    raise ValueError('No supported system font found for overlays (install Arial or DejaVu Sans)')


def _normalize(source, clip, target, metadata):
    args=['-ss',str(clip['start']),'-i',str(source)]
    if not metadata['has_audio']:
        args+=['-f','lavfi','-i','anullsrc=channel_layout=stereo:sample_rate=48000']
    args+=['-t',str(clip['duration']),'-map','0:v:0','-map','0:a:0' if metadata['has_audio'] else '1:a:0',
           '-vf',VERTICAL,'-af','aresample=48000:async=1:first_pts=0,apad',
           '-c:v','libx264','-preset','fast','-crf','23','-pix_fmt','yuv420p','-c:a','aac','-ar','48000','-ac','2',
           '-map_metadata','-1','-movflags','+faststart',str(target)]
    _run(args)


def render_plan(available, plan, target):
    """Render only IDs and bounded times already validated by the director."""
    target=Path(target).resolve(); target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists(): raise ValueError('Render target already exists')
    with tempfile.TemporaryDirectory(prefix='edit-',dir=target.parent) as folder:
        work=Path(folder); sources=[]; segments=[]
        for index,clip in enumerate(plan['clips']):
            row=available[clip['id']]; source=Path(row['path']).resolve(strict=True)
            digest=row['sha256']
            if fingerprint(source)!=digest:
                raise ValueError('Source footage changed since tagging; tag it again')
            metadata=probe_video(source)
            if clip['start']+clip['duration']>metadata['duration_seconds']+0.001:
                raise ValueError('Source duration changed; tag it again')
            segment=work/f'clip-{index:02}.mp4'
            _normalize(source,clip,segment,metadata)
            sources.append((source,digest)); segments.append(segment)
        # Filenames are generated locally, never sourced from model text or input paths.
        manifest=work/'concat.txt'
        manifest.write_text(''.join(f"file '{p.name}'\n" for p in segments),encoding='ascii')
        joined=work/'joined.mp4'
        _run(['-f','concat','-safe','1','-i',manifest.name,'-c','copy','-movflags','+faststart',joined.name],cwd=work)
        result=joined
        if plan['overlays']:
            shutil.copyfile(_font(),work/'overlay-font.ttf')
            filters=[]
            for index,overlay in enumerate(plan['overlays']):
                name=f'overlay-{index:02}.txt'
                text='\n'.join(textwrap.fill(line, width=24) for line in overlay['text'].splitlines())
                (work/name).write_text(text,encoding='utf-8')
                # textfile + expansion=none prevents model text from becoming FFmpeg syntax.
                filters.append(f"drawtext=fontfile=overlay-font.ttf:textfile={name}:expansion=none:"
                               f"fontsize=54:fontcolor=white:borderw=3:x=(w-text_w)/2:y=h*0.20:"
                               f"enable='between(t,{overlay['start']},{overlay['end']})'")
            result=work/'final.mp4'
            _run(['-i',joined.name,'-vf',','.join(filters),'-c:v','libx264','-preset','fast','-crf','23',
                  '-c:a','copy','-movflags','+faststart',result.name],cwd=work)
        output=probe_video(result)
        if (output['width'],output['height'])!=(1080,1920) or not output['has_audio']:
            raise ValueError('Rendered dimensions or audio failed validation')
        if output['duration_seconds']<3 or abs(output['duration_seconds']-plan['duration'])>0.75 or result.stat().st_size>300_000_000:
            raise ValueError('Rendered duration or size failed validation')
        for source,digest in sources:
            if fingerprint(source)!=digest: raise ValueError('Source changed while rendering')
        result.replace(target)
    return target
