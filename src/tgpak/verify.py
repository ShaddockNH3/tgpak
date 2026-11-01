"""完整性校验。

真值从哪来：
  取图路径 → media_pNN.json（文件名集合逐个对）
  P 盘路径 → 重新读一遍分享，比文件数和总字节

远端比本地麻烦一点，但只有远端才是最终结果，所以两个都做。
"""
import asyncio
import json
import pathlib

from . import pikpak as pkm


def _tg_manifest(out: pathlib.Path, period: int):
    f = out / f"media_p{period:02d}.json"
    if not f.exists():
        return None
    items = json.loads(f.read_text(encoding="utf-8"))["items"]
    return items


def _expected_names(items):
    from .grab import target_name
    return {target_name(it) for it in items}


def _pikpak_truth(cfg, out: pathlib.Path, period: int):
    link = pkm.load_links(out).get(str(period))
    if not link:
        return None
    from pikpakapi import PikPakApi

    async def run():
        pk = cfg["pikpak"]
        cli = PikPakApi(username=pk["username"], password=pk["password"])
        await cli.login()
        sid = link.rstrip("/").split("/s/")[-1].split("/")[0]
        info = await cli.get_share_info(link)
        files = await pkm.list_share(cli, sid, info["pass_code_token"],
                                     info["files"][0]["id"])
        files = [f for f in files if f.get("kind") != "drive#folder"]
        return {"count": len(files),
                "bytes": sum(int(f.get("size") or 0) for f in files)}

    try:
        return asyncio.run(run())
    except Exception as exc:
        return {"error": str(exc)[:80]}


def check_period(cfg, out, staging, period, remote_names=None):
    """返回问题列表，空表示没问题。remote_names 不为 None 时按远端比。"""
    items = _tg_manifest(out, period)
    issues = []

    if remote_names is not None:
        files = remote_names
        if items is not None:
            want = _expected_names(items)
            missing = want - files
            extra = files - want
            if missing:
                issues.append(f"缺 {len(missing)} 个：{sorted(missing)[:3]}")
            if extra:
                issues.append(f"多 {len(extra)} 个：{sorted(extra)[:3]}")
        else:
            truth = _pikpak_truth(cfg, out, period)
            if truth and "count" in truth:
                if len(files) != truth["count"]:
                    diff = truth["count"] - len(files)
                    issues.append(f"{'缺' if diff > 0 else '多'}{abs(diff)} 个"
                                  f"（{len(files)}/{truth['count']}）")
        return issues

    # 本地比对
    local = staging / f"p{period:02d}"
    files = {f.name for f in local.iterdir() if f.is_file()} if local.exists() else set()
    if not files:
        return ["本地没有"]
    if items is not None:
        want = _expected_names(items)
        missing = want - files
        if missing:
            issues.append(f"缺 {len(missing)} 个：{sorted(missing)[:3]}")
    return issues


def run(cfg, out, staging, periods, remote=False):
    ol = None
    base = None
    if remote:
        from .push import OpenList
        up = cfg["upload"]
        ol = OpenList(up["url"], up["username"], up["password"])
        ol._cred = (up["username"], up["password"])
        base = up["base"].rstrip("/")

    print(f"{'期':<6}{'文件':>6}{'大小':>10}  结论")
    print("-" * 56)
    bad = []
    for p in periods:
        if remote:
            path = f"{base}/p{p:02d}"
            cont = [x for x in ol.ls(path) if not x.get("is_dir")]
            names = {x.get("name") for x in cont}
            size = sum(int(x.get("size") or 0) for x in cont)
        else:
            d = staging / f"p{p:02d}"
            cont = [x for x in d.iterdir() if x.is_file()] if d.exists() else []
            names = {x.name for x in cont}
            size = sum(x.stat().st_size for x in cont)

        issues = check_period(cfg, out, staging, p, names if remote else None)
        zero = [n for n in names if n.endswith(".part")]
        if zero:
            issues.append(f"残骸 {len(zero)}")
        ok = not issues
        print(f"p{p:02d} {len(names):>6}{size / 1048576:>9.1f}M  "
              f"{'ok' if ok else 'x ' + '；'.join(issues)}")
        if not ok:
            bad.append({"period": p, "issues": issues})

    print("-" * 56)
    if bad:
        print(f"不齐 {len(bad)} 期：{[x['period'] for x in bad]}")
    else:
        print("全部齐了")
    (out / "verify.json").write_text(
        json.dumps(bad, ensure_ascii=False, indent=1), encoding="utf-8")
    return bad
