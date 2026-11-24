"""Persistent, validated creative briefs. No credentials belong in profiles."""
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import tempfile


@dataclass(frozen=True)
class Profile:
    name: str
    description: str
    audience: str = ''
    tone: str = 'Natural and concise'
    categories: str = ''
    editing_style: str = 'Clean, fast-paced cuts'
    music_preferences: str = ''
    restricted_topics: str = ''
    min_duration: int = 7
    max_duration: int = 30
    max_clips: int = 4
    max_hashtags: int = 5
    audio_mode: str = 'off'
    mix_style: str = 'auto'
    beat_sync: bool = True
    require_ad_eligible: bool = True

    @classmethod
    def parse(cls, data):
        if not isinstance(data, dict):
            raise ValueError('Profile must be a JSON object')
        try:
            p = cls(**data)
        except TypeError as exc:
            raise ValueError('Unknown or missing profile field') from exc
        if not isinstance(p.name, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,39}', p.name):
            raise ValueError('Profile name must be a lowercase slug (letters, digits, _ or -)')
        for key in ('description','audience','tone','categories','editing_style','music_preferences','restricted_topics'):
            value = getattr(p,key)
            if not isinstance(value,str) or len(value) > 1000:
                raise ValueError(f'{key} must be text of at most 1000 characters')
        if not p.description.strip():
            raise ValueError('Account description is required')
        for key, low, high in (('min_duration',3,90),('max_duration',3,90),('max_clips',1,6),('max_hashtags',0,10)):
            v = getattr(p,key)
            if type(v) is not int or not low <= v <= high:
                raise ValueError(f'{key} must be an integer from {low} to {high}')
        if p.min_duration > p.max_duration:
            raise ValueError('Minimum duration exceeds maximum duration')
        if p.audio_mode not in ('off','local','native','auto') or p.mix_style not in ('auto','cinematic','dialogue','natural'):
            raise ValueError('Invalid audio mode or mix style')
        if type(p.beat_sync) is not bool or type(p.require_ad_eligible) is not bool:
            raise ValueError('Audio flags must be booleans')
        return p


def profile_path(data, name):
    if not isinstance(name,str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,39}',name):
        raise ValueError('Invalid profile name')
    return Path(data)/'profiles'/(name+'.json')


def save_profile(data, profile):
    profile = Profile.parse(asdict(profile))
    path = profile_path(data, profile.name)
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, suffix='.tmp', delete=False) as f:
        tmp = Path(f.name)
        json.dump(asdict(profile), f, indent=2, ensure_ascii=False)
    try:
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def load_profile(data,name):
    return Profile.parse(json.loads(profile_path(data,name).read_text(encoding='utf-8-sig')))


def profiles(data):
    return sorted(p.stem for p in (Path(data)/'profiles').glob('*.json'))
