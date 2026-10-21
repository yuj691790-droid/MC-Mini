"""Separate aria2 CLI transport, with verified atomic publication of files."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def executable():
    home = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
    path = home / 'aria2' / 'aria2c.exe'
    if not path.is_file():
        raise FileNotFoundError('缺少 aria2/aria2c.exe；请完整解压便携包，勿只复制 MC-Mini.exe。')
    return path


def valid(path, sha1, size):
    if not path.is_file() or (size is not None and path.stat().st_size != size):
        return False
    if sha1:
        with path.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha1').hexdigest() == sha1.lower()
    return size is not None


def fetch(items, cancel, log, logdir):
    pending = []
    for url, path, sha1, size, _ in items:
        if cancel.is_set():
            raise InterruptedError('下载已取消；断点和已校验文件已保留。')
        if sha1 and valid(path, sha1, size):
            continue
        temp = path.with_name(path.name + '.mcmini-part')
        # Input-file options are line based: reject remote metadata injection.
        if any(c in str(value) for value in (url, temp.parent, temp.name) for c in '\r\n\t'):
            raise ValueError('下载地址或路径包含非法控制字符')
        if sha1 and (len(sha1) != 40 or any(c not in '0123456789abcdefABCDEF' for c in sha1)):
            raise ValueError('非法 SHA-1')
        path.parent.mkdir(parents=True, exist_ok=True)
        pending.append((url, path, temp, sha1, size))
    if not pending:
        return
    program = executable()
    logdir = Path(logdir)
    logdir.mkdir(parents=True, exist_ok=True)
    logfile = logdir / 'aria2-download.log'
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.aria2-input', delete=False) as stream:
        input_path = Path(stream.name)
        for url, path, temp, sha1, size in pending:
            stream.write(f'{url}\n  dir={temp.parent}\n  out={temp.name}\n')
            if sha1:
                stream.write(f'  checksum=sha-1={sha1.lower()}\n')
    args = [str(program), '--no-conf=true', '--no-netrc=true', '--enable-rpc=false',
            '--check-certificate=true', '--check-integrity=true', '--continue=true',
            '--auto-save-interval=1', '--allow-overwrite=true', '--auto-file-renaming=false', '--file-allocation=none',
            '--max-concurrent-downloads=8', '--split=2', '--max-connection-per-server=2',
            '--max-tries=5', '--retry-wait=2', '--connect-timeout=15', '--timeout=30',
            '--max-file-not-found=1', '--enable-color=false', '--console-log-level=warn',
            '--download-result=hide', '--summary-interval=5', '--follow-metalink=false',
            '--follow-torrent=false', '--input-file=' + str(input_path)]
    log(f'aria2：下载 {len(pending)} 个文件，支持断点续传…')
    try:
        with logfile.open('wb') as output:
            process = subprocess.Popen(args, stdout=output, stderr=subprocess.STDOUT,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            next_update = time.monotonic() + 10
            while process.poll() is None:
                if cancel.wait(0.2):
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    raise InterruptedError('下载已取消；断点和已校验文件已保留。')
                if time.monotonic() >= next_update:
                    log(f'aria2 正在下载 {len(pending)} 个文件；可随时取消，断点会保留。')
                    next_update = time.monotonic() + 10
        completed = 0
        for url, path, temp, sha1, size in pending:
            if temp.is_file() and not temp.with_name(temp.name + '.aria2').exists():
                if valid(temp, sha1, size) or (not sha1 and size is None and process.returncode == 0):
                    os.replace(temp, path)
                    completed += 1
        if process.returncode or completed != len(pending):
            with logfile.open('rb') as stream:
                stream.seek(max(0, logfile.stat().st_size - 1600))
                tail = stream.read().decode('utf-8', errors='replace')
            raise OSError(f'aria2 未完成全部下载（退出码 {process.returncode}，已完成 {completed}/{len(pending)}）。'
                          f'\n断点已保留，可重新安装或手动换源。\n{tail}\n日志：{logfile}')
        log(f'aria2：{completed} 个文件已下载并校验。')
    finally:
        input_path.unlink(missing_ok=True)
