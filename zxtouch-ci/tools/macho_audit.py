"""Structural iOS Mach-O checks. This does not verify runtime behavior or trust."""
import struct

ARM64 = 0x0100000C
ARM64E = 0x80000002
MAX_IOS = (16 << 16) | (1 << 8) | 1
SUBSTRATE = '@rpath/CydiaSubstrate.framework/CydiaSubstrate'
SYSTEM_LIBS = {'libobjc.A.dylib', 'libSystem.B.dylib', 'libc++.1.dylib',
               'libc++abi.dylib', 'libz.1.dylib', 'libiconv.2.dylib',
               'libsqlite3.dylib', 'libcompression.dylib', 'libxml2.2.dylib',
               'libresolv.9.dylib', 'libnetwork.dylib', 'libbz2.1.0.dylib'}
RPATHS = {'/var/jb/Library/Frameworks', '/var/jb/usr/lib',
          '@loader_path/.jbroot/Library/Frameworks', '@loader_path/.jbroot/usr/lib',
          '@executable_path/Frameworks', '@executable_path/../../Frameworks', '@loader_path/Frameworks'}


def _string(command, offset):
    if offset < 8 or offset >= len(command):
        raise ValueError('invalid load command string offset')
    end = command.find(b'\0', offset)
    if end < 0:
        raise ValueError('unterminated load command string')
    return command[offset:end].decode('utf-8')


def _signature(blob, offset, size):
    if size < 12 or offset < 32 or offset + size > len(blob):
        raise ValueError('invalid code signature bounds')
    data = blob[offset:offset+size]
    magic, length, count = struct.unpack_from('>III', data)
    if magic != 0xFADE0CC0 or length > size or length < 12+count*8:
        raise ValueError('invalid code signature superblob')
    directory = False
    for i in range(count):
        kind, child_offset = struct.unpack_from('>II', data, 12+i*8)
        if child_offset < 12+count*8 or child_offset+8 > length:
            raise ValueError('invalid code signature slot bounds')
        child_magic, child_size = struct.unpack_from('>II', data, child_offset)
        if child_size < 8 or child_offset+child_size > length:
            raise ValueError('invalid code signature child size')
        if kind == 0 or 0x1000 <= kind <= 0x1005:
            if child_magic != 0xFADE0C02 or child_size < 44:
                raise ValueError('invalid CodeDirectory')
            directory = True
    if not directory:
        raise ValueError('missing CodeDirectory')


def _slice(blob, expected_type):
    if len(blob) < 32 or blob[:4] != b'\xcf\xfa\xed\xfe':
        raise ValueError('expected little endian 64-bit Mach-O')
    _, cpu, subtype, filetype, ncmds, sizeofcmds, _, _ = struct.unpack_from('<8I', blob)
    if cpu != ARM64 or subtype not in (0, ARM64E):
        raise ValueError('unexpected Mach-O architectures / old arm64e ABI')
    if filetype != expected_type:
        raise ValueError('wrong Mach-O filetype')
    if not ncmds or ncmds > 4096 or 32+sizeofcmds > len(blob):
        raise ValueError('invalid load command table')
    pos = 32
    platform = minos = None
    dependencies, rpaths = [], []
    signature = None
    for _ in range(ncmds):
        if pos+8 > 32+sizeofcmds:
            raise ValueError('truncated load command')
        cmd, size = struct.unpack_from('<II', blob, pos)
        if size < 8 or size % 8 or pos+size > 32+sizeofcmds:
            raise ValueError('invalid load command size')
        command = blob[pos:pos+size]
        if cmd == 0x32:
            if size < 24:
                raise ValueError('short LC_BUILD_VERSION')
            platform, minos, sdk, ntools = struct.unpack_from('<4I', command, 8)
            if size < 24+ntools*8:
                raise ValueError('invalid build version tool table')
        elif cmd == 0x25:
            if size < 16:
                raise ValueError('short LC_VERSION_MIN_IPHONEOS')
            platform, minos = 2, struct.unpack_from('<I', command, 8)[0]
        elif cmd in (0xC, 0x80000018, 0x8000001F, 0x80000023, 0x20):
            if size < 24:
                raise ValueError('short dylib command')
            dependencies.append(_string(command, struct.unpack_from('<I', command, 8)[0]))
        elif cmd == 0x8000001C:
            if size < 16:
                raise ValueError('short rpath command')
            rpaths.append(_string(command, struct.unpack_from('<I', command, 8)[0]))
        elif cmd == 0x1D:
            if size != 16 or signature is not None:
                raise ValueError('invalid code signature command')
            signature = struct.unpack_from('<II', command, 8)
        pos += size
    if pos != 32+sizeofcmds:
        raise ValueError('load command size mismatch')
    if platform != 2 or minos is None or minos > MAX_IOS:
        raise ValueError('not an iOS device binary compatible with iOS 16.1.1')
    if signature is None or signature[0] < pos:
        raise ValueError('missing code signature or signature overlaps load commands')
    _signature(blob, *signature)
    for name in dependencies:
        system = name.startswith(('/System/Library/Frameworks/', '/System/Library/PrivateFrameworks/'))
        system = system or (name.startswith('/usr/lib/') and name[9:] in SYSTEM_LIBS)
        if not system and name != SUBSTRATE:
            raise ValueError('unsupported dependency: ' + name)
    if any(path not in RPATHS for path in rpaths):
        raise ValueError('unexpected rpath: ' + repr(rpaths))
    if SUBSTRATE in dependencies and '/var/jb/Library/Frameworks' not in rpaths:
        raise ValueError('substrate lacks rootless framework rpath')
    return {'cpu':cpu,'subtype':subtype,'filetype':filetype,'platform':platform,
            'minimumIOS':minos,'dependencies':dependencies,'rpaths':rpaths,
            'signature':'CodeDirectory present (structural check only)'}


def inspect_macho(blob, expected_type=6, require_arm64e=True):
    if blob[:4] == b'\xcf\xfa\xed\xfe':
        slices = [_slice(blob, expected_type)]
    elif blob[:4] == b'\xca\xfe\xba\xbe':
        if len(blob) < 8:
            raise ValueError('truncated fat header')
        count = struct.unpack_from('>I', blob, 4)[0]
        if not 1 <= count <= 2 or len(blob) < 8+20*count:
            raise ValueError('invalid fat architecture table')
        slices, ranges = [], []
        for i in range(count):
            cpu, subtype, offset, size, align = struct.unpack_from('>5I', blob, 8+i*20)
            if align > 30 or offset % (1 << align) or size < 32 or offset < 8+20*count or offset+size > len(blob):
                raise ValueError('invalid fat slice bounds/alignment')
            if any(offset < end and offset+size > start for start, end in ranges):
                raise ValueError('overlapping fat slices')
            ranges.append((offset, offset+size))
            info = _slice(blob[offset:offset+size], expected_type)
            if (cpu, subtype) != (info['cpu'], info['subtype']):
                raise ValueError('outer and inner Mach-O architectures differ')
            slices.append(info)
    else:
        raise ValueError('expected Mach-O, not a placeholder/header fixture')
    subtypes = [s['subtype'] for s in slices]
    if 0 not in subtypes or len(set(subtypes)) != len(subtypes) or (require_arm64e and ARM64E not in subtypes):
        raise ValueError('unexpected Mach-O architectures: arm64 and modern arm64e required')
    return slices
