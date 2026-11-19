import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TouchStateTests(unittest.TestCase):
    def test_portable_production_state_machine(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = str(Path(directory) / 'touch-state-tests')
            flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-g']
            if os.environ.get('SANITIZE') == '1':
                flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
            command = shlex.split(os.environ.get('CC', 'cc')) + flags + [
                '-I' + str(ROOT / 'pccontrol'),
                str(ROOT / 'pccontrol/TouchState.c'),
                str(ROOT / 'tests/touch_state_test.c'), '-o', binary]
            subprocess.run(command, check=True)
            subprocess.run([binary], check=True)
