from __future__ import annotations
import argparse
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import DOWNLOAD_ROOT


def format_duration(seconds: float) -> str:
    total = max(0.0, seconds)
    hours = int(total // 3600)
    minutes = int((total % 3600) // 60)
    secs = total % 60
    if hours:
        return f"{hours}h {minutes}m {secs:.1f}s"
    if minutes:
        return f"{minutes}m {secs:.1f}s"
    return f"{secs:.1f}s"


def format_speed(bytes_count: float, seconds: float) -> str:
    if seconds <= 0:
        return "0 B/s"
    bytes_per_second = bytes_count / seconds
    units = ["B/s", "KB/s", "MB/s", "GB/s"]
    value = float(bytes_per_second)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B/s":
                return f"{int(value):,} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} GB/s"


def parse_display_size(display_size: str) -> int:
    normalized = display_size.strip().replace(",", "")
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([KMGT]?B)", normalized, flags=re.IGNORECASE)
    if not match:
        return 0

    value = float(match.group(1))
    unit = match.group(2).upper()
    factors = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3, "TB": 1024 ** 4}
    return int(value * factors.get(unit, 1))


def estimate_completion(entries: list["DownloadEntry"], target_path: Path, recent_speeds: list[float], elapsed_so_far: float) -> str:
    remaining_entries = [
        item for item in entries if not (target_path / item.filename).exists()
    ]
    if not remaining_entries:
        return "Forecast: complete."

    if not recent_speeds:
        return "Forecast: waiting for speed samples."

    remaining_bytes = sum(parse_display_size(entry.display_size) for entry in remaining_entries)
    avg_speed = sum(recent_speeds) / len(recent_speeds)
    if avg_speed <= 0:
        return "Forecast: speed is currently zero; retrying later."

    remaining_seconds = remaining_bytes / avg_speed
    total_seconds = elapsed_so_far + remaining_seconds
    return (
        f"Forecast: {format_duration(remaining_seconds)} remaining, "
        f"about {format_duration(total_seconds)} total."
    )

  
  

TARGET_PATH = DOWNLOAD_ROOT

RETRY_COUNT = 3

CHUNK_SIZE = 1024 * 1024

  
  

@dataclass(frozen=True)

class DownloadEntry:

    index: int

    description: str

    filename: str

    display_size: str

    url: str

  
  

def find_markdown_path() -> Path:
    preferred_names = [
        "links.md",
        "dl.md",
    ]

    for name in preferred_names:
        candidate = Path(__file__).with_name(name)
        if candidate.exists():
            return candidate

    candidates = sorted(
        Path(__file__).parent.glob("lightroom-library-download-links-*.md"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        return candidates[0]

    return Path(__file__).with_name("links.md")


def is_archive_url(url: str) -> bool:
    lower = url.lower()
    if re.search(r"(?:\.zip|\.rar|\.7z|\.tar|\.gz|\.tgz)(?:[?#]|$)", lower):
        return True
    if "download.adobe.com" in lower or "blob:" in lower:
        return True
    return False


def parse_markdown(path: Path) -> list[DownloadEntry]:

    row_pattern = re.compile(

        r"^\|\s*(\d+)\s*\|\s*(.*?)\s*\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|\s*<([^>]+)>\s*\|"

    )

    entries: list[DownloadEntry] = []

    for line in path.read_text(encoding="utf-8").splitlines():

        match = row_pattern.match(line)

        if not match:
            continue

        filename = match.group(3).strip()
        url = match.group(5).strip()
        if not is_archive_url(url):
            continue

        entries.append(

            DownloadEntry(

                index=int(match.group(1)),

                description=match.group(2).strip(),

                filename=filename,

                display_size=match.group(4).strip(),

                url=url,

            )

        )

    return entries


def refresh_archive_links() -> Path:
    extractor = Path(__file__).with_name("extract-lightroom-download-links.py")
    if not extractor.exists():
        raise FileNotFoundError(f"Extractor script not found: {extractor}")

    print("  Adobe archive links are no longer authorized; refreshing signed URLs from Lightroom.")
    result = subprocess.run(
        [sys.executable, str(extractor)],
        cwd=str(Path(__file__).parent),
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        details = "\n".join(part for part in [stdout, stderr] if part)
        raise RuntimeError(
            f"Failed to refresh Adobe archive links (exit code {result.returncode}).\n{details}"
        )

    refreshed = find_markdown_path()
    if not refreshed.exists():
        raise FileNotFoundError(f"Refreshed markdown file not found: {refreshed}")

    return refreshed

  
  

def remote_size(url: str) -> int | None:

    request = Request(url, method="HEAD", headers={"User-Agent": "lightroom-library-downloader/1.0"})

    try:
        with urlopen(request, timeout=60) as response:
            value = response.headers.get("Content-Length")
            return int(value) if value and value.isdigit() else None
    except (HTTPError, URLError, TimeoutError, ValueError):
        return None

  
  

def download(entry: DownloadEntry, destination: Path, expected_size: int | None) -> float:

    existing_size = destination.stat().st_size if destination.exists() else 0

    headers = {"User-Agent": "lightroom-library-downloader/1.0"}

    if existing_size:
        headers["Range"] = f"bytes={existing_size}-"

    request = Request(entry.url, headers=headers)
    start = time.monotonic()

    with urlopen(request, timeout=120) as response:
        status = getattr(response, "status", response.getcode())

        if existing_size and status == 206:
            mode = "ab"
        elif existing_size and status == 200:
            print("  Server did not resume; restarting this file from byte 0.")
            mode = "wb"
            existing_size = 0
        else:
            mode = "wb"

        downloaded = existing_size

        with destination.open(mode + "") as file:
            while True:
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break

                file.write(chunk)
                downloaded += len(chunk)

                if expected_size:
                    percent = downloaded * 100 / expected_size
                    print(f"\r  {downloaded:,}/{expected_size:,} bytes ({percent:.1f}%)", end="")
                else:
                    print(f"\r  {downloaded:,} bytes", end="")

        print()

    if expected_size is not None:
        final_size = destination.stat().st_size
        if final_size != expected_size:
            raise RuntimeError(
                f"Size mismatch for {entry.filename}: got {final_size:,} bytes, expected {expected_size:,} bytes"
            )

    elapsed = time.monotonic() - start
    return elapsed

  
  

def process_entry(
    entry: DownloadEntry,
    total: int,
    target_path: Path,
    entries: list[DownloadEntry],
    recent_speeds: list[float],
    total_start: float,
) -> None:

    destination = target_path / entry.filename

    print(f"[{entry.index}/{total}] {entry.filename} ({entry.display_size})")

    if destination.exists():
        print("  Already downloaded; skipping by filename.")
        return

    expected_size = remote_size(entry.url)

    if expected_size is not None:
        print(f"  Remote size: {expected_size:,} bytes")

    print("  Downloading.")

    for attempt in range(1, RETRY_COUNT + 1):
        try:
            elapsed = download(entry, destination, expected_size)
            final_size = destination.stat().st_size
            avg_speed = format_speed(final_size, elapsed)
            print(f"  Complete in {format_duration(elapsed)} at {avg_speed}.")

            if elapsed > 0:
                speed_bps = final_size / elapsed
                recent_speeds.append(speed_bps)
                if len(recent_speeds) > 5:
                    recent_speeds.pop(0)
                elapsed_so_far = time.monotonic() - total_start
                print(f"  {estimate_completion(entries, target_path, recent_speeds, elapsed_so_far)}")
            return
        except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
            if isinstance(exc, HTTPError) and exc.code in {401, 403}:
                refreshed_path = refresh_archive_links()
                refreshed_entries = parse_markdown(refreshed_path)
                refreshed_entry = next((item for item in refreshed_entries if item.filename == entry.filename), None)
                if refreshed_entry is None:
                    raise RuntimeError(
                        f"The refreshed Adobe link list no longer contains {entry.filename}."
                    ) from exc

                print(f"  Refreshed link for {entry.filename}; retrying with a new signed URL.")
                entry = refreshed_entry
                expected_size = remote_size(entry.url)
                if expected_size is not None:
                    print(f"  Remote size: {expected_size:,} bytes")
                continue

            print(f"  Attempt {attempt} failed: {exc}")
            if attempt == RETRY_COUNT:
                raise
            time.sleep(10 * attempt)

  
  

def main() -> None:

    parser = argparse.ArgumentParser(description="Download Adobe Lightroom library archives from markdown links.")

    parser.add_argument("--dry-run", action="store_true", help="Parse the markdown and print what would be downloaded.")

    args = parser.parse_args()
    total_start = time.monotonic()

    markdown_path = find_markdown_path()

    if not markdown_path.exists():

        raise FileNotFoundError(f"Markdown file not found: {markdown_path}")

    entries = parse_markdown(markdown_path)

    if not entries:

        raise RuntimeError(f"No real archive download entries found in: {markdown_path}")

    TARGET_PATH.mkdir(parents=True, exist_ok=True)

    print(f"Found {len(entries)} download entries.")

    print(f"Target path: {TARGET_PATH}")

    print(f"Using markdown file: {markdown_path}")

    if args.dry_run:

        for entry in entries:

            print(f"[{entry.index}/{len(entries)}] {entry.filename} ({entry.display_size})")

        return

    recent_speeds: list[float] = []
    for entry in entries:
        process_entry(entry, len(entries), TARGET_PATH, entries, recent_speeds, total_start)

    total_elapsed = time.monotonic() - total_start
    print(f"Total elapsed: {format_duration(total_elapsed)}")
    print("Done.")

  
  

if __name__ == "__main__":
    main()