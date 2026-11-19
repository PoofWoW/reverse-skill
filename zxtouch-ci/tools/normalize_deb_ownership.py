#!/usr/bin/env python3
"""Normalize tar numeric owners, preserving Mach-O bytes and all file modes.

Theos dm.pl/NIC may set uname/gname=root/wheel without changing numeric IDs.
This is an archive metadata operation, never a binary ABI relabeling operation.
"""
import argparse
import io
from pathlib import Path
import tarfile
from audit_touch_deb import members


def normalize(blob):
    ar = members(blob)
    if ar.get('debian-binary') != b'2.0\n':
        raise ValueError('unsupported deb format')
    output = bytearray(b'!<arch>\n')
    for kind in ('debian-binary', 'control', 'data'):
        if kind == 'debian-binary':
            name, payload = kind, ar[kind]
        else:
            matches = [v for k, v in ar.items() if k.startswith(kind+'.tar')]
            if len(matches) != 1:
                raise ValueError('missing/duplicate Debian tar member: ' + kind)
            target = io.BytesIO()
            with tarfile.open(fileobj=io.BytesIO(matches[0]), mode='r:*') as source, \
                 tarfile.open(fileobj=target, mode='w:gz', format=tarfile.GNU_FORMAT) as destination:
                for entry in source:
                    entry.uid = entry.gid = 0
                    entry.uname, entry.gname = 'root', 'wheel'
                    entry.pax_headers = {}
                    destination.addfile(entry, source.extractfile(entry) if entry.isfile() else None)
            name, payload = kind+'.tar.gz', target.getvalue()
        header = '{:<16}{:<12}{:<6}{:<6}{:<8}{:<10}`\n'.format(name, 0, 0, 0, '100644', len(payload))
        output.extend(header.encode('ascii'))
        output.extend(payload)
        if len(payload) % 2:
            output.extend(b'\n')
    return bytes(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('deb')
    args = parser.parse_args()
    path = Path(args.deb)
    target = path.with_suffix(path.suffix+'.tmp')
    target.write_bytes(normalize(path.read_bytes()))
    target.replace(path)
