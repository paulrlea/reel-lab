from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from reel_lab.analysis import probe_video
from reel_lab.config import Config
from reel_lab.director import candidates, validate_plan, plan, NoFootage
from reel_lab.editor import render_plan
from reel_lab.footage import export, analyze_clip
from reel_lab.generate import generate, fill_queue
from reel_lab.media import fingerprint
from reel_lab.profile import Profile, save_profile, load_profile, profiles
from reel_lab.store import Store


def raw_plan():
    return {'concept':'Campus montage','clips':[{'id':'1','start':0,'duration':2}, {'id':'2','start':1,'duration':2}],
            'overlays':[{'text':'A day on campus','start':0,'end':2}], 'caption':'A campus moment',
            'hashtags':['#campus'], 'hypothesis':'Short opening hook'}


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.c=Config(Path(self.tmp.name),min_interval=0)
        self.s=Store(self.c); self.addCleanup(self.s.db.close)
        self.p=Profile.parse({'name':'campus','description':'campus life','min_duration':3,'max_duration':10})
        self.rows=[{'path':str(self.c.data/f'{i}.mov'),'sha256':str(i)*64,'duration_seconds':5,
                    'summary':'campus life','tagged_at':str(3-i)} for i in (1,2)]
        self.available=candidates(self.rows,self.p)

    def test_profile_round_trip(self):
        save_profile(self.c.data,self.p)
        self.assertEqual(load_profile(self.c.data,'campus'),self.p)
        self.assertEqual(profiles(self.c.data),['campus'])
        for name in ('../x','x/y',''):
            with self.assertRaises(ValueError): load_profile(self.c.data,name)
        with self.assertRaises(ValueError): Profile.parse({**asdict(self.p),'max_duration':True})

    def test_valid_plan(self):
        result=validate_plan(raw_plan(),self.available,self.p)
        self.assertEqual(result['duration'],4)
        self.assertEqual(result['hashtags'],['#campus'])

    def test_invalid_plan(self):
        changes=[{'clips':[{'id':'unlisted','start':0,'duration':4}]},
                 {'clips':[{'id':'1','start':4,'duration':3}]},
                 {'clips':[{'id':'1','start':float('nan'),'duration':4}]},
                 {'clips':[{'id':'1','start':0,'duration':4,'path':'unsafe'}]},
                 {'clips':[{'id':'1','start':0,'duration':2},{'id':'1','start':2,'duration':2}]},
                 {'overlays':[{'text':'hook','start':0,'end':99}]},
                 {'overlays':[{'text':'hook','start':0,'end':3},{'text':'again','start':1,'end':2}]},
                 {'hashtags':['#campus','#Campus']}, {'hashtags':['hashtag']}, {'commands':['ffmpeg']}]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate_plan({**raw_plan(),**change},self.available,self.p)

    def test_candidate_dedup_and_undescribed(self):
        self.assertEqual(len(candidates(self.rows+[self.rows[0]],self.p)),2)
        self.assertEqual(len(candidates(self.rows,self.p,{self.rows[0]['sha256']})),1)
        self.assertEqual(candidates([{**self.rows[0],'summary':''}],self.p),{})

    def test_director_retries_invalid_response(self):
        with patch('reel_lab.director.chat',side_effect=[{'clips':[]},raw_plan()]) as ai:
            result=plan(self.c,self.p,self.available)
            self.assertEqual(ai.call_count,2)
            self.assertEqual(result['duration'],4)
            self.assertNotIn(str(self.c.data),ai.call_args.args[2])
        with self.assertRaises(NoFootage): plan(self.c,self.p,{})

    def test_generation_inserts_draft_and_provenance(self):
        def fake_render(available,plan,out):
            out.parent.mkdir(parents=True,exist_ok=True); out.write_bytes(b'fake rendered video'); return out
        due=datetime.now(timezone.utc).isoformat()
        with patch('reel_lab.generate.footage.export',return_value=self.rows),patch('reel_lab.director.chat',return_value=raw_plan()),patch('reel_lab.generate.editor.render_plan',side_effect=fake_render):
            id=generate(self.c,self.s,self.p,due)
            self.assertEqual(self.s.get(id)['state'],'draft')
            self.assertIsNone(self.s.claim())
            record=self.s.generated(id)
            self.assertEqual(record['profile']['name'],'campus')
            self.assertEqual(record['plan']['duration'],4)
            self.assertEqual(self.s.used_sources(),{r['sha256'] for r in self.rows})
            self.assertIn('#campus',self.s.get(id)['caption'])
            self.assertIsNone(fill_queue(self.c,self.s,self.p,max_pending=1))
            with self.assertRaises(NoFootage): generate(self.c,self.s,self.p,due)

    def test_generation_failure_no_job(self):
        with patch('reel_lab.generate.footage.export',return_value=self.rows),patch('reel_lab.director.chat',return_value=raw_plan()),patch('reel_lab.generate.editor.render_plan',side_effect=ValueError('render failed')):
            with self.assertRaises(ValueError): generate(self.c,self.s,self.p,datetime.now(timezone.utc).isoformat())
            self.assertEqual(self.s.rows(),[])

    def test_profile_reuse_guard(self):
        sources=[{'sha256':'a'*64}]; due=datetime.now(timezone.utc).isoformat()
        self.s.add_generated('first','hash1','caption','brief','hypothesis',due,asdict(self.p),{},sources)
        with self.assertRaises(ValueError): self.s.add_generated('second','hash2','caption','brief','hypothesis',due,asdict(self.p),{},sources)
        self.assertEqual(len(self.s.rows()),1)

    def test_legacy_metadata_and_stale_catalog(self):
        path=self.c.data/'clip.MOV'; path.write_bytes(b'video'); stat=path.stat()
        db=self.c.data/'footage.sqlite3'
        with sqlite3.connect(db) as conn:
            conn.execute('CREATE TABLE footage (path TEXT, bytes INTEGER, mtime_ns INTEGER, sha256 TEXT, model TEXT, tagged_at TEXT, labels_json TEXT)')
            conn.execute('INSERT INTO footage VALUES(?,?,?,?,?,?,?)',(str(path),stat.st_size,stat.st_mtime_ns,fingerprint(path),'qwen3-vl:2b','today',json.dumps({'summary':'a clip','duration_seconds':5})))
        conn.close()
        self.assertEqual(export(db)[0]['summary'],'a clip')
        path.write_bytes(b'changed video')
        self.assertEqual(export(db),[])

    def test_probe_orientation_and_optional_transcription(self):
        output={'format':{'duration':'5'},'streams':[{'codec_type':'video','width':1920,'height':1080,'side_data_list':[{'rotation':90}]},{'codec_type':'audio'}]}
        with patch('reel_lab.analysis.subprocess.run',return_value=subprocess.CompletedProcess([],0,stdout=json.dumps(output))):
            metadata=probe_video('test.mov')
        self.assertEqual(metadata['orientation'],'portrait')
        self.assertTrue(metadata['has_audio'])
        path=self.c.data/'test.mov'; path.with_suffix('.txt').write_text('A campus scene',encoding='utf-8')
        with patch('reel_lab.footage.probe_video',return_value=metadata),patch('reel_lab.footage.transcribe',return_value='Hello there'):
            labels=analyze_clip(path,'http://localhost:11434',vision=False,whisper_cli='whisper',whisper_model='model',scenes=False)
        self.assertEqual(labels['transcript'],'Hello there')
        self.assertEqual(labels['brief'],'A campus scene')


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg not installed')
class RenderIntegration(unittest.TestCase):
    def test_real_render_mixed_audio_and_overlay(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root); paths=[folder/'source 1.mp4',folder/'source 2.mp4']
            for i,path in enumerate(paths):
                args=['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=blue:s=320x180:r=30']
                if i: args+=['-f','lavfi','-i','sine=frequency=440:sample_rate=48000']
                args+=['-t','5','-c:v','libx264','-pix_fmt','yuv420p',str(path)]
                subprocess.run(args,check=True,timeout=60)
            available={str(i+1):{'path':str(path),'sha256':fingerprint(path),'duration_seconds':5} for i,path in enumerate(paths)}
            p=Profile('test','synthetic test',min_duration=3,max_duration=10)
            raw=raw_plan(); raw['overlays'][0]['text']="100% 'safe': %{pts}"
            target=folder/'rendered.mp4'
            render_plan(available,validate_plan(raw,available,p),target)
            metadata=probe_video(target)
            self.assertEqual((metadata['width'],metadata['height']),(1080,1920))
            self.assertTrue(metadata['has_audio'])
            self.assertAlmostEqual(metadata['duration_seconds'],4,delta=0.75)


if __name__=='__main__': unittest.main()
