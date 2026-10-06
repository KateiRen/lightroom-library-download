# Lightroom Archive Downloader

This project downloads Adobe Lightroom archive files from a prepared list of signed direct-download URLs.

## Why

After many years of buying new annual subscriptions to benefit from Lightroom CC and 1TB of online storage I found out, that I am barely using the service anymore and that I wouls be better of by combining my stored pictures with my automated camera uploads to OneDrive into a new archive sitting on my Synology NAS.

Initially I thought it would need some hack to get all the photos downloaded, until I discovered that Adobe actually offers exact that option.
However, in my case the download page contained 258 links to distinct zip files With a combined size of 583 GB. Have a lot of fun downloading this manually...

Thats when I discovered the offical export option exists but is practically useless until you apply some automation. 

## First step: prepare the Lightroom archive

You can now download all your synced Lightroom files (photos and videos) from your device as ZIP archives.

Go to [https://lightroom.adobe.com/lightroom-library-download](https://lightroom.adobe.com/lightroom-library-download)

Sign in with your Google, Facebook, Apple, Microsoft, or LINE account credentials for your Adobe account.

Choose Export my photos to begin preparing your files in ZIP format.
This will take quite some time and you will be notified by email when its done.




## The Automated Workflow

1. Run the extractor (extract-lightroom-download-links.py) to open Adobe Lightroom in a browser and capture the archive links. This will store all download urls in `links.md`.
2. Run the downloader to fetch the archive files into the target download folder (configured in config.py).
4. If Adobe rejects a signed URL with `401` or `403`, the downloader will invoke the extractor again to get new working links.

## Scripts

- `extract-lightroom-download-links.py` - opens the download page, lets you log in, waits for the archive metadata, and writes signed URLs to `links.md`.
- `download-prepared-links.py` - reads the prepared links and downloads each archive file to the configured download path (configure.py).
- `restore-downloads.py` - previews ZIP archives from the download folder, extracts them into the target structure, and deletes each archive after a successful extraction.
- `test_dl.py` - regression tests for parsing and filtering the link list.

## Setup

This project uses `uv`.

```bash
cd "C:/Users/karst/GitHub/tst/downloadLightroom"
uv sync
```

If Playwright has not been installed yet:

```bash
uv run python -m playwright install
```

## Generate the archive link list

```bash
uv run python extract-lightroom-download-links.py
```

The script uses a persistent browser profile and waits for Lightroom to provide the archive metadata. If Adobe asks you to sign in, do so in the browser window.

## Download the archives

```bash
uv run python download-prepared-links.py
```

Dry run:

```bash
uv run python download-prepared-links.py --dry-run
```

## Why this is necessary

Getting the Lightroom library archive back from Adobe is not straightforward. The official Adobe workflow exposes a download page, but the actual archive is split into many signed direct-download URLs, and those URLs can expire or stop working while the browser session remains valid.

In practice, the only realistic way to recover the data is to grab the Adobe-generated archive metadata and signed direct links from the authenticated browser session, then download the pieces in order. Without this kind of automation, the archive is effectively locked behind a fragile web workflow with many moving parts.

For a real example, the archive set in this project contained 254 ZIP files with a total payload of around 560+ GB. The files ranged from small part files of a few MB to multi-gigabyte archive chunks, and the observed average transfer speed was about 13 Mbit/s. At that rate, a full recovery run takes a long time and is easy to interrupt or lose if the signed URLs are not refreshed at the right time.

This is why these scripts matter: they make the process possible at all by capturing the correct signed URLs from Adobe, reusing the authenticated browser session, validating the output, and retrying when Adobe invalidates the old archive links.

## License

This project is licensed under the MIT License. See the LICENSE file for details.

## Important notes

- The downloader prefers `links.md` as the source for archive URLs.
- It skips files that already exist by filename.
- Adobe site authentication usually remains active even when the signed archive URLs are no longer valid, so rebuilding `links.md` from the browser session usually works without re-signing in.
- With a real archive set like this one, the total transfer can be hundreds of GB and take many hours, so automation is essential to keep the process stable and resumable.
- Generated browser profiles, downloaded archive files, and temporary metadata are intentionally left out of source control.

