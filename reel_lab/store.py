from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import json
import sqlite3
import math


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
            PRIMARY KEY(job_id,age));
        CREATE TABLE IF NOT EXISTS generated_plans (
            job_id INTEGER PRIMARY KEY REFERENCES jobs(id), profile TEXT NOT NULL,
            profile_json TEXT NOT NULL, plan_json TEXT NOT NULL, sources_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS job_audio (job_id INTEGER PRIMARY KEY REFERENCES jobs(id), metadata TEXT NOT NULL);''')

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

    def add_generated(self,path,digest,caption,brief,hypothesis,due,profile,plan,sources,*,allow_reuse=False,audio=None):
        with self.transaction():
            if not allow_reuse and self.used_sources() & {item['sha256'] for item in sources}:
                raise ValueError('Footage was already used by another generated draft')
            cur=self.db.execute('INSERT INTO jobs(path,hash,caption,brief,hypothesis,trial,due,created) VALUES(?,?,?,?,?,?,?,?)',
                (str(path),digest,caption,brief,hypothesis,'MANUAL',scheduled(due),now()))
            id=cur.lastrowid
            self.db.execute('INSERT INTO generated_plans VALUES(?,?,?,?,?)',
                (id,profile['name'],json.dumps(profile),json.dumps(plan),json.dumps(sources)))
            if audio: self.db.execute('INSERT INTO job_audio VALUES(?,?)',(id,json.dumps(audio)))
            return id

    def audio(self,id):
        row=self.db.execute('SELECT metadata FROM job_audio WHERE job_id=?',(id,)).fetchone()
        return json.loads(row[0]) if row else None

    def audio_report(self,profile=None,age=72):
        if age not in (24,72): raise ValueError('Age must be 24 or 72 hours')
        query='''SELECT g.profile,m.data,a.metadata FROM metrics m JOIN jobs j ON j.id=m.job_id
                 JOIN generated_plans g ON g.job_id=j.id LEFT JOIN job_audio a ON a.job_id=j.id
                 WHERE j.state='published' AND j.mode='live' AND m.age=?'''
        params=[age]
        if profile: query+=' AND g.profile=?'; params.append(profile)
        groups={}
        for row in self.db.execute(query,params):
            audio=json.loads(row['metadata']) if row['metadata'] else {'key':'none','title':'No added music','source':'none'}
            key=(row['profile'],audio['key']); g=groups.setdefault(key,{'profile':row['profile'],'key':audio['key'],
                'title':audio['title'],'source':audio['source'],'age':age,'records':0,'rates':[],'views':[]})
            g['records']+=1; values=json.loads(row['data']); views=values.get('views')
            valid=lambda x:type(x) in (int,float) and math.isfinite(x) and x>=0
            if valid(views) and views>0:
                g['views'].append(views); interactions=[values.get(k) for k in ('likes','comments','shares','saved')]
                if all(valid(x) for x in interactions): g['rates'].append(sum(interactions)/views)
        result=[]
        for g in groups.values():
            rates=g.pop('rates'); views=g.pop('views'); g['samples']=len(rates)
            g['mean_interactions_per_view']=round(sum(rates)/len(rates),6) if rates else None
            g['mean_views']=round(sum(views)/len(views),2) if views else None
            result.append(g)
        return sorted(result,key=lambda g:(g['profile'],g['key']))

    def generated(self,id):
        row=self.db.execute('SELECT * FROM generated_plans WHERE job_id=?',(id,)).fetchone()
        if not row: return None
        return {'profile':json.loads(row['profile_json']),'plan':json.loads(row['plan_json']),'sources':json.loads(row['sources_json'])}

    def used_sources(self):
        return {item['sha256'] for row in self.db.execute('SELECT sources_json FROM generated_plans')
                for item in json.loads(row['sources_json'])}

    def rows(self):
        return [dict(r) for r in self.db.execute('SELECT * FROM jobs ORDER BY id DESC')]

    def get(self, id):
        row = self.db.execute('SELECT * FROM jobs WHERE id=?', (id,)).fetchone()
        if row is None:
            raise ValueError('Unknown job')
        return dict(row)

    def approve(self, id, *, native_audio_reviewed=False):
        with self.db:
            audio=self.audio(id)
            if audio:
                from .audio import AudioCatalog
                if not AudioCatalog(self.config.data).is_enabled(audio['key']):
                    raise ValueError('Soundtrack is disabled or missing from the audio catalog')
            if audio and audio['source']=='native':
                if not native_audio_reviewed: raise ValueError('Review native music title, volumes and no-preview limitation before approval')
                if not self.config.dry_run and (not self.config.allow_native_audio or audio['account']!=self.config.user_id or self.config.login!='facebook'):
                    raise ValueError('Native audio is disabled or belongs to another account')
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
            job=dict(row); job['audio']=self.audio(job['id']); return job

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
