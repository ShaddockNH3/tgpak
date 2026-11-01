"""配置文件读取。默认读当前目录的 config.json。"""
import json
import os
import pathlib


def load(path: str | None = None) -> dict:
    p = pathlib.Path(path or os.environ.get("TGPAK_CONFIG", "config.json"))
    if not p.exists():
        raise SystemExit(f"没有配置文件：{p}\n先 cp config.example.json config.json 再填。")
    cfg = json.loads(p.read_text(encoding="utf-8"))
    cfg["_path"] = str(p.resolve())
    return cfg


def paths(cfg: dict) -> tuple[pathlib.Path, pathlib.Path]:
    out = pathlib.Path(cfg["paths"]["out"]).resolve()
    staging = pathlib.Path(cfg["paths"]["staging"]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    staging.mkdir(parents=True, exist_ok=True)
    return out, staging


def period_dir(staging: pathlib.Path, period: int) -> pathlib.Path:
    """期数一律补零成 pNN，p1 也要写成 p01。"""
    return staging / f"p{int(period):02d}"
