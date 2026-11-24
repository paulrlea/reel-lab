from array import array
from dataclasses import asdict,replace
from datetime import datetime,timezone
from pathlib import Path
import math
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import wave

from reel_lab.audio import AudioCatalog,NativeAudio,choose
from reel_lab.beats import analyze_beats,snap_plan
from reel_lab.config import Config
from reel_lab.editor import render_plan
from reel_lab.analysis import probe_video
from reel_lab.instagram import Instagram
from reel_lab.media import fingerprint
from reel_lab.profile import Profile
from reel_lab.store import Store
from reel_lab.generate import generate


def make_music(path):
    # A synthetic 120 BPM click track, not a copyrighted song.
    rate=8000; samples=array('h',(int(14000*math.sin(2*math.pi*440*i/rate)) if i%4000<320 else 0 for i in range(rate*10)))
    with wave.open(str(path),'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(rate); f.writeframes(samples.tobytes())


def native_row(id='123',eligible=True):
    return {'audio_id':id,'title':'Alpine','display_artist':'Artist','duration_in_ms':40000,'audio_type':'music','is_ads_eligible':eligible,'download_url':'https://example.com/temporary'}


class AudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.c=Config(Path(self.tmp.name),user_id='12345',token='secret',allow_native_audio=True,min_interval=0)
        self.catalog=AudioCatalog(self.c.data); self.s=Store(self.c); self.addCleanup(self.s.db.close)
        self.p=Profile('talon','Mountain climbing',music_preferences='cinematic alpine',audio_mode='auto',min_duration=3)
        self.clip={'1':{'duration_seconds':10,'summary':'mountain climbing','tags':['alpine'],'transcript':''},'2':{'duration_seconds':10}}
        self.plan={'concept':'Alpine montage','clips':[{'id':'1','start':0,'duration':2.2},{'id':'2','start':0,'duration':2.8}], 'duration':5,'overlays':[]}

    def test_discovery_and_manual_research(self):
        with patch('reel_lab.audio.request',return_value={'audio':[native_row(),native_row('456',False)]}) as api:
            rows=self.catalog.discover(self.c,'')
            self.assertEqual(len(rows),2)
            self.assertNotIn('secret',api.call_args.args[0]); self.assertIn('audio_type=music',api.call_args.args[0])
            self.assertNotIn('download_url',rows[0]); self.assertEqual(self.catalog.discoveries()[0]['query'],'')
        ref=self.catalog.add_reference('https://www.instagram.com/reel/abc/?igsh=private','mammut','Alpine','Artist','climbing',rows[0]['key'])
        self.assertEqual(ref['url'],'https://www.instagram.com/reel/abc/')
        self.assertEqual(len(self.catalog.references()),1)
        with self.assertRaises(ValueError): self.catalog.add_reference('https://example.com/reel/x','mammut','Song','Artist')
        with patch('reel_lab.audio.request',return_value={'business_discovery':{'media':{'data':[{'media_product_type':'REELS','media_audio_type':'MUSIC','permalink':ref['url']},{'media_product_type':'FEED','permalink':'https://www.instagram.com/p/x/'}]}}}):
            research=self.catalog.research(self.c,'mammut')
        self.assertEqual(len(research),1); self.assertNotIn('title',research[0]); self.assertEqual(research,self.catalog.research_posts())

    def test_native_eligibility_and_selection(self):
        with patch('reel_lab.audio.request',return_value={'audio':[native_row(),native_row('456',False)]}): self.catalog.discover(self.c)
        with patch('reel_lab.audio.chat',return_value={'id':'999','reason':'invented'}):
            selected=choose(self.c,self.s,self.p,self.plan,self.clip,self.catalog)
        self.assertEqual(selected['audio_id'],'123'); self.assertEqual(selected['mix_style'],'cinematic')
        with self.assertRaises(ValueError): choose(replace(self.c,allow_native_audio=False),self.s,self.p,self.plan,self.clip,self.catalog)
        with self.assertRaises(ValueError): choose(replace(self.c,user_id='999'),self.s,self.p,self.plan,self.clip,self.catalog)
        self.assertIsNone(choose(self.c,self.s,replace(self.p,audio_mode='off'),self.plan,self.clip,self.catalog))
        self.catalog.set_enabled(selected['key'],False)
        with self.assertRaises(ValueError): choose(self.c,self.s,self.p,self.plan,self.clip,self.catalog)
        self.catalog.set_enabled(selected['key'],True)
        self.assertTrue(self.catalog.is_enabled(selected['key']))

    def test_native_review_and_publish_exact_parameters(self):
        c=replace(self.c,dry_run=False,allow_live=True)
        with patch('reel_lab.audio.request',return_value={'audio':[native_row()]}): self.catalog.discover(self.c)
        with patch('reel_lab.audio.chat',return_value={'id':'0'}): a=choose(self.c,self.s,self.p,self.plan,self.clip,self.catalog)
        p=self.c.data/'video.mp4'; p.write_bytes(b'video')
        id=self.s.add_generated(p,fingerprint(p),'caption','concept','hypothesis',datetime.now(timezone.utc).isoformat(),asdict(self.p),self.plan,[{'sha256':'a'*64}],audio=a)
        with self.assertRaises(ValueError): self.s.approve(id)
        self.s.approve(id,native_audio_reviewed=True); job=self.s.claim()
        self.assertEqual(job['audio']['audio_id'],'123')
        with patch('reel_lab.audio.request',return_value=native_row(eligible=False)),patch('reel_lab.instagram.request') as api:
            with self.assertRaises(ValueError): Instagram(c).publish(job)
            api.assert_not_called()
        with patch('reel_lab.audio.request',return_value=native_row()),patch('reel_lab.instagram.request',side_effect=[{'id':'456'},{'success':True},{'status_code':'FINISHED'},{'id':'789'}]) as api:
            self.assertEqual(Instagram(c).publish(job),'789')
            body=api.call_args_list[0].kwargs['payload']; self.assertEqual(body['audio_configuration'],{'audio_id':'123','audio_volume':80,'video_volume':35}); self.assertIn('trial_params',body)
        self.s.db.execute("UPDATE jobs SET state='published',mode='live' WHERE id=?",(id,)); self.s.db.commit()
        self.s.save_metrics(id,72,{'views':100,'likes':5,'comments':1,'shares':2,'saved':2})
        self.assertEqual(self.s.audio_report('talon',72)[0]['mean_interactions_per_view'],.1)
        self.assertEqual(self.s.audio_report('talon',24),[])

    def test_local_registration_requires_rights(self):
        with self.assertRaises(ValueError): self.catalog.register_local('file.wav','Title','Artist','ambient','')

    def test_beat_snap_bounded(self):
        plan,shifts=snap_plan(self.plan,self.clip,[2.0,2.5,3.0]); self.assertEqual(plan['clips'][0]['duration'],2.0)
        self.assertEqual(plan['duration'],5); self.assertEqual(shifts[0]['at'],2.0)
        constrained={**self.clip,'2':{'duration_seconds':2.8}}
        plan,shifts=snap_plan(self.plan,constrained,[2.0]); self.assertEqual(shifts,[])

    def test_generation_persists_local_audio_and_snapped_plan(self):
        track=self.c.data/'track.wav'; track.write_bytes(b'fake music')
        with patch('reel_lab.audio.probe_audio',return_value=20),patch('reel_lab.audio.analyze_beats',return_value={'bpm':120,'beats':[2,2.5,3],'confidence':.9}):
            local=self.catalog.register_local(track,'Alpine','Artist','cinematic alpine','Verified test license',rights_confirmed=True,ads_eligible=True)
        footage=[{'path':str(self.c.data/f'{i}.mov'),'sha256':str(i)*64,'duration_seconds':10,'summary':'mountain climbing','tagged_at':str(3-i)} for i in (1,2)]
        plan={**self.plan,'caption':'Alpine','hashtags':['#mountains'],'hypothesis':'Edit to beat'}
        def fake_render(available,plan,out,*,audio):
            self.assertEqual(plan['clips'][0]['duration'],2)
            self.assertEqual(audio['key'],local['key']); out.parent.mkdir(parents=True,exist_ok=True); out.write_bytes(b'output')
        with patch('reel_lab.generate.footage.export',return_value=footage),patch('reel_lab.generate.director.plan',return_value=plan),patch('reel_lab.audio.chat',return_value={'id':'0'}),patch('reel_lab.generate.editor.render_plan',side_effect=fake_render):
            id=generate(self.c,self.s,replace(self.p,audio_mode='local'),datetime.now(timezone.utc).isoformat())
        self.assertEqual(self.s.get(id)['state'],'draft'); self.assertEqual(self.s.audio(id)['beat_shifts'][0]['at'],2)
        self.catalog.set_enabled(local['key'],False)
        with self.assertRaises(ValueError): self.s.approve(id)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg not installed')
class AudioIntegration(unittest.TestCase):
    def test_real_beat_analysis_and_mixed_reel(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root); track=folder/'click.wav'; make_music(track)
            detected=analyze_beats(track); self.assertAlmostEqual(detected['bpm'],120,delta=3); self.assertGreater(detected['confidence'],.65)
            catalog=AudioCatalog(folder); music=catalog.register_local(track,'Click','Test','cinematic','Synthetic test audio',rights_confirmed=True,ads_eligible=True)
            clip=folder/'clip.mp4'
            subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=blue:s=320x180:r=30','-f','lavfi','-i','sine=frequency=300:sample_rate=48000','-t','5','-c:v','libx264','-pix_fmt','yuv420p',str(clip)],check=True,timeout=60)
            available={'1':{'path':str(clip),'sha256':fingerprint(clip),'duration_seconds':5}}
            plan={'clips':[{'id':'1','start':0,'duration':4}],'duration':4,'overlays':[]}
            for style in ('cinematic','dialogue'):
                out=folder/f'{style}.mp4'
                render_plan(available,plan,out,audio={**music,'music_volume':50,'video_volume':80,'mix_style':style})
                data=probe_video(out); self.assertTrue(data['has_audio']); self.assertAlmostEqual(data['duration_seconds'],4,delta=.75)
                self.assertEqual((data['width'],data['height']),(1080,1920))
