"""Structural Mach-O fixtures, deliberately NOT runnable or cryptographically signed.

The fixtures model real fat/slice headers, load command bounds and an embedded
SuperBlob/CodeDirectory so an architecture label alone cannot satisfy the gate.
"""
import importlib.util
from pathlib import Path
import struct
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('macho_audit', ROOT / 'tools/macho_audit.py')
macho_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(macho_module)
inspect_macho = macho_module.inspect_macho

CPU_ARM64 = 0x0100000C
ARM64E_CURRENT = 0x80000002
LC_BUILD_VERSION = 0x32
LC_LOAD_DYLIB = 0x0C
LC_RPATH = 0x8000001C
LC_CODE_SIGNATURE = 0x1D


def _align(value, alignment):
    return (value + alignment - 1) & ~(alignment - 1)


def _string_command(command, value, fixed_size):
    value = value.encode('utf-8') + b'\0'
    size = _align(fixed_size + len(value), 8)
    if command == LC_LOAD_DYLIB:
        header = struct.pack('<6I', command, size, fixed_size, 0, 0, 0)
    else:
        header = struct.pack('<3I', command, size, fixed_size)
    return header + value + b'\0' * (size - fixed_size - len(value))


def _thin_fixture(subtype, filetype, platform, minos, dependency, signature,
                  rpath='/var/jb/Library/Frameworks'):
    commands = [struct.pack('<6I', LC_BUILD_VERSION, 24, platform, minos, 0x00100500, 0),
                _string_command(LC_LOAD_DYLIB, dependency, 24),
                _string_command(LC_RPATH, rpath, 12)]
    count = len(commands) + int(signature)
    command_size = sum(map(len, commands)) + (16 if signature else 0)
    content_end = _align(32 + command_size, 16)
    superblob = b''
    if signature:
        # CodeDirectory v0x20001's fixed prefix is 44 bytes. Add a NUL-terminated
        # identifier and one SHA-256 slot in bounds, but no real hash validation.
        identifier = b'fixture\0'
        hash_offset = 44 + len(identifier)
        cd_size = hash_offset + 32
        code_directory = struct.pack('>9I4BI',
            0xFADE0C02, cd_size, 0x20001, 0, hash_offset, 44,
            0, 1, content_end, 32, 2, 0, 12, 0) + identifier + b'\0' * 32
        superblob_size = 20 + len(code_directory)
        superblob = struct.pack('>5I', 0xFADE0CC0, superblob_size, 1, 0, 20) + code_directory
        commands.append(struct.pack('<4I', LC_CODE_SIGNATURE, 16, content_end, len(superblob)))
    header = struct.pack('<8I', 0xFEEDFACF, CPU_ARM64, subtype, filetype,
                         count, command_size, 0x85, 0)
    content = header + b''.join(commands)
    return content + b'\0' * (content_end - len(content)) + superblob


def _fat_fixture(first, second, subtype):
    first_offset = 4096
    second_offset = _align(first_offset + len(first), 4096)
    header = struct.pack('>2I', 0xCAFEBABE, 2)
    header += struct.pack('>5I', CPU_ARM64, 0, first_offset, len(first), 12)
    header += struct.pack('>5I', CPU_ARM64, subtype, second_offset, len(second), 12)
    blob = bytearray(second_offset + len(second))
    blob[:len(header)] = header
    blob[first_offset:first_offset + len(first)] = first
    blob[second_offset:second_offset + len(second)] = second
    return bytes(blob)


def macho_fixture(subtype=ARM64E_CURRENT, filetype=6, platform=2,
                  minos=0x0F0000, dependency='/usr/lib/libSystem.B.dylib', signature=True):
    """Return a structurally valid fat arm64 + arm64e synthetic fixture."""
    first = _thin_fixture(0, filetype, platform, minos, dependency, signature)
    second = _thin_fixture(subtype, filetype, platform, minos, dependency, signature)
    return _fat_fixture(first, second, subtype)


def _slice_offset(blob, index=1):
    return struct.unpack_from('>I', blob, 8 + index * 20 + 8)[0]


def _command_offset(blob, command, index=1):
    offset = _slice_offset(blob, index)
    count = struct.unpack_from('<I', blob, offset + 16)[0]
    cursor = offset + 32
    for _ in range(count):
        cmd, size = struct.unpack_from('<2I', blob, cursor)
        if cmd == command:
            return cursor
        cursor += size
    raise AssertionError('fixture command missing')


