"""Generate drafts from the catalog. The publishing worker remains separate."""
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
import sqlite3
import uuid

from . import footage, director, editor
from .media import fingerprint
from .store import scheduled
from .ai import caption_valid
from .audio import AudioCatalog, choose
from .beats import snap_plan


def generate(config, store, profile, due, *, allow_reuse=False):
    due=scheduled(due)
    used=() if allow_reuse else store.used_sources()
    available=director.candidates(footage.export(config.data/'footage.sqlite3'),profile,used)
    plan=director.plan(config,profile,available)
    audio=choose(config,store,profile,plan,available,AudioCatalog(config.data)) if profile.audio_mode!='off' else None
    if audio:
        audio['beat_shifts']=[]
        if audio['source']=='local' and audio['beat_sync'] and audio.get('confidence',0)>=.65:
            plan,audio['beat_shifts']=snap_plan(plan,available,audio['beats'],audio['offset'])
        audio['requested_duration']=plan['duration']
    out=config.data/'rendered'/(uuid.uuid4().hex+'.mp4')
    sources=[{'id':clip['id'],'path':available[clip['id']]['path'],'sha256':available[clip['id']]['sha256']}
             for clip in plan['clips']]
    caption=caption_valid(plan['caption']+('\n\n'+' '.join(plan['hashtags']) if plan['hashtags'] else ''))
    try:
        if audio: editor.render_plan(available,plan,out,audio=audio)
        else: editor.render_plan(available,plan,out)
        return store.add_generated(out,fingerprint(out),caption,plan['concept'],plan['hypothesis'],due,asdict(profile),plan,sources,allow_reuse=allow_reuse,audio=audio)
    except sqlite3.IntegrityError:
        out.unlink(missing_ok=True)
        raise ValueError('An identical rendered video is already queued') from None
    except Exception:
        out.unlink(missing_ok=True)
        raise


def fill_queue(config,store,profile,max_pending=2,spacing_hours=24):
    if not 1<=max_pending<=10 or not max(1,config.min_interval)<=spacing_hours<=168:
        raise ValueError('Invalid queue target or spacing')
    pending=[j for j in store.rows() if j['state'] in ('draft','approved','publishing','uncertain')]
    if len(pending)>=max_pending:
        return None
    now=datetime.now(timezone.utc)
    latest=max((datetime.fromisoformat(j['due']) for j in pending),default=now-timedelta(hours=spacing_hours))
    due=max(now,latest+timedelta(hours=spacing_hours))
    return generate(config,store,profile,due.isoformat())
