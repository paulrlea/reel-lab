from dataclasses import dataclass
import os
from pathlib import Path
import re


@dataclass(frozen=True)
class Config:
    data: Path
    model: str = "qwen3:1.7b"
    ollama_url: str = "http://127.0.0.1:11434"
    dry_run: bool = True
    allow_live: bool = False
    max_per_day: int = 2
    min_interval: float = 6
    login: str = "facebook"
    version: str = "v27.0"
    user_id: str = ""
    token: str = ""
    upload: str = "resumable"
    media_base: str = ""

    @classmethod
    def load(cls):
        values = {}
        if Path('.env').exists():
            for line in Path('.env').read_text(encoding='utf-8-sig').splitlines():
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    values[key.strip()] = value.strip().strip('"').strip("'")
        def get(k, default=''):
            return os.environ.get(k, values.get(k, default))
        def flag(k, default):
            value = get(k, default).lower()
            if value not in ('true', 'false'):
                raise ValueError(f'{k} must be true or false')
            return value == 'true'
        c = cls(Path(get('DATA_DIR', 'data')).resolve(), get('OLLAMA_MODEL', 'qwen3:1.7b'), get('OLLAMA_URL', 'http://127.0.0.1:11434'), flag('DRY_RUN', 'true'), flag('ALLOW_LIVE_TRIALS', 'false'), int(get('MAX_PER_DAY', '2')), float(get('MIN_INTERVAL_HOURS', '6')), get('IG_LOGIN', 'facebook'), get('IG_API_VERSION', 'v27.0'), get('IG_USER_ID'), get('IG_ACCESS_TOKEN'), get('IG_UPLOAD', 'resumable'), get('MEDIA_BASE_URL'))
        if not 1 <= c.max_per_day <= 10 or not 0 <= c.min_interval <= 24:
            raise ValueError('Use MAX_PER_DAY 1–10 and MIN_INTERVAL_HOURS 0–24')
        if c.login not in ('facebook', 'instagram') or c.upload not in ('resumable', 'url') or not re.fullmatch(r'v\d+\.\d+', c.version):
            raise ValueError('Invalid Instagram API configuration')
        c.data.mkdir(parents=True, exist_ok=True)
        return c
