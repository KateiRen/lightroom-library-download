from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

from config import DOWNLOAD_ROOT


DEFAULT_DOWNLOAD_ROOT = DOWNLOAD_ROOT


def find_zip_archives(root: Path) -> list[Path]:
    if not root.exists():
        raise FileNotFoundError(f"Download folder does not exist: {root}")

    archives = sorted(root.rglob("*.zip"), key=lambda item: item.name.lower())
    return archives


def render_preview_tree(root: Path, archives: list[Path]) -> str:
    lines: list[str] = []
    lines.append(f"Download root: {root}")
    lines.append(f"ZIP files found: {len(archives)}")

    if not archives:
        lines.append("No ZIP archives to process.")
        return "\n".join(lines)

    for archive in archives:
        try:
            with zipfile.ZipFile(archive) as zf:
                members = zf.infolist()
                file_names = [info.filename for info in members if not info.is_dir()]
                top_level = sorted({Path(name).parts[0] for name in file_names if name})
                dir_names = sorted({str(Path(name).parent) for name in file_names if "/" in name})
                member_count = len(file_names)
                lines.append(f"- {archive.name}: {member_count} files")
                if top_level:
                    lines.append(f"  top-level folders: {', '.join(top_level[:8])}{' ...' if len(top_level) > 8 else ''}")
                if dir_names:
                    lines.append(f"  nested paths: {', '.join(dir_names[:5])}{' ...' if len(dir_names) > 5 else ''}")
                if not file_names:
                    lines.append("  no files inside archive")
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            lines.append(f"- {archive.name}: preview unavailable ({exc})")

    return "\n".join(lines)


def confirm_action(preview: str) -> bool:
    print("\nPreview of the extraction result:\n")
    print(preview)
    print("\nThis will extract all ZIP files into the download folder and delete each archive after a successful extraction.")
    answer = input("Proceed? [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def safe_extract_path(target_root: Path, member_name: str) -> Path:
    target = (target_root / member_name).resolve()
    try:
        target.relative_to(target_root.resolve())
    except ValueError as exc:
        raise ValueError(f"Unsafe archive member path: {member_name!r}") from exc
    return target


def extract_archive(archive: Path, root: Path) -> bool:
    try:
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                destination = safe_extract_path(root, info.filename)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info, "r") as src, open(destination, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"Failed to extract {archive.name}: {exc}")
        return False

    try:
        archive.unlink()
        print(f"Extracted and removed: {archive.name}")
    except OSError as exc:
        print(f"Extracted successfully but could not delete {archive.name}: {exc}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract ZIP archives in a download folder and delete them after successful extraction.")
    parser.add_argument("--root", type=Path, default=DEFAULT_DOWNLOAD_ROOT, help="Folder containing the ZIP files to restore.")
    parser.add_argument("--dry-run", action="store_true", help="Show the preview without extracting.")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt.")
    args = parser.parse_args()

    root = args.root
    archives = find_zip_archives(root)

    preview = render_preview_tree(root, archives)

    if args.dry_run:
        print(preview)
        return 0

    if not args.yes:
        if not confirm_action(preview):
            print("Aborted.")
            return 0

    if not archives:
        print("No ZIP files found to restore.")
        return 0

    remaining = archives[:]
    while remaining:
        archive = remaining.pop(0)
        if archive.exists() and archive.suffix.lower() == ".zip":
            extract_archive(archive, root)

        remaining = find_zip_archives(root)
        if not remaining:
            break

    print("\nDone. All ZIP archives processed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt as exc:
        print("\nInterrupted by user.")
        raise SystemExit(130) from exc
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
