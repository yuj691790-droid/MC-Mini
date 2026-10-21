"""Separate aria2 CLI transport, with verified atomic publication of files."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import secrets
import socket
import sys
import tempfile
import time
import urllib.request
import urllib.error


class ProgressReader:
    """Read byte counts and aggregate network speed from our loopback-only aria2."""
    def __init__(self, pending, cached, callback):
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            self.port = reservation.getsockname()[1]
        self.secret = secrets.token_hex(24)
        self.callback = callback
        self.cached = cached
        self.sizes = {str(temp.resolve()).replace('\\', '/'): size
                      for _, _, temp, _, size in pending}
        self.stopped = {}
        self.offset = 0
        self.shutdown_requested = False
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def options(self):
        return ['--enable-rpc=true', '--rpc-listen-all=false', '--rpc-allow-origin-all=false',
                f'--rpc-listen-port={self.port}', '--rpc-secret=' + self.secret,
                '--max-download-result=' + str(len(self.sizes))]

    def sample(self):
        keys = ['gid', 'status', 'completedLength', 'totalLength', 'files']
        calls = [('aria2.getGlobalStat', []), ('aria2.tellStopped', [self.offset, 1000, keys]),
                 ('aria2.tellActive', [keys])]
        body = [{'jsonrpc': '2.0', 'id': str(i), 'method': method,
                 'params': ['token:' + self.secret, *params]} for i, (method, params) in enumerate(calls)]
        req = urllib.request.Request(f'http://127.0.0.1:{self.port}/jsonrpc',
                                     data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
        try:
            with self.opener.open(req, timeout=0.5) as response:
                results = {row['id']: row for row in json.load(response)}
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            # aria2 has not opened its listener yet, or exited after the last poll.
            return
        for row in results.values():
            if 'error' in row:
                raise RuntimeError('读取 aria2 进度失败：' + row['error']['message'])
        stopped = results['1']['result']
        self.offset += len(stopped)
        for row in stopped:
            self.stopped[row['gid']] = row
        rows = {**{row['gid']: row for row in results['2']['result']}, **self.stopped}
        for row in rows.values():
            path = row['files'][0]['path'].replace('\\', '/')
            if self.sizes.get(path) is None and int(row['totalLength']) > 0:
                self.sizes[path] = int(row['totalLength'])
        total = self.cached + sum(self.sizes.values()) if all(v is not None for v in self.sizes.values()) else None
        completed = self.cached + sum(int(row['completedLength']) for row in rows.values())
        self.callback(completed, total, int(results['0']['result']['downloadSpeed']))
        stat = results['0']['result']
        if (not self.shutdown_requested and int(stat['numActive']) == 0 and int(stat['numWaiting']) == 0
                and int(stat['numStoppedTotal']) >= len(self.sizes)
                and self.offset >= int(stat['numStoppedTotal'])):
            shutdown = {'jsonrpc': '2.0', 'id': 'shutdown', 'method': 'aria2.shutdown',
                        'params': ['token:' + self.secret]}
            req.data = json.dumps(shutdown).encode()
            with self.opener.open(req, timeout=0.5) as response:
                json.load(response)
            self.shutdown_requested = True


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


def fetch(items, cancel, log, logdir, progress=None):
    pending = []
    cached = 0
    for url, path, sha1, size, _ in items:
        if cancel.is_set():
            raise InterruptedError('下载已取消；断点和已校验文件已保留。')
        if sha1 and valid(path, sha1, size):
            cached += path.stat().st_size
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
        if progress:
            progress(cached, cached, 0)
        return
    reader = ProgressReader(pending, cached, progress) if progress else None
    if progress:
        total = cached + sum(row[4] for row in pending) if all(row[4] is not None for row in pending) else None
        progress(cached, total, 0)
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
    if reader:
        args.remove('--enable-rpc=false')
        args.extend(reader.options())
    process = None
    try:
        with logfile.open('wb') as output:
            process = subprocess.Popen(args, stdout=output, stderr=subprocess.STDOUT,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            next_update = time.monotonic() + 10
            next_sample = time.monotonic()
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
                if reader and time.monotonic() >= next_sample:
                    reader.sample()
                    next_sample = time.monotonic() + 0.5
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
        if progress:
            total = cached + sum(row[1].stat().st_size for row in pending)
            progress(total, total, 0)
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait()
        input_path.unlink(missing_ok=True)
