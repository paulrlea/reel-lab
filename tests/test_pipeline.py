from dataclasses import replace
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reel_lab.config import Config
from reel_lab.store import Store, scheduled
from reel_lab.media import fingerprint
from reel_lab.ai import caption_valid, draft
from reel_lab.worker import tick
from reel_lab.instagram import Instagram, PublishUncertain


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.c = Config(Path(self.tmp.name), min_interval=0)
        self.s = Store(self.c)
        self.addCleanup(self.s.db.close)
        self.path = self.c.data / 'clip.mp4'
        self.path.write_bytes(b'test clip')

    def add(self, name='test', due=None, strategy='MANUAL'):
        self.path.write_bytes(name.encode())
        return self.s.add(self.path, fingerprint(self.path), 'Caption', 'Brief', 'Hook', strategy, due or (datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat())

    def test_dry_run_requires_approval(self):
        id = self.add()
        self.assertIsNone(tick(self.c,self.s))
        self.s.approve(id)
        with patch('reel_lab.worker.Instagram') as api:
            self.assertEqual(tick(self.c,self.s), id)
            api.assert_not_called()
        self.assertEqual(self.s.get(id)['state'], 'simulated')
        self.assertIsNone(tick(self.c,self.s))

    def test_dry_approval_does_not_carry_to_live(self):
        id = self.add(); self.s.approve(id)
        live = replace(self.c, dry_run=False, allow_live=True)
        live_store = Store(live); self.addCleanup(live_store.db.close)
        self.assertIsNone(live_store.claim())
        self.s.reset_dry(id)
        self.assertEqual(self.s.get(id)['state'],'draft')

    def test_file_changed(self):
        id = self.add(); self.s.approve(id)
        self.path.write_bytes(b'changed')
        tick(self.c,self.s)
        self.assertEqual(self.s.get(id)['state'],'failed')

    def test_future_and_limits(self):
        id = self.add(due=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()); self.s.approve(id)
        self.assertIsNone(self.s.claim())
        for name in ('one','two'):
            id = self.add(name); self.s.approve(id); tick(self.c,self.s)
        id = self.add('three'); self.s.approve(id)
        self.assertIsNone(self.s.claim())

    def test_timezone_and_caption_validation(self):
        with self.assertRaises(ValueError): scheduled('2027-01-01T12:00:00')
        with self.assertRaises(ValueError): caption_valid('x'*2201)
        with self.assertRaises(ValueError): caption_valid('#'*31)

    def test_local_ai_json(self):
        with patch('reel_lab.ai.request', return_value={'message':{'content':'{"caption":"Great clip","hypothesis":"New hook"}'}}):
            self.assertEqual(draft(self.c,'brief',[]), ('Great clip','New hook'))

    def test_live_mock_trial_params_and_publish(self):
        c = replace(self.c,dry_run=False,allow_live=True,user_id='123',token='fake',upload='resumable')
        id = self.add(strategy='SS_PERFORMANCE'); job = self.s.get(id)
        with patch('reel_lab.instagram.request', side_effect=[{'id':'456'},{'success':True},{'status_code':'FINISHED'},{'id':'789'}]) as req:
            self.assertEqual(Instagram(c).publish(job),'789')
            self.assertEqual(req.call_args_list[0].kwargs['payload']['trial_params'],{'graduation_strategy':'SS_PERFORMANCE'})
            self.assertIn('ig-api-upload',req.call_args_list[1].args[0])
            self.assertEqual(req.call_args_list[-1].kwargs['payload'],{'creation_id':'456'})

    def test_ambiguous_publish_not_retried(self):
        c = replace(self.c,dry_run=False,allow_live=True,user_id='123',token='fake',upload='resumable')
        id = self.add(); job = self.s.get(id)
        with patch('reel_lab.instagram.request', side_effect=[{'id':'456'},{'success':True},{'status_code':'FINISHED'},RuntimeError('timeout')]) as req:
            with self.assertRaises(PublishUncertain): Instagram(c).publish(job)
            self.assertEqual(req.call_count,4)

    def test_live_guard(self):
        with self.assertRaises(ValueError): Instagram(self.c)

    def test_uncertain_blocks_next_live_job(self):
        c = replace(self.c,dry_run=False,allow_live=True)
        s = Store(c); self.addCleanup(s.db.close)
        id = self.add('first'); s.approve(id); s.claim(); s.finish(id,'uncertain')
        other = self.add('second'); s.approve(other)
        self.assertIsNone(s.claim())
        s.reconcile(id)
        self.assertEqual(s.claim()['id'],other)


if __name__ == '__main__': unittest.main()
