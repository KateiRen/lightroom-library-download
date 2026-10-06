from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright


LIGHTROOM_DOWNLOAD_PAGE = "https://lightroom.adobe.com/lightroom-library-download"
OUTPUT_PATH = Path(__file__).with_name("links.md")
BROWSER_PROFILE_PATH = Path(__file__).with_name(".lightroom-browser-profile")
WAIT_TIMEOUT_MS = 15 * 60 * 1000


def strip_adobe_json_guard(text: str) -> str:
    stripped = re.sub(r"^while \(1\) \{\}\s*", "", text)
    if not stripped.startswith("{"):
        raise ValueError("Response did not contain a JSON object.")
    return stripped


def format_size(byte_count: int) -> str:
    value = float(byte_count)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.2f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    raise AssertionError("unreachable")


def natural_key(name: str) -> list[int | str]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def is_archive_detail_url(url: str) -> bool:
    return re.search(r"/v2/catalogs/[^/?#]+/archives/[^/?#]+(?:[?#].*)?$", url) is not None


def parse_adobe_json(text: str) -> dict[str, Any]:
    return json.loads(strip_adobe_json_guard(text))


def write_markdown(archive: dict[str, Any], output_path: Path) -> None:
    files = sorted(archive.get("archive_files", []), key=lambda item: natural_key(item.get("name", "")))
    if not files:
        raise RuntimeError("Archive response did not contain any archive_files.")

    total_bytes = sum(int(item.get("size") or 0) for item in files)
    archive_summary = archive.get("archive_summary") or {}

    lines = [
        "# Adobe Lightroom library download links",
        "",
        f"- Source page: <{LIGHTROOM_DOWNLOAD_PAGE}>",
        f"- Archive ID: `{archive.get('id', '')}`",
        f"- Status: `{archive.get('status', '')}`",
    ]

    if archive.get("created"):
        lines.append(f"- Archive requested: `{archive['created']}`")
    if archive.get("expires"):
        lines.append(f"- Adobe archive available until: `{archive['expires']}`")

    lines.extend(
        [
            f"- Link extraction time: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}`",
            f"- Files: {len(files)}",
            f"- Total size: {format_size(total_bytes)}",
        ]
    )

    if archive_summary:
        lines.append(f"- Archive summary: `{json.dumps(archive_summary, ensure_ascii=False)}`")

    lines.extend(
        [
            "",
            "> Note: these are signed direct download URLs captured from Adobe Lightroom. The Adobe archive may remain available until the date above, but each direct signed URL can expire earlier and may need to be refreshed from the source page.",
            ">",
            "> Automation note: do not store or reuse Adobe browser session cookies or account auth tokens. The links below are already pre-signed direct download URLs and should be used as-is while they remain valid.",
            "",
            "| # | Description | File | Size | Download link |",
            "|---:|---|---|---:|---|",
        ]
    )

    for index, item in enumerate(files, 1):
        name = str(item.get("name", ""))
        size = format_size(int(item.get("size") or 0))
        url = str(item.get("location", ""))
        description = f"Lightroom library archive file {name}"
        lines.append(f"| {index} | {description} | `{name}` | {size} | <{url}> |")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE_PATH),
            headless=False,
            accept_downloads=False,
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        captured_archive = None
        last_error = "Waiting for Lightroom's archive-detail response."

        def capture_archive_response(response: Any) -> None:
            nonlocal captured_archive, last_error
            if captured_archive is not None:
                return
            if response.status != 200 or not is_archive_detail_url(response.url):
                return
            try:
                payload = parse_adobe_json(response.text())
                if payload.get("archive_files"):
                    captured_archive = payload
            except Exception as exc:
                last_error = f"Could not parse archive response from {response.url}: {exc}"

        page.on("response", capture_archive_response)

        print(f"Opening {LIGHTROOM_DOWNLOAD_PAGE}")
        print("Sign in in the browser if Adobe asks you to.")
        print("After sign-in, the script captures Lightroom's own archive-detail response.")
        page.goto(LIGHTROOM_DOWNLOAD_PAGE, wait_until="domcontentloaded")

        deadline = time.monotonic() + WAIT_TIMEOUT_MS / 1000
        while captured_archive is None and time.monotonic() < deadline:
            try:
                page.wait_for_timeout(1000)
            except Exception as exc:
                last_error = str(exc)
                break

        browser.close()

    if captured_archive is None:
        raise RuntimeError(f"Timed out waiting for Adobe Lightroom archive metadata. Last error: {last_error}")

    write_markdown(captured_archive, OUTPUT_PATH)
    file_count = len(captured_archive.get("archive_files", []))
    print(f"Wrote {file_count} links to: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
