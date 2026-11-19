#!/usr/bin/env python3
"""Fail early rather than emit an incompatible Rootless arm64e candidate."""
import json
import os
from pathlib import Path
import platform
import struct
import subprocess
import tempfile


def output(*cmd):
    return subprocess.check_output(cmd, text=True).strip()


def main():
    if platform.system() != 'Darwin':
        raise SystemExit('Full arm64e candidate requires Apple Xcode on macOS; Linux is not accepted')
    developer = os.environ.get('DEVELOPER_DIR', '')
    if not developer or not Path(developer).is_dir():
        raise SystemExit('Set DEVELOPER_DIR to the selected Xcode before building')
    clang = output('xcrun', '--sdk', 'iphoneos', '--find', 'clang')
    version = output(clang, '--version')
    if 'Apple clang' not in version:
        raise SystemExit('Compiler is not Apple Clang')
    sdk = Path(os.environ['THEOS']) / 'sdks/iPhoneOS16.5.sdk'
    with tempfile.TemporaryDirectory() as directory:
        source, obj = Path(directory)/'abi-probe.m', Path(directory)/'abi-probe.o'
        source.write_text('int zxtouch_arm64e_build_probe(void) { return 1611; }\n')
        subprocess.run([clang, '-target', 'arm64e-apple-ios15.0', '-isysroot', str(sdk),
                        '-c', str(source), '-o', str(obj)], check=True)
        data = obj.read_bytes()
        if struct.unpack_from('<4I', data) != (0xFEEDFACF, 0x0100000C, 0x80000002, 1):
            raise SystemExit('Apple compiler did not emit the current arm64e object ABI; do not relabel it')
    metadata = {'platform':platform.platform(),'developerDir':developer,
                'xcode':output('xcodebuild', '-version'),'clang':version,
                'theosCommit':output('git', '-C', os.environ['THEOS'], 'rev-parse', 'HEAD'),
                'theosSDK':str(sdk), 'deploymentIOS':'15.0','targetIOS':'16.1.1',
                'objectSubtype':'0x80000002', 'deviceValidated':False}
    Path('toolchain-info.json').write_text(json.dumps(metadata, indent=2)+'\n')
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    main()
