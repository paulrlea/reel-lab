from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reel_lab.acquire import register, materialize
from reel_lab.audio import AudioCatalog
from reel_lab.config import Config


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.config=Config(Path(self.tmp.name),allow_spotdl=True)
        self.catalog=AudioCatalog(self.config.data)
        self.spotify='https://open.spotify.com/track/'+'A'*22
        self.youtube='https://www.youtube.com/watch?v='+'B'*11

    def register(self,**kwargs):
        return register(self.catalog,self.spotify,self.youtube,'Test','Artist','ambient','Authorized test recording',30,**kwargs)

    def test_explicit_rights_and_exact_urls(self):
        with self.assertRaises(ValueError): self.register()
        self.youtube='https://www.youtube.com/playlist?list=abc'
        with self.assertRaises(ValueError): self.register(rights_confirmed=True)

    def test_selected_download_cache_and_disable(self):
        track=self.register(rights_confirmed=True,ads_eligible=True)
        selected={**track,'require_ads':True,'requested_duration':10,'mix_style':'cinematic'}
        def fake_run(args,**kwargs):
            self.assertIn(self.youtube+'|'+self.spotify,args)
            (kwargs['cwd']/('A'*22+'.mp3')).write_bytes(b'synthetic authorized recording')
        with patch('reel_lab.acquire.subprocess.run',side_effect=fake_run) as download,patch('reel_lab.acquire.probe_audio',return_value=30),patch('reel_lab.acquire.analyze_beats',return_value={'bpm':120,'beats':[1,2],'confidence':.9}):
            with self.assertRaises(ValueError): materialize(replace(self.config,allow_spotdl=False),self.catalog,selected)
            result=materialize(self.config,self.catalog,selected)
            self.assertEqual(result['bpm'],120); self.assertTrue(Path(result['path']).is_file())
            self.assertEqual(materialize(self.config,self.catalog,selected)['sha256'],result['sha256'])
            self.assertEqual(download.call_count,1)
            self.catalog.set_enabled(track['key'],False)
            with self.assertRaises(ValueError): materialize(self.config,self.catalog,selected)

    def test_duration_mismatch_not_cached(self):
        track=self.register(rights_confirmed=True)
        def fake_run(args,**kwargs): (kwargs['cwd']/('A'*22+'.mp3')).write_bytes(b'wrong recording')
        with patch('reel_lab.acquire.subprocess.run',side_effect=fake_run),patch('reel_lab.acquire.probe_audio',return_value=40):
            with self.assertRaises(ValueError): materialize(self.config,self.catalog,{**track,'require_ads':False,'requested_duration':10})
        self.assertFalse(self.catalog.tracks()[0]['path'])
