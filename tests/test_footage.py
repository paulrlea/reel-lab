import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from reel_lab.config import Config
from reel_lab.footage import FootageWatcher


class FootageTests(unittest.TestCase):
    def test_stability_and_duplicate_import(self):
        with tempfile.TemporaryDirectory() as root:
            config = Config(Path(root))
            watcher = FootageWatcher(config, Path(root)/'incoming', 30)
            source = watcher.folder/'IMG_0001.MOV'
            source.write_bytes(b'video bytes')
            with patch('reel_lab.footage.time.monotonic', return_value=100):
                self.assertEqual(watcher.scan(), [])
            with patch('reel_lab.footage.time.monotonic', return_value=131):
                dest, = watcher.scan()
                self.assertEqual(dest.read_bytes(), source.read_bytes())
                self.assertEqual(watcher.scan(), [])
            duplicate = watcher.folder/'IMG_0002.mov'
            duplicate.write_bytes(source.read_bytes())
            with patch('reel_lab.footage.time.monotonic', return_value=132): watcher.scan()
            with patch('reel_lab.footage.time.monotonic', return_value=163):
                self.assertEqual(watcher.scan(), [])
            self.assertTrue(source.exists())
