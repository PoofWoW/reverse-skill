#!/usr/bin/env python3
"""Read a deb without installing it. Reject non-SpringBoard injection filters."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import plistlib
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from macho_audit import inspect_macho


def members(blob):
    if blob[:8] != b'!<arch>\n':
        raise ValueError('not a Debian ar archive')
    pos = 8
    result = {}
    while pos < len(blob):
        header = blob[pos:pos+60]
        if len(header) != 60 or header[-2:] != b'`\n':
            raise ValueError('invalid ar member')
        name = header[:16].decode('ascii').strip().rstrip('/')
        size = int(header[48:58])
        if name in result or size < 0 or pos+60+size > len(blob):
            raise ValueError('invalid ar size or duplicate member')
        result[name] = blob[pos+60:pos+60+size]
        pos += 60+size+(size%2)
    return result


def tar_members(blob, require_root=True):
    with tarfile.open(fileobj=io.BytesIO(blob), mode='r:*') as archive:
        result = {}
        for member in archive:
            path = str(PurePosixPath(member.name))
            if path.startswith('/') or '..' in PurePosixPath(path).parts or path in result:
                raise ValueError('unsafe or duplicate tar path')
            if require_root and (member.uid != 0 or member.gid != 0):
                raise ValueError('package payload not owned by root/wheel: ' + path)
            if member.isdir() and member.mode & 0o777 != 0o755:
                raise ValueError('unsafe directory permissions: ' + path)
            if member.issym() or member.islnk():
                raise ValueError('unexpected archive link: ' + path)
            if member.isfile():
                if member.mode & 0o777 not in (0o644, 0o755):
                    raise ValueError('unsafe file permissions: ' + path)
                if path in ('preinst', 'postinst', 'prerm', 'postrm') and member.mode & 0o111 == 0:
                    raise ValueError('maintainer script not executable: ' + path)
                if member.size > 32*1024*1024:
                    raise ValueError('unexpectedly large file')
                content = archive.extractfile(member).read()
                if content[:4] in (b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe') and member.mode & 0o111 == 0:
                    raise ValueError('Mach-O payload not executable: ' + path)
                result[path] = content
        return result


def audit(path, expected_commit=None):
    blob = Path(path).read_bytes()
    ar = members(blob)
    if ar.get('debian-binary') != b'2.0\n':
        raise ValueError('unsupported deb format')
    control = tar_members(next(value for key, value in ar.items() if key.startswith('control.tar')), require_root=False)
    data = tar_members(next(value for key, value in ar.items() if key.startswith('data.tar')))
    fields = dict(line.split(': ', 1) for line in control['control'].decode().splitlines() if ': ' in line)
    if fields.get('Package') != 'com.zjx.ioscontrol':
        raise ValueError('wrong package identity / cannot replace official ZXTouch')
    if 'ellekit' not in fields.get('Depends', '') or 'firmware (>= 15.0)' not in fields.get('Depends', ''):
        raise ValueError('missing Rootless dependencies')
    if fields['Architecture'] != 'iphoneos-arm64' or '~touchtest.' not in fields['Version']:
        raise ValueError('not a rootless experimental touch package')
    dylibs = sorted(path for path in data if path.endswith('.dylib'))
    prefix = 'var/jb/Library/MobileSubstrate/DynamicLibraries/'
    if dylibs != [prefix+'pccontrol.dylib']:
        raise ValueError('unexpected dylibs: ' + repr(dylibs))
    filters = {path:plistlib.loads(value) for path, value in data.items()
               if '/DynamicLibraries/' in path and path.endswith('.plist')}
    expected = {prefix+'pccontrol.plist':{'Filter':{'Bundles':['com.apple.springboard']}}}
    if filters != expected:
        raise ValueError('App-process injection filter present, or unexpected tweak filter')
    for path in data:
        if not path.startswith('var/jb/'):
            raise ValueError('payload outside rootless prefix: ' + path)
        if 'appdelegate' in path.lower() or '__pycache__' in path or path.endswith('postinst-roothide'):
            raise ValueError('unwanted test-package content: ' + path)
    app = 'var/jb/Applications/zxtouch.app/'
    extension = app + 'PlugIns/shortcutext.appex/'
    executables = {prefix+'pccontrol.dylib':6, app+'zxtouch':2,
                   extension+'shortcutext':2, 'var/jb/usr/bin/zxtouchb':2,
                   'var/jb/usr/libexec/zxtouch-runner':2}
    required = [app+'Info.plist', extension+'Info.plist',
                'var/jb/usr/share/zxtouch/python/zxtouch/client.py',
                'var/jb/usr/share/zxtouch/python/zxtouch/tasktypes.py',
                'var/jb/usr/share/zxtouch/diagnostics/touch-probe.html',
                'var/jb/usr/share/zxtouch/diagnostics/mixed_touch.py'] + list(executables)
    if any(name not in data for name in required):
        raise ValueError('incomplete full ZXTouch payload: ' + repr([p for p in required if p not in data]))
    if any('ZXTouchProbe.app/' in name for name in data):
        raise ValueError('receiver package path conflict: do not bundle ZXTouchProbe.app')
    for location, identifier in [(app, 'com.zjx.zxtouch'), (extension, 'com.zjx.zxtouch.shortcutext')]:
        info = plistlib.loads(data[location+'Info.plist'])
        if info.get('CFBundleIdentifier') != identifier:
            raise ValueError('wrong/duplicate App or extension bundle ID')
        version = tuple(int(v) for v in info.get('MinimumOSVersion', '999').split('.'))
        if (version + (0, 0, 0))[:3] > (16, 1, 1):
            raise ValueError('App Info.plist requires newer iOS')
    metadata = {name:inspect_macho(data[name], kind, require_arm64e=True)
                for name, kind in executables.items()}
    # All packaged Mach-O must be accounted for; no stale extra binary escapes.
    for name, content in data.items():
        if content[:4] in (b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe') and name not in executables:
            raise ValueError('unexpected Mach-O payload: ' + name)
    patched = data[prefix+'pccontrol.dylib']
    for marker in (b'ZXTouchTouch:', b'buildCommit', b'slot-owned-by-another-client'):
        if marker not in patched:
            raise ValueError('missing compiled touch lifecycle patch marker')
    if expected_commit is not None:
        if len(expected_commit) != 40 or any(c not in '0123456789abcdef' for c in expected_commit):
            raise ValueError('invalid expected source commit')
        if expected_commit.encode('ascii') not in patched:
            raise ValueError('compiled sender buildCommit does not match source commit')
    for script in ('postinst', 'prerm'):
        if script not in control:
            raise ValueError('missing maintainer script: ' + script)
    return {'sha256':hashlib.sha256(blob).hexdigest(),'size':len(blob),'control':fields,
            'filters':filters,'machO':metadata,'payloadFileCount':len(data),
            'sourceCommit':expected_commit, 'containsFullZXTouch':True,
            'signatureValidation':'structure only; no device trust or delivery assertion',
            'deviceValidated':False, 'foregroundReceiptVerified':False,
            'status':'full-package-structure-verified; NOT DEVICE VALIDATED'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('deb')
    parser.add_argument('--expected-commit')
    args = parser.parse_args()
    print(json.dumps(audit(args.deb, args.expected_commit), indent=2))