class MachOAuditTests(unittest.TestCase):
    def test_accepts_realistic_headers_and_structural_signature(self):
        metadata = inspect_macho(macho_fixture(), expected_type=6, require_arm64e=True)
        self.assertEqual(len(metadata), 2)
        self.assertTrue(all(isinstance(item, dict) for item in metadata))

    def test_accepts_executable_when_requested(self):
        self.assertEqual(len(inspect_macho(macho_fixture(filetype=2), expected_type=2)), 2)

    def test_accepts_substrate_only_with_rootless_framework_rpath(self):
        value = '@rpath/CydiaSubstrate.framework/CydiaSubstrate'
        self.assertEqual(len(inspect_macho(macho_fixture(dependency=value))), 2)
        first = _thin_fixture(0, 6, 2, 0x0F0000, value, True, rpath='@executable_path/Frameworks')
        second = _thin_fixture(ARM64E_CURRENT, 6, 2, 0x0F0000, value, True,
                               rpath='@executable_path/Frameworks')
        with self.assertRaises(ValueError):
            inspect_macho(_fat_fixture(first, second, ARM64E_CURRENT))

    def test_rejects_legacy_arm64e_abi(self):
        with self.assertRaises(ValueError):
            inspect_macho(macho_fixture(subtype=2))

    def test_rejects_outer_modern_label_on_legacy_slice(self):
        blob = bytearray(macho_fixture())
        struct.pack_into('<I', blob, _slice_offset(blob) + 8, 2)
        with self.assertRaises(ValueError):
            inspect_macho(bytes(blob))

    def test_rejects_inner_outer_cpu_mismatch(self):
        blob = bytearray(macho_fixture())
        struct.pack_into('<I', blob, _slice_offset(blob) + 4, 0x01000007)
        with self.assertRaises(ValueError):
            inspect_macho(bytes(blob))

    def test_rejects_truncated_fat_header(self):
        with self.assertRaises(ValueError):
            inspect_macho(macho_fixture()[:40])

    def test_rejects_overlapping_slices(self):
        blob = bytearray(macho_fixture())
        struct.pack_into('>I', blob, 8 + 20 + 8, _slice_offset(blob, 0))
        with self.assertRaises(ValueError):
            inspect_macho(bytes(blob))

    def test_rejects_slice_outside_file(self):
        blob = bytearray(macho_fixture())
        struct.pack_into('>I', blob, 8 + 20 + 8, len(blob) + 4096)
        with self.assertRaises(ValueError):
            inspect_macho(bytes(blob))

    def test_rejects_slice_overlapping_fat_header(self):
        blob = bytearray(macho_fixture())
        struct.pack_into('>I', blob, 8 + 8, 32)
        with self.assertRaises(ValueError):
            inspect_macho(bytes(blob))

    def test_rejects_simulator_platform(self):
        with self.assertRaises(ValueError):
            inspect_macho(macho_fixture(platform=7))

    def test_rejects_deployment_target_above_ios_16_1_1(self):
        with self.assertRaises(ValueError):
            inspect_macho(macho_fixture(minos=0x110000))

    def test_accepts_exact_target_ios_16_1_1(self):
        self.assertEqual(len(inspect_macho(macho_fixture(minos=0x100101))), 2)

    def test_rejects_missing_signature(self):
        with self.assertRaises(ValueError):
            inspect_macho(macho_fixture(signature=False))

    def test_rejects_wrong_filetype(self):
        with self.assertRaises(ValueError):
            inspect_macho(macho_fixture(filetype=2), expected_type=6)

    def test_rejects_rootful_and_developer_dependencies(self):
        for dependency in ['/usr/lib/libsubstrate.dylib',
                           '/Users/builder/Library/libprivate.dylib',
                           '/Applications/Xcode.app/Contents/Developer/libfoo.dylib']:
            with self.subTest(dependency=dependency), self.assertRaises(ValueError):
                inspect_macho(macho_fixture(dependency=dependency))

    def test_rejects_developer_rpath(self):
        first = _thin_fixture(0, 6, 2, 0x0F0000, '/usr/lib/libSystem.B.dylib', True,
                              rpath='/Users/builder/lib')
        second = _thin_fixture(ARM64E_CURRENT, 6, 2, 0x0F0000,
                               '/usr/lib/libSystem.B.dylib', True, rpath='/Users/builder/lib')
        with self.assertRaises(ValueError):
            inspect_macho(_fat_fixture(first, second, ARM64E_CURRENT))

    def test_rejects_load_command_bounds_violation(self):
        blob = bytearray(macho_fixture())
        struct.pack_into('<I', blob, _slice_offset(blob) + 32 + 4, 0xFFFFFFF8)
        with self.assertRaises(ValueError):
            inspect_macho(bytes(blob))

    def test_rejects_signature_outside_slice(self):
        blob = bytearray(macho_fixture())
        command = _command_offset(blob, LC_CODE_SIGNATURE)
        struct.pack_into('<I', blob, command + 8, 0xFFFFFFF0)
        with self.assertRaises(ValueError):
            inspect_macho(bytes(blob))

    def test_rejects_invalid_superblob_magic(self):
        blob = bytearray(macho_fixture())
        command = _command_offset(blob, LC_CODE_SIGNATURE)
        data_offset = struct.unpack_from('<I', blob, command + 8)[0]
        struct.pack_into('>I', blob, _slice_offset(blob) + data_offset, 0xDEADBEEF)
        with self.assertRaises(ValueError):
            inspect_macho(bytes(blob))

    def test_rejects_superblob_child_out_of_bounds(self):
        blob = bytearray(macho_fixture())
        command = _command_offset(blob, LC_CODE_SIGNATURE)
        data_offset = struct.unpack_from('<I', blob, command + 8)[0]
        struct.pack_into('>I', blob, _slice_offset(blob) + data_offset + 16, 0xFFFF)
        with self.assertRaises(ValueError):
            inspect_macho(bytes(blob))

    def test_rejects_code_directory_shorter_than_fixed_header(self):
        blob = bytearray(macho_fixture())
        command = _command_offset(blob, LC_CODE_SIGNATURE)
        data_offset = struct.unpack_from('<I', blob, command + 8)[0]
        struct.pack_into('>I', blob, _slice_offset(blob) + data_offset + 20 + 4, 43)
        with self.assertRaises(ValueError):
            inspect_macho(bytes(blob))

    def test_rejects_code_directory_outside_signature(self):
        blob = bytearray(macho_fixture())
        command = _command_offset(blob, LC_CODE_SIGNATURE)
        data_offset = struct.unpack_from('<I', blob, command + 8)[0]
        struct.pack_into('>I', blob, _slice_offset(blob) + data_offset + 20 + 4, 0xFFFF)
        with self.assertRaises(ValueError):
            inspect_macho(bytes(blob))


if __name__ == '__main__':
    unittest.main()
