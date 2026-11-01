"""P 盘路径：PikPak 分享里的原档。

免费号空间只有 6GB，所以是「分批转存 → 立刻下载 → 立刻删云端」。
两个上限要注意：
  file_list(size=) 最大 100，分页要自己翻
  单批别超过 90 个文件，否则落盘不全
"""
import asyncio
import json
import pathlib
import time

import aiohttp
from pikpakapi import PikPakApi

BATCH_BYTES = 3.4 * 1024 ** 3
BATCH_FILES = 90
RETRY = 3


def load_links(out: pathlib.Path) -> dict:
    f = out / "links.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def save_link(out: pathlib.Path, period: int, url: str):
    data = load_links(out)
    data[str(period)] = url
    (out / "links.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def human(n: float) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def load_progress(out: pathlib.Path) -> dict:
    f = out / "dl_progress.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"done": {}, "bytes": 0}


def save_progress(out: pathlib.Path, prog: dict):
    (out / "dl_progress.json").write_text(
        json.dumps(prog, ensure_ascii=False, indent=1), encoding="utf-8")


async def list_share(cli: PikPakApi, sid: str, token: str, parent: str):
    """分享目录完整翻页。库自带的 file_list 写死了 limit=100。"""
    files, page = [], None
    while True:
        params = {"limit": "100", "thumbnail_size": "SIZE_LARGE", "order": "6",
                  "share_id": sid, "parent_id": parent, "pass_code_token": token}
        if page:
            params["page_token"] = page
        r = await cli._request_get(f"https://{cli.PIKPAK_API_HOST}/drive/v1/share/detail",
                                   params=params)
        batch = r.get("files") or []
        files.extend(batch)
        page = r.get("next_page_token")
        if not page or not batch:
            break
        await asyncio.sleep(0.8)
    return files


async def _pack_folder(cli: PikPakApi):
    lst = await cli.file_list(size=100)
    for f in (lst.get("files") or []):
        if f.get("kind") == "drive#folder" and "Pack From Shared" in (f.get("name") or ""):
            return f["id"]
    return None


async def _download_one(cli, session, f, dest: pathlib.Path, prog, key):
    target = dest / f["name"]
    if key in prog["done"] or (target.exists() and target.stat().st_size > 0):
        prog["done"].setdefault(key, f.get("id"))
        return 0
    for attempt in range(RETRY):
        try:
            info = await cli.get_download_url(f["id"])
            link = info.get("web_content_link") or info.get("url")
            if not link:
                raise RuntimeError("没有下载直链")
            tmp = target.with_name(target.name + ".part")
            got = 0
            async with session.get(link, timeout=aiohttp.ClientTimeout(total=None)) as r:
                r.raise_for_status()
                with open(tmp, "wb") as fp:
                    async for chunk in r.content.iter_chunked(1 << 20):
                        fp.write(chunk)
                        got += len(chunk)
            tmp.rename(target)
            prog["done"][key] = f.get("id")
            prog["bytes"] = prog.get("bytes", 0) + got
            return got
        except Exception as exc:
            print(f"    ! {f['name'][:40]} 第{attempt + 1}次失败: {str(exc)[:70]}")
            await asyncio.sleep(4 + attempt * 4)
    return 0


async def _run(cfg, staging: pathlib.Path, out: pathlib.Path, period: int, link: str):
    pk = cfg["pikpak"]
    if not pk.get("username"):
        raise SystemExit("config.json 里没填 pikpak 账号")
    cli = PikPakApi(username=pk["username"], password=pk["password"])
    await cli.login()

    sid = link.rstrip("/").split("/s/")[-1].split("/")[0]
    info = await cli.get_share_info(link)
    token = info["pass_code_token"]
    root = info["files"][0]
    files = await list_share(cli, sid, token, root["id"])
    files = [f for f in files if f.get("kind") != "drive#folder"]
    total = sum(int(f.get("size") or 0) for f in files)
    print(f"第 {period} 期  {root.get('name')}")
    print(f"  {len(files)} 个文件 / {human(total)}")

    dest = staging / f"p{period:02d}"
    dest.mkdir(parents=True, exist_ok=True)
    prog = load_progress(out)
    already = sum(1 for k in prog["done"] if k.startswith(f"{period}/"))
    if already:
        print(f"  已经下过 {already} 个，接着来")

    batches, cur, acc = [], [], 0
    for f in files:
        size = int(f.get("size") or 0)
        if cur and (acc + size > BATCH_BYTES or len(cur) >= BATCH_FILES):
            batches.append(cur)
            cur, acc = [], 0
        cur.append(f)
        acc += size
    if cur:
        batches.append(cur)

    started = time.time()
    for i, batch in enumerate(batches, 1):
        need = [f for f in batch if f"{period}/{f['name']}" not in prog["done"]]
        if not need:
            print(f"  [批 {i}/{len(batches)}] 都下过了，跳过")
            continue
        print(f"  [批 {i}/{len(batches)}] {len(need)} 个，转存中…")
        await cli.restore(sid, token, [f["id"] for f in need])
        await asyncio.sleep(8)
        pack = await _pack_folder(cli)
        if not pack:
            print("    找不到转存目录，跳过这批")
            continue
        lst = await cli.file_list(parent_id=pack, size=100)
        landed = {f["name"]: f for f in (lst.get("files") or [])}
        async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as sess:
            for f in need:
                src = landed.get(f["name"])
                if not src:
                    print(f"    ? {f['name'][:40]} 还没落盘，留给下一轮")
                    continue
                got = await _download_one(
                    cli, sess, src, dest, prog, f"{period}/{f['name']}")
                if got:
                    el = time.time() - started
                    print(f"    + {f['name'][:40]:<42} {human(got):>8}  "
                          f"累计 {human(prog.get('bytes', 0))}  "
                          f"{prog.get('bytes', 0) / el / 1048576 if el else 0:.1f}MB/s")
                    save_progress(out, prog)
                try:
                    await cli.delete_forever([src["id"]])
                except Exception:
                    pass
    save_progress(out, prog)
    print(f"  完成，文件在 {dest}")


def get(cfg, staging: pathlib.Path, out: pathlib.Path, period: int, link: str | None = None):
    link = link or load_links(out).get(str(period))
    if not link:
        raise SystemExit(f"第 {period} 期没有 P 盘链接，先 tgpak pikpak link --period {period} --url ...")
    asyncio.run(_run(cfg, staging, out, period, link))
