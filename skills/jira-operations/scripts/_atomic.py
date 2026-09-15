# -*- coding: utf-8 -*-
"""原子写 / 文件锁 / jsonl 追加（纯标准库）。

用途：
- plan / watch state 落盘：同目录临时文件 + os.replace，中断不留半截 JSON。
- audit.log 追加：fcntl 排他锁保证并发追加不交错。
"""

try:
    import fcntl
except ImportError:
    fcntl = None
import os


def atomic_write(path, text):
    """把 text 原子写入 path（同目录临时文件 + os.replace）。"""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = "%s.tmp.%d" % (path, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def jsonl_append(path, line):
    """以排他锁向 path 追加一行 JSON（单行，末尾补换行）。Windows 无 fcntl 时降级为普通追加。"""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        if fcntl is not None:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(line.rstrip("\r\n") + "\n")
            f.flush()
            os.fsync(f.fileno())
        finally:
            if fcntl is not None:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
