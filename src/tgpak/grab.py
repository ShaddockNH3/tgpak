"""取图路径：扫帖子 → 拉某期清单 → 下载。"""
import json
import pathlib
import re
import time

def _cn(n: int) -> str:
    digits = "零一二三四五六七八九"
    if n < 10:
        return digits[n]
    if n < 20:
        return "十" + (digits[n % 10] if n % 10 else "")
    if n < 100:
        tens, rest = divmod(n, 10)
        return digits[tens] + "十" + (digits[rest] if rest else "")
    return str(n)


CN = {n: _cn(n) for n in range(1, 100)}
ARCHIVE_EXT = {".zip", ".rar", ".7z", ".tar", ".gz"}
MEDIA_EXT = {".mp4", ".mov", ".mkv", ".png", ".jpg", ".jpeg", ".pdf"}


def period_of(text: str) -> int | None:
    """从标题里认「第N期」。中文数字和阿拉伯数字都认。"""
    for num, cn in CN.items():
        if f"第{cn}期" in text:
            return num
    m = re.search(r"第(\d+)期", text)
    return int(m.group(1)) if m else None


def load_periods(out: pathlib.Path) -> dict:
    f = out / "periods.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def save_periods(out: pathlib.Path, data: dict):
    (out / "periods.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def add_post(out: pathlib.Path, period: int, post: int):
    """认不出期数的帖子（比如合集）手动登记。"""
    data = load_periods(out)
    data[str(period)] = post
    save_periods(out, data)
    print(f"第 {period} 期 → 帖子 {post}")


def scan(wc, cfg, out: pathlib.Path) -> dict:
    tag = cfg["telegram"]["tag"]
    posts = wc.search(tag)
    found, unknown = {}, []
    for p in posts:
        num = period_of(p["text"])
        if num is None:
            unknown.append({"id": p["id"], "text": p["text"][:80]})
            continue
        found.setdefault(str(num), p["id"])
    data = load_periods(out)
    data.update(found)
    save_periods(out, data)
    print(f"搜到 {len(posts)} 条帖子，认出 {len(found)} 期")
    if unknown:
        print(f"另有 {len(unknown)} 条认不出期数（可能是合集或别的作者）：")
        for u in unknown[:10]:
            print(f"  {u['id']:>8}  {u['text'][:60]}")
    return data


def fetch(wc, cfg, out: pathlib.Path, period: int) -> dict:
    posts = load_periods(out)
    post = posts.get(str(period))
    if not post:
        raise SystemExit(f"第 {period} 期还没登记，先跑 tgpak tg scan")
    items = wc.load(post)
    ph = sum(1 for x in items if x["kind"] == "photo")
    doc = len(items) - ph
    manifest = {"period": period, "post": post, "items": items}
    f = out / f"media_p{period:02d}.json"
    f.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"第 {period} 期（帖子 {post}）：{len(items)} 个 = {ph} 图 + {doc} 视频/文件")
    print(f"  清单 → {f}")
    return manifest


def target_name(item: dict) -> str:
    """归档命名：图片视频用 001.jpg / 002.mp4，压缩包保留原名挂个序号。"""
    idx, ext = item["idx"], item["ext"]
    fname = item.get("fname")
    if fname:
        safe = re.sub(r'[\\/:*?"<>|]', "_", fname).strip()
        suffix = pathlib.Path(safe).suffix.lower()
        if suffix in ARCHIVE_EXT:
            return f"{idx:02d}-{safe}" if len(safe) < 70 else f"{idx:02d}{suffix}"
    return f"{idx:03d}.{ext}"


def get(wc, cfg, staging: pathlib.Path, out: pathlib.Path, period: int, force=False):
    mf = out / f"media_p{period:02d}.json"
    if not mf.exists():
        fetch(wc, cfg, out, period)
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    items = manifest["items"]
    # 清单在磁盘上，但文件对象只活在页面里，每次下载都得重新灌一遍
    wc.load(manifest["post"])
    dest = staging / f"p{period:02d}"
    dest.mkdir(parents=True, exist_ok=True)

    ok = skip = fail = 0
    total = 0
    started = time.time()
    for it in items:
        name = target_name(it)
        target = dest / name
        if not force and target.exists() and target.stat().st_size > 1024:
            ok += 1
            skip += 1
            continue
        size = wc.download(it["msg"], name, dest)
        if size is None:
            time.sleep(0.8)
            size = wc.download(it["msg"], name, dest)
        if size is None:
            print(f"  x {name}  {wc.last_error[:90]}")
            fail += 1
            continue
        ok += 1
        total += size
        if it["idx"] % 20 == 0:
            print(f"  {it['idx']:>3}/{len(items)}  {total / 1048576:.1f}MB")
    used = time.time() - started
    print(f"第 {period} 期：成功 {ok}（其中已存在 {skip}）/ 失败 {fail}  "
          f"{total / 1048576:.1f}MB  {used / 60:.1f} 分钟 → {dest}")
    return ok, fail
