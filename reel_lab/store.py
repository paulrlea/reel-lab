from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import json
import sqlite3


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def scheduled(value):
    d = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if d.tzinfo is None:
        raise ValueError('Schedule must include a timezone offset, e.g. 2027-01-01T18:00:00-06:00')
    return d.astimezone(timezone.utc).isoformat(timespec='seconds')


class Store:
    def __init__(self, config):
        self.config = config
        self.db = sqlite3.connect(config.data / 'reels.sqlite3', timeout=15)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY, path TEXT NOT NULL, hash TEXT NOT NULL UNIQUE,
            caption TEXT NOT NULL, brief TEXT NOT NULL, hypothesis TEXT NOT NULL DEFAULT '',
            trial TEXT NOT NULL CHECK(trial IN ('MANUAL','SS_PERFORMANCE')),
            due TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'draft',
            created TEXT NOT NULL, started TEXT, published TEXT, media_id TEXT, error TEXT,
            video_url TEXT NOT NULL DEFAULT '', mode TEXT);
        CREATE TABLE IF NOT EXISTS metrics (
            job_id INTEGER NOT NULL, age INTEGER NOT NULL, collected TEXT NOT NULL, data TEXT NOT NULL,
            PRIMARY KEY(job_id,age));''')

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def add(self, path, digest, caption, brief, hypothesis, trial, due, url=''):
        with self.db:
            cur = self.db.execute('INSERT INTO jobs(path,hash,caption,brief,hypothesis,trial,due,created,video_url) VALUES(?,?,?,?,?,?,?,?,?)', (str(path), digest, caption, brief, hypothesis, trial, scheduled(due), now(), url))
            return cur.lastrowid

    def rows(self):
        return [dict(r) for r in self.db.execute('SELECT * FROM jobs ORDER BY id DESC')]

    def get(self, id):
        row = self.db.execute('SELECT * FROM jobs WHERE id=?', (id,)).fetchone()
        if row is None:
            raise ValueError('Unknown job')
        return dict(row)

    def approve(self, id):
        with self.db:
            if self.db.execute("UPDATE jobs SET state='approved',mode=? WHERE id=? AND state='draft'", ('dry' if self.config.dry_run else 'live', id)).rowcount != 1:
                raise ValueError('Only draft jobs may be approved')

    def edit(self, id, caption, due):
        with self.db:
            if self.db.execute("UPDATE jobs SET caption=?,due=? WHERE id=? AND state='draft'", (caption, scheduled(due), id)).rowcount != 1:
                raise ValueError('Only draft jobs can be edited')

    def cancel(self, id):
        with self.db:
            if self.db.execute("UPDATE jobs SET state='cancelled' WHERE id=? AND state IN ('draft','approved')", (id,)).rowcount != 1:
                raise ValueError('Only drafts and approved jobs can be cancelled')

    def claim(self):
        mode = 'dry' if self.config.dry_run else 'live'
        t = now()
        day_ago = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec='seconds')
        interval_ago = (datetime.now(timezone.utc) - timedelta(hours=self.config.min_interval)).isoformat(timespec='seconds')
        with self.transaction():
            if mode == 'live' and self.db.execute("SELECT 1 FROM jobs WHERE mode='live' AND state IN ('uncertain','publishing') LIMIT 1").fetchone():
                return None
            # Count attempts, not only successful posts: conservative after uncertain outcomes.
            if self.db.execute("SELECT COUNT(*) FROM jobs WHERE mode=? AND started>?", (mode, day_ago)).fetchone()[0] >= self.config.max_per_day:
                return None
            if self.db.execute("SELECT 1 FROM jobs WHERE mode=? AND (started>? OR state='publishing') LIMIT 1", (mode, interval_ago)).fetchone():
                return None
            row = self.db.execute("SELECT * FROM jobs WHERE state='approved' AND due<=? AND mode=? ORDER BY due,id LIMIT 1", (t,mode)).fetchone()
            if row is None:
                return None
            self.db.execute("UPDATE jobs SET state='publishing',started=?,mode=? WHERE id=?", (t, mode, row['id']))
            return dict(row)

    def finish(self, id, state, media_id=None, error=None):
        with self.db:
            if self.db.execute("UPDATE jobs SET state=?,media_id=?,error=?,published=? WHERE id=? AND state='publishing'", (state, media_id, error, now() if state == 'published' else None, id)).rowcount != 1:
                raise ValueError('Job no longer publishing')

    def reconcile(self, id, media_id=None):
        # Manual reconciliation only, never retry a potentially published request.
        with self.db:
            if self.db.execute("UPDATE jobs SET state=?,media_id=?,published=?,error=NULL WHERE id=? AND state IN ('publishing','uncertain')", ('published' if media_id else 'abandoned', media_id, now() if media_id else None, id)).rowcount != 1:
                raise ValueError('Only interrupted/uncertain jobs can be reconciled')

    def reset_dry(self, id):
        with self.db:
            if self.db.execute("UPDATE jobs SET state='draft',mode=NULL,started=NULL,error=NULL WHERE id=? AND state IN ('simulated','approved') AND mode='dry'", (id,)).rowcount != 1:
                raise ValueError('Only simulated or dry-run-approved jobs can be reset')

    def history(self):
        rows = self.db.execute('SELECT jobs.hypothesis,jobs.caption,metrics.age,metrics.data FROM metrics JOIN jobs ON jobs.id=metrics.job_id ORDER BY metrics.collected DESC LIMIT 12').fetchall()
        return [{**dict(r), 'data': json.loads(r['data'])} for r in rows]

    def due_metrics(self):
        for r in self.db.execute("SELECT id,media_id,published FROM jobs WHERE state='published' AND mode='live'").fetchall():
            elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(r['published'])).total_seconds()/3600
            # Avoid labelling an already-old measurement as a 24-hour sample.
            for age in (24, 72):
                if age <= elapsed < age + 12 and not self.db.execute('SELECT 1 FROM metrics WHERE job_id=? AND age=?', (r['id'], age)).fetchone():
                    yield r['id'], r['media_id'], age

    def save_metrics(self, id, age, data):
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO metrics VALUES(?,?,?,?)', (id, age, now(), json.dumps(data)))
