"""传网盘：走 OpenList 的 HTTP API，rclone crypt 由它自己处理。

原则是「传完一个验一个」，整期都对上了才删本地。中途断了重跑会跳过
远端已存在且尺寸一致的文件，所以可以随时中断。
"""
import pathlib
import time
import urllib.parse

import requests

CHUNK_TIMEOUT = 600
RETRY = 3


class OpenList:
    def __init__(self, url: str, username: str, password: str):
        self.url = url.rstrip("/")
        self.session = requests.Session()
        self.token = ""
        self._login(username, password)

    def _login(self, username, password):
        r = self.session.post(f"{self.url}/api/auth/login",
                              json={"username": username, "password": password}, timeout=30)
        data = r.json()
        if data.get("code") != 200:
            raise SystemExit(f"OpenList 登录失败：{data.get('message')}")
        self.token = data["data"]["token"]
        self.session.headers.update({"Authorization": self.token})

    def _post(self, path, payload, timeout=60):
        r = self.session.post(f"{self.url}{path}", json=payload, timeout=timeout)
        data = r.json()
        if data.get("code") == 401:
            self._login(*self._cred)
        return data

    def ls(self, path):
        r = self.session.post(f"{self.url}/api/fs/list",
                              json={"path": path, "password": "", "page": 1,
                                    "per_page": 1000, "refresh": True}, timeout=60)
        data = r.json()
        if data.get("code") == 401:
            self._login(*self._cred)
            return self.ls(path)
        if data.get("code") != 200:
            return []
        return (data.get("data") or {}).get("content") or []

    def mkdir(self, path):
        return self._post("/api/fs/mkdir", {"path": path}).get("code") == 200

    def size(self, path) -> int:
        data = self._post("/api/fs/get", {"path": path})
        if data.get("code") == 200:
            return int((data.get("data") or {}).get("size") or 0)
        return -1

    def put(self, local: pathlib.Path, remote: str):
        headers = {"File-Path": urllib.parse.quote(remote),
                   "Content-Type": "application/octet-stream"}
        with open(local, "rb") as fp:
            r = self.session.put(f"{self.url}/api/fs/put", headers=headers, data=fp,
                                 timeout=CHUNK_TIMEOUT)
        try:
            return r.json()
        except Exception:
            return {"code": r.status_code, "message": r.text[:120]}


def _human(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def _rm_quiet(path: pathlib.Path) -> bool:
    try:
        path.unlink()
        return True
    except Exception:
        return False


def push(cfg, staging: pathlib.Path, period: int, remote_base: str | None = None,
         keep=False, force=False):
    up = cfg["upload"]
    src = staging / f"p{period:02d}"
    if not src.exists():
        raise SystemExit(f"本地没有 {src}")
    files = sorted(f for f in src.iterdir() if f.is_file() and not f.name.endswith(".part"))
    if not files:
        raise SystemExit("目录是空的")

    total = sum(f.stat().st_size for f in files)
    remote_dir = f"{remote_base or up['base'].rstrip('/')}/p{period:02d}"
    print(f"第 {period} 期：{len(files)} 个 / {_human(total)}")
    print(f"  → {remote_dir}")

    ol = OpenList(up["url"], up["username"], up["password"])
    ol._cred = (up["username"], up["password"])
    remote = {x.get("name"): int(x.get("size") or 0) for x in ol.ls(remote_dir)}
    ol.mkdir(remote_dir)

    failed, done_bytes = [], 0
    started = time.time()
    for i, f in enumerate(files, 1):
        size = f.stat().st_size
        if not force and remote.get(f.name) == size:
            print(f"  [{i}/{len(files)}] = 已在云端 {f.name[:36]}")
            done_bytes += size
            continue
        ok = False
        for attempt in range(RETRY):
            try:
                res = ol.put(f, f"{remote_dir}/{f.name}")
                if res.get("code") != 200:
                    raise RuntimeError(f"API {res.get('code')} {str(res.get('message'))[:60]}")
                if ol.size(f"{remote_dir}/{f.name}") != size:
                    raise RuntimeError("尺寸对不上")
                ok = True
                done_bytes += size
                el = time.time() - started
                print(f"  [{i}/{len(files)}] + {f.name[:36]:<38} {_human(size):>8}  "
                      f"{done_bytes / el / 1048576 if el else 0:.1f}MB/s")
                break
            except Exception as exc:
                print(f"  [{i}/{len(files)}] ! 第{attempt + 1}次 {f.name[:24]}: {str(exc)[:60]}")
                time.sleep(3 + attempt * 5)
        if not ok:
            failed.append(f.name)

    print(f"  成功 {len(files) - len(failed)} / {len(files)}  "
          f"用时 {(time.time() - started) / 60:.1f} 分钟")
    if failed:
        print("  这些没传成功，本地留着：")
        for name in failed:
            print("   ", name)
        return failed

    if keep:
        print("  --keep，本地保留")
        return []

    # 小批量删，一次删几百个容易卡住
    removed = 0
    for i in range(0, len(files), 10):
        for f in files[i:i + 10]:
            if _rm_quiet(f):
                removed += 1
    print(f"  本地已删 {removed} 个")
    return []
