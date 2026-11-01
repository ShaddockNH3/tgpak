"""命令行入口。三条路径：tg（取图）/ pikpak（P 盘）/ push（传网盘）。"""
import argparse
import pathlib
import sys

from . import config, grab, pikpak, push, verify
from .kapi import WebK, login as do_login


def _periods(args):
    if getattr(args, "periods", None):
        lo, _, hi = args.periods.partition("-")
        return list(range(int(lo), int(hi or lo) + 1))
    if getattr(args, "period", None):
        return [args.period]
    raise SystemExit("给 --period N 或 --periods A-B")


def _profile(cfg) -> pathlib.Path:
    p = pathlib.Path(cfg["telegram"]["profile"]).expanduser()
    if not p.is_absolute():
        p = pathlib.Path(cfg["_path"]).parent / p
    return p


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tgpak", description="Telegram 图包归档")
    ap.add_argument("-c", "--config", default=None, help="配置文件，默认 ./config.json")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("login", help="登录 Telegram Web K 并保存登录态")

    tg = sub.add_parser("tg", help="取图路径")
    tg_sub = tg.add_subparsers(dest="sub", required=True)
    tg_sub.add_parser("scan", help="在频道里搜 tag，登记每一期的帖子 id")
    addp = tg_sub.add_parser("add", help="手动登记一期的帖子 id（合集之类）")
    addp.add_argument("--period", type=int, required=True)
    addp.add_argument("--post", type=int, required=True)
    for name in ("fetch", "get"):
        p = tg_sub.add_parser(name, help="拉清单" if name == "fetch" else "下载")
        p.add_argument("--period", type=int)
        p.add_argument("--periods")
        p.add_argument("--force", action="store_true")

    pk = sub.add_parser("pikpak", help="P 盘路径")
    pk_sub = pk.add_subparsers(dest="sub", required=True)
    link = pk_sub.add_parser("link", help="登记某期的 P 盘分享链接")
    link.add_argument("--period", type=int, required=True)
    link.add_argument("--url", required=True)
    pk_get = pk_sub.add_parser("get", help="转存并下载")
    pk_get.add_argument("--period", type=int)
    pk_get.add_argument("--periods")

    p = sub.add_parser("push", help="传到网盘")
    p.add_argument("--period", type=int, required=True)
    p.add_argument("--to", default=None, help="远端目录，默认用 config.upload.base")
    p.add_argument("--keep", action="store_true", help="传完不删本地")
    p.add_argument("--force", action="store_true", help="云端已有也重传")

    v = sub.add_parser("verify", help="校验齐不齐")
    v.add_argument("--period", type=int)
    v.add_argument("--periods")
    v.add_argument("--remote", action="store_true", help="看云端而不是本地")

    args = ap.parse_args(argv)
    cfg = config.load(args.config)
    out, staging = config.paths(cfg)

    if args.cmd == "login":
        do_login(_profile(cfg))
        return 0

    if args.cmd == "verify":
        verify.run(cfg, out, staging, _periods(args), remote=args.remote)
        return 0

    if args.cmd == "push":
        failed = push.push(cfg, staging, args.period, args.to,
                           keep=args.keep, force=args.force)
        return 1 if failed else 0

    if args.cmd == "pikpak":
        if args.sub == "link":
            pikpak.save_link(out, args.period, args.url)
            print(f"第 {args.period} 期链接已存进 {out / 'links.json'}")
            return 0
        for period in _periods(args):
            pikpak.get(cfg, staging, out, period)
        return 0

    if args.cmd == "tg":
        if args.sub == "add":
            grab.add_post(out, args.period, args.post)
            return 0
        with WebK(_profile(cfg), cfg["telegram"]["channel"],
                  headless=cfg["telegram"].get("headless", False)) as wc:
            if args.sub == "scan":
                grab.scan(wc, cfg, out)
                return 0
            for period in _periods(args):
                if args.sub == "fetch":
                    grab.fetch(wc, cfg, out, period)
                else:
                    grab.get(wc, cfg, staging, out, period, force=args.force)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
