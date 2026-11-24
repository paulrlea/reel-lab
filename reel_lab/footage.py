"""Import fully transferred videos without modifying or publishing originals."""
from datetime import datetime, timezone
from pathlib import Path
import shutil
import time
import uuid
from .media import fingerprint

VIDEO_EXTENSIONS = {'.mov', '.mp4', '.m4v'}


def videos(folder):
    return sorted(p for p in Path(folder).iterdir() if p.is_file() and not p.is_symlink() and p.suffix.lower() in VIDEO_EXTENSIONS)


class FootageWatcher:
    def __init__(self, config, folder, settle=30):
        self.folder = Path(folder).resolve()
        self.folder.mkdir(parents=True, exist_ok=True)
        self.archive = config.data / 'footage'
        self.archive.mkdir(parents=True, exist_ok=True)
        self.settle = max(1, settle)
        self.observed = {}
        self.completed = {}

    def scan(self):
        imported = []
        active = set()
        for source in videos(self.folder):
            active.add(source)
            try:
                stat = source.stat()
                signature = (stat.st_size, stat.st_mtime_ns)
                if self.completed.get(source) == signature:
                    continue
                previous, first = self.observed.get(source, (None, 0))
                if signature != previous:
                    self.observed[source] = (signature, time.monotonic())
                    continue
                if not stat.st_size or time.monotonic() - first < self.settle:
                    continue
                digest = fingerprint(source)
                if any(self.archive.glob(f'*/{digest}.*')):
                    self.completed[source] = signature
                    continue
                date = datetime.fromtimestamp(stat.st_mtime, timezone.utc).strftime('%Y-%m-%d')
                dest = self.archive / date / (digest + source.suffix.lower())
                dest.parent.mkdir(parents=True, exist_ok=True)
                temp = dest.with_name(dest.name + '.' + uuid.uuid4().hex + '.partial')
                try:
                    shutil.copy2(source, temp)
                    after = source.stat()
                    if signature != (after.st_size, after.st_mtime_ns) or fingerprint(temp) != digest:
                        continue
                    temp.replace(dest)
                    self.completed[source] = signature
                    imported.append(dest)
                finally:
                    temp.unlink(missing_ok=True)
            except OSError:
                # Network copy may still be open; try again later.
                continue
        self.observed = {p: v for p, v in self.observed.items() if p in active}
        self.completed = {p: v for p, v in self.completed.items() if p in active}
        return imported
