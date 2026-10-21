"""Fetch pinned upstream aria2 and corresponding source/licenses for distribution."""
import hashlib
import io
from pathlib import Path
import urllib.request
import zipfile

BASE = 'https://github.com/aria2/aria2/releases/download/release-1.37.0/'
ARCHIVE = 'aria2-1.37.0-win-64bit-build1.zip'
ZIP_SHA256 = '67d015301eef0b612191212d564c5bb0a14b5b9c4796b76454276a4d28d9b288'
EXE_SHA256 = 'be2099c214f63a3cb4954b09a0becd6e2e34660b886d4c898d260febfe9d70c2'
SOURCE = 'aria2-1.37.0.tar.bz2'
SOURCE_SHA256 = 'a75c8534902ff1a64a23d7a47c033032329002553634251a89d53a9cb8b20efa'


def obtain(name, expected):
    with urllib.request.urlopen(BASE + name, timeout=60) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('aria2 upstream file SHA-256 mismatch: ' + name)
    return data


def main():
    folder = Path(__file__).parent / 'aria2'
    folder.mkdir(exist_ok=True)
    exe = folder / 'aria2c.exe'
    if not exe.exists() or hashlib.sha256(exe.read_bytes()).hexdigest() != EXE_SHA256 or not (folder / 'README.mingw').exists():
        with zipfile.ZipFile(io.BytesIO(obtain(ARCHIVE, ZIP_SHA256))) as archive:
            for name in archive.namelist():
                leaf = name.rsplit('/', 1)[-1]
                if leaf in ('aria2c.exe', 'COPYING', 'LICENSE.OpenSSL', 'README.mingw', 'AUTHORS'):
                    (folder / leaf).write_bytes(archive.read(name))
    source = folder / SOURCE
    if not source.exists() or hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA256:
        source.write_bytes(obtain(SOURCE, SOURCE_SHA256))
    (folder / 'NOTICE.txt').write_text(
        'aria2 1.37.0, upstream unmodified standalone executable.\n'
        'Copyright Tatsuhiro Tsujikawa and contributors. GPL-2.0-or-later; see COPYING.\n'
        'Independent third-party program; MC Mini CC terms do not apply to aria2.\n'
        'Upstream source is included as aria2-1.37.0.tar.bz2.\n'
        'Windows build information: README.mingw. Additional notices: LICENSE.OpenSSL.\n'
        'Project: https://github.com/aria2/aria2\n'
        'Binary: ' + BASE + ARCHIVE + '\nSource: ' + BASE + SOURCE + '\n', encoding='utf-8')
    print('aria2 1.37.0 and source/licenses verified.')


if __name__ == '__main__':
    main()
