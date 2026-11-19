#!/usr/bin/env python3
"""Label the staged package; leave the upstream release control unchanged."""
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
if '~touchtest.' not in text:
    raise SystemExit('Diagnostic package requires PACKAGE_VERSION=1.0.1~touchtest.<build>')
text = '\n'.join('Name: ZXTouch Touch Test (SpringBoard only)' if line.startswith('Name:') else
                 'Description: Experimental iOS 16.1.1 touch lifecycle diagnostics; NOT DEVICE VALIDATED' if line.startswith('Description:') else
                 line for line in text.splitlines()) + '\n'
path.write_text(text)

# Normalize checkout-dependent umask (e.g. cloud workspaces with umask 077).
# Assets must be readable by mobile, and DEBIAN must satisfy dpkg permissions.
stage = path.parent.parent
# Theos moves the rootless prefix from a sibling staging tree AFTER this hook.
for root in (stage, Path(str(stage) + 'tmp')):
    if not root.exists():
        continue
    root.chmod(0o755)
    for item in root.rglob('*'):
        if item.is_symlink():
            continue
        if item.is_dir():
            item.chmod(0o755)
        elif item.is_file():
            item.chmod(0o755 if item.stat().st_mode & 0o111 else 0o644)

# ZIP/web imports may lose Git executable bits; maintainer scripts still must run.
for name in ('preinst', 'postinst', 'prerm', 'postrm'):
    script = stage / 'DEBIAN' / name
    if script.is_file():
        script.chmod(0o755)
