"""Opt-in acquisition of individually authorized recordings via spotDL."""
import hashlib
import math
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from .audio import text_field, probe_audio, utcnow
from .beats import analyze_beats
from .media import fingerprint


def register(catalog,spotify,youtube,title,artist,tags,license_note,duration,*,rights_confirmed=False,ads_eligible=False,offset=0):
    # Pin the exact source rather than allowing a search to choose a different upload.
    if rights_confirmed is not True or not str(license_note).strip():
        raise ValueError('Confirm download permission and commercial synchronization rights for this exact recording')
    sp=re.fullmatch(r'https://open\.spotify\.com/track/([A-Za-z0-9]{22})',spotify)
    yt=re.fullmatch(r'https://www\.youtube\.com/watch\?v=([A-Za-z0-9_-]{11})',youtube)
    if not sp or not yt: raise ValueError('Use a single Spotify track URL and exact YouTube watch URL, without tracking parameters')
    if type(duration) not in (int,float) or not math.isfinite(duration) or not 3<=duration<=1800:
        raise ValueError('Enter expected recording duration in seconds (3–1800)')
    if type(offset) not in (int,float) or not math.isfinite(offset) or not 0<=offset<=duration-3:
        raise ValueError('Invalid start offset')
    title=text_field(title); artist=text_field(artist)
    if not title or not artist: raise ValueError('Title and artist are required')
    key='spotdl:'+hashlib.sha256((spotify+'|'+youtube).encode()).hexdigest()
    old=next((t for t in catalog.tracks() if t['key']==key),None)
    track={'key':key,'source':'local','provider':'spotdl','spotify_url':spotify,'youtube_url':youtube,
           'title':title,'artist':artist,'tags':text_field(tags,1000),'license':text_field(license_note,1000),
           'duration':float(duration),'expected_duration':float(duration),'offset':offset,'rights_confirmed':True,
           'ads_eligible':ads_eligible is True,'observed':utcnow(),'path':'','bpm':None,'beats':[],'confidence':0.0}
    if old and old.get('path'):
        track.update({k:old[k] for k in ('path','sha256','duration','bpm','beats','confidence')})
    return catalog._save(track)


def materialize(config,catalog,selected):
    if selected.get('provider')!='spotdl': return selected
    entry=next((t for t in catalog.tracks() if t['key']==selected['key']),None)
    if not config.allow_spotdl or not entry or not entry['enabled'] or entry.get('rights_confirmed') is not True:
        raise ValueError('spotDL acquisition is not enabled or this recording is no longer authorized')
    if selected['require_ads'] and not entry['ads_eligible']:
        raise ValueError('Recording is no longer eligible for advertising')
    if entry.get('path'):
        path=Path(entry['path'])
        if not path.is_file() or fingerprint(path)!=entry['sha256']:
            raise ValueError('Cached recording is missing or changed; check the licensed file')
    else:
        cache=config.data/'music-cache'; cache.mkdir(parents=True,exist_ok=True)
        dest=cache/(entry['key'].split(':',1)[1]+'.mp3')
        if dest.exists(): raise ValueError('Unregistered cache file exists; review it before retrying')
        with tempfile.TemporaryDirectory(prefix='spotdl-',dir=cache) as directory:
            work=Path(directory)
            subprocess.run([sys.executable,'-m','spotdl','download',entry['youtube_url']+'|'+entry['spotify_url'],
                '--format','mp3','--output','{track-id}.{output-ext}'],cwd=work,check=True,timeout=600)
            expected=entry['spotify_url'].rsplit('/',1)[1]+'.mp3'
            files=list(work.glob('*.mp3'))
            if len(files)!=1 or files[0].name!=expected: raise ValueError('Expected exactly one matching downloaded recording')
            path=files[0]; duration=probe_audio(path)
            if abs(duration-entry['expected_duration'])>3: raise ValueError('Downloaded duration differs from the authorized recording')
            if duration-entry['offset']<selected['requested_duration']: raise ValueError('Downloaded track is too short')
            beats=analyze_beats(path); digest=fingerprint(path)
            path.replace(dest)
            entry.update(path=str(dest.resolve()),sha256=digest,duration=duration,**beats)
            catalog._save(entry)
    if entry['duration']-entry['offset']<selected['requested_duration'] or abs(entry['duration']-entry['expected_duration'])>3:
        raise ValueError('Cached duration does not match the authorized recording')
    return {**selected,**entry}
