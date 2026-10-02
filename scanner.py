# -*- coding: utf-8 -*-
"""目录扫描"""
import os
from pathlib import Path
from typing import List


def iter_projects(root_dir) -> List[Path]:
    root = Path(root_dir)
    if not root.exists():
        raise FileNotFoundError(f"项目根目录不存在：{root}")
    return sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.name)


def find_financial_dirs(project_dir, keywords, max_depth: int = 4) -> List[Path]:
    root = Path(project_dir).resolve()
    found: List[Path] = []
    for dirpath, dirnames, _ in os.walk(root):
        cur = Path(dirpath)
        try:
            depth = len(cur.relative_to(root).parts)
        except ValueError:
            depth = 0
        if depth >= max_depth:
            dirnames[:] = []
            continue
        for d in list(dirnames):
            if any(k in d for k in keywords):
                found.append(cur / d)
                dirnames.remove(d)
    return sorted(found)


def list_images(fs_dir, exts) -> List[Path]:
    p = Path(fs_dir)
    imgs = [f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in exts]
    return sorted(imgs, key=lambda x: str(x).lower())