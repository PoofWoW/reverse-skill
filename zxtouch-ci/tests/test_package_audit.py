import importlib.util
import io
from pathlib import Path
import plistlib
from test_macho_audit import macho_fixture
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('audit_touch_deb', Path(__file__).resolve().parents[1] / 'tools/audit_touch_deb.py')
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)
PREFIX = 'var/jb/Library/MobileSubstrate/DynamicLibraries/'


def tar(files, dir_mode=0o755, uid=0):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as archive:
        directory = tarfile.TarInfo('.')
        directory.type = tarfile.DIRTYPE
        directory.mode = dir_mode
        directory.uid = directory.gid = uid
        archive.addfile(directory)
        for name, payload in files.items():
            member = tarfile.TarInfo(name)
            member.mode = 0o755 if name in ('postinst', 'prerm') or payload[:4] == b'\xca\xfe\xba\xbe' else 0o644
            member.size = len(payload)
            member.uid = member.gid = uid
            archive.addfile(member, io.BytesIO(payload))
    return buf.getvalue()


def deb(files, dir_mode=0o755):
    control = b'Package: com.zjx.ioscontrol\nArchitecture: iphoneos-arm64\nVersion: 1.0.1~touchtest.1\nDepends: mobilesubstrate | ellekit, firmware (>= 15.0)\n'
    ar = bytearray(b'!<arch>\n')
    for name, data in [('debian-binary', b'2.0\n'), ('control.tar.gz', tar({'control':control, 'postinst':b'#!/bin/sh\n', 'prerm':b'#!/bin/sh\n'})), ('data.tar.gz', tar(files, dir_mode))]:
        ar.extend(('{:<16}{:<12}{:<6}{:<6}{:<8}{:<10}`\n'.format(name, 0, 0, 0, '100644', len(data))).encode('ascii'))
        ar.extend(data)
        if len(data)%2:
            ar.extend(b'\n')
    return ar


def payload(subtype=0x80000002):
    macho = macho_fixture(subtype=subtype)
    app = 'var/jb/Applications/zxtouch.app/'
    ext = app+'PlugIns/shortcutext.appex/'
    files = {PREFIX+'pccontrol.dylib':macho+b'ZXTouchTouch: buildCommit slot-owned-by-another-client',
             PREFIX+'pccontrol.plist':plistlib.dumps({'Filter':{'Bundles':['com.apple.springboard']}}),
             'var/jb/usr/share/zxtouch/diagnostics/touch-probe.html':b'fixture',
             'var/jb/usr/share/zxtouch/diagnostics/mixed_touch.py':b'fixture',
             app+'Info.plist':plistlib.dumps({'CFBundleIdentifier':'com.zjx.zxtouch','MinimumOSVersion':'15.0'}),
             ext+'Info.plist':plistlib.dumps({'CFBundleIdentifier':'com.zjx.zxtouch.shortcutext','MinimumOSVersion':'15.0'}),
             'var/jb/usr/share/zxtouch/python/zxtouch/client.py':b'fixture',
             'var/jb/usr/share/zxtouch/python/zxtouch/tasktypes.py':b'fixture'}
    for path in (app+'zxtouch',ext+'shortcutext','var/jb/usr/bin/zxtouchb','var/jb/usr/libexec/zxtouch-runner'):
        files[path] = macho_fixture(filetype=2)
    return files



class PackageAuditTests(unittest.TestCase):
    def audit(self, files, mode=0o755):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'test.deb'
            path.write_bytes(deb(files, mode))
            return audit_module.audit(path)

    def test_springboard_filter_and_modern_abi_gate(self):
        self.assertIn('NOT DEVICE VALIDATED', self.audit(payload())['status'])

    def test_app_injection_is_rejected(self):
        files = payload()
        files[PREFIX+'pccontrol.plist'] = plistlib.dumps({'Filter':{'Bundles':['com.apple.UIKit']}})
        with self.assertRaisesRegex(ValueError, 'App-process injection'):
            self.audit(files)
        files = payload()
        files[PREFIX+'appdelegate.dylib'] = b'fixture'
        with self.assertRaisesRegex(ValueError, 'unexpected dylibs'):
            self.audit(files)

    def test_old_arm64e_abi_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unexpected Mach-O architectures'):
            self.audit(payload(subtype=2))

    def test_umask_077_prefix_directories_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unsafe directory permissions'):
            self.audit(payload(), mode=0o700)

    def test_receiver_only_or_incomplete_package_is_rejected(self):
        files = payload()
        del files['var/jb/Applications/zxtouch.app/zxtouch']
        with self.assertRaisesRegex(ValueError, 'incomplete full ZXTouch'):
            self.audit(files)

    def test_bundled_receiver_conflict_is_rejected(self):
        files = payload()
        files['var/jb/Applications/ZXTouchProbe.app/ZXTouchProbe'] = b'fixture'
        with self.assertRaisesRegex(ValueError, 'receiver package path conflict'):
            self.audit(files)

    def test_duplicate_extension_bundle_id_is_rejected(self):
        files = payload()
        files['var/jb/Applications/zxtouch.app/PlugIns/shortcutext.appex/Info.plist'] = plistlib.dumps(
            {'CFBundleIdentifier':'com.zjx.zxtouch','MinimumOSVersion':'15.0'})
        with self.assertRaisesRegex(ValueError, 'bundle ID'):
            self.audit(files)

    def test_unpatched_sender_is_rejected(self):
        files = payload()
        files[PREFIX+'pccontrol.dylib'] = macho_fixture()
        with self.assertRaisesRegex(ValueError, 'missing compiled touch'):
            self.audit(files)

    def test_repack_normalizes_numeric_owners_without_changing_files(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
        from normalize_deb_ownership import normalize
        # Model the published package's mismatch: operator numeric UID/GID.
        original = payload()
        archive = bytearray(b'!<arch>\n')
        control = b'Package: com.zjx.ioscontrol\n'
        for name, value in [('debian-binary',b'2.0\n'),('control.tar.gz',tar({'control':control},uid=501)),('data.tar.gz',tar(original,uid=501))]:
            archive.extend(('{:<16}{:<12}{:<6}{:<6}{:<8}{:<10}`\n'.format(name,0,0,0,'100644',len(value))).encode('ascii'))
            archive.extend(value)
            if len(value)%2: archive.extend(b'\n')
        ar = audit_module.members(bytes(archive))
        with self.assertRaisesRegex(ValueError, 'not owned by root'):
            audit_module.tar_members(ar['data.tar.gz'])
        normalized = audit_module.members(normalize(bytes(archive)))
        self.assertEqual(audit_module.tar_members(normalized['data.tar.gz']), original)
