from pathlib import Path
import shutil
import subprocess
import unittest


class ProbeLogicTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is required for the DOM logic test')
    def test_touch_counts_never_include_pointer_ids(self):
        subprocess.run(['node', str(Path(__file__).with_suffix('.js'))], check=True)
