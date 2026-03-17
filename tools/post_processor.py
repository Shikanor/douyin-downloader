"""
post_processor.py — 视频后处理脚本

将下载目录下所有嵌套子文件夹中的 .mp4 文件提取到根目录，
并删除已清空的子文件夹（封面、音乐、JSON 等附件一并清除）。

用法：
    python tools/post_processor.py [--path /your/save/path] [--config config.yml] [--dry-run]

参数：
    --path      指定根目录（优先级高于配置文件）
    --config    配置文件路径（默认 config.yml）
    --dry-run   只预览操作，不实际移动/删除文件
"""

import argparse
import shutil
import sys
from pathlib import Path
from typing import List, Tuple

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


def _load_path_from_config(config_path: str) -> str:
    if yaml is None:
        print("[警告] 未安装 pyyaml，无法读取配置文件，请通过 --path 手动指定路径")
        return ""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get("path", "")
    except FileNotFoundError:
        print(f"[警告] 配置文件不存在：{config_path}")
        return ""


def _resolve_dest_path(root: Path, filename: str) -> Path:
    """处理文件名冲突：若目标已存在则追加 _1, _2 ..."""
    dest = root / filename
    if not dest.exists():
        return dest
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    counter = 1
    while True:
        candidate = root / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def collect_videos(root: Path) -> List[Path]:
    """收集所有嵌套在子文件夹中的 .mp4 文件（排除根目录直属文件）。"""
    videos = []
    for mp4 in root.rglob("*.mp4"):
        if mp4.parent == root:
            continue  # 已在根目录，跳过
        videos.append(mp4)
    return sorted(videos)


def run(root: Path, dry_run: bool) -> Tuple[int, int]:
    """
    执行后处理：移动视频到根目录，清理空子目录。

    返回 (moved_count, deleted_dir_count)
    """
    videos = collect_videos(root)
    if not videos:
        print("未发现需要处理的视频文件。")
        return 0, 0

    moved = 0
    for video in videos:
        dest = _resolve_dest_path(root, video.name)
        rel_src = video.relative_to(root)
        rel_dest = dest.relative_to(root)
        if dry_run:
            print(f"  [预览] 移动：{rel_src}  →  {rel_dest}")
        else:
            shutil.move(str(video), str(dest))
            print(f"  [移动] {rel_src}  →  {rel_dest}")
        moved += 1

    # 收集所有非根直属子目录，从深到浅尝试删除
    subdirs = sorted(
        {p.parent for p in videos},
        key=lambda p: len(p.parts),
        reverse=True,
    )
    # 展开到所有上级目录（直到 root 为止）
    all_subdirs = set()
    for d in subdirs:
        current = d
        while current != root:
            all_subdirs.add(current)
            current = current.parent

    deleted = 0
    for d in sorted(all_subdirs, key=lambda p: len(p.parts), reverse=True):
        if dry_run:
            contents = list(d.iterdir()) if d.exists() else []
            print(f"  [预览] 删除目录：{d.relative_to(root)}  ({len(contents)} 个文件/子目录)")
            deleted += 1
        else:
            if d.exists():
                shutil.rmtree(str(d))
                print(f"  [删除] {d.relative_to(root)}")
                deleted += 1

    return moved, deleted


def main() -> int:
    parser = argparse.ArgumentParser(
        description="抖音下载器后处理：提取 .mp4 到根目录并清理子文件夹"
    )
    parser.add_argument("--path", help="根目录路径（优先于配置文件）")
    parser.add_argument("--config", default="config.yml", help="配置文件路径（默认 config.yml）")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不实际操作")
    args = parser.parse_args()

    # 确定根目录
    if args.path:
        root_str = args.path
    else:
        root_str = _load_path_from_config(args.config)

    if not root_str:
        print("[错误] 未指定根目录，请通过 --path 或配置文件中的 path 字段指定。")
        return 1

    root = Path(root_str).expanduser().resolve()
    if not root.exists():
        print(f"[错误] 目录不存在：{root}")
        return 1

    mode = "【预览模式 - 不会修改文件】" if args.dry_run else "【执行模式】"
    print(f"\n抖音后处理 {mode}")
    print(f"根目录：{root}\n")

    moved, deleted = run(root, args.dry_run)

    if args.dry_run:
        print(f"\n预览完成：将移动 {moved} 个视频，删除 {deleted} 个目录（含附件）。")
        print("运行时去掉 --dry-run 参数即可实际执行。")
    else:
        print(f"\n完成：已移动 {moved} 个视频，删除 {deleted} 个目录。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
