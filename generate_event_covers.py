#!/usr/bin/env python3
"""Create 800x400 landscape event covers for the AzuraCast iCalendar feed."""
import hashlib
import re
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image, ImageOps

CALENDAR = Path("azuracast_schedule.ics")
COVER_DIR = Path("event_covers")
WIDTH, HEIGHT = 800, 400
RAW_BASE = "https://raw.githubusercontent.com/913AycltFM/913-Ayclt-FM-Azuracast-Calender/main/event_covers"

def unfold(lines):
    result = []
    for line in lines:
        if line.startswith((" ", "\t")) and result:
            result[-1] += line[1:]
        else:
            result.append(line)
    return result

def fold(line):
    parts, current, size = [], "", 0
    for char in line:
        n = len(char.encode("utf-8"))
        if size + n > 75:
            parts.append(current)
            current, size = " ", 1
        current += char
        size += n
    parts.append(current)
    return "\r\n".join(parts)

def download_and_resize(source_url):
    filename = hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:20] + ".jpg"
    output = COVER_DIR / filename
    request = urllib.request.Request(
        source_url,
        headers={"User-Agent": "913AycltFM-Event-Cover-Generator/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        image_data = response.read()

    COVER_DIR.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(".tmp")
    from io import BytesIO
    with Image.open(BytesIO(image_data)) as source:
        source = ImageOps.exif_transpose(source).convert("RGB")
        cover = ImageOps.fit(
            source, (WIDTH, HEIGHT),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
        cover.save(temp, format="JPEG", quality=90, optimize=True)
    temp.replace(output)
    return f"{RAW_BASE}/{filename}"

def main():
    if not CALENDAR.exists():
        raise SystemExit("Calendar file not found.")
    original = CALENDAR.read_text(encoding="utf-8").splitlines()
    lines = unfold(original)
    converted = {}
    failures = 0
    for index, line in enumerate(lines):
        if not line.startswith(("DESCRIPTION:", "IMAGE;")):
            continue
        match = re.search(r'cover="(https?://[^"]+)"', line)
        if not match and line.startswith("IMAGE;"):
            match = re.search(r":(https?://\S+)$", line)
        if not match:
            continue
        source_url = match.group(1)
        if source_url not in converted:
            try:
                converted[source_url] = download_and_resize(source_url)
                print(f"Created 800x400 cover for {source_url}")
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                print(f"WARNING: could not resize {source_url}: {exc}")
                converted[source_url] = source_url
                failures += 1
        lines[index] = line[:match.start(1)] + converted[source_url] + line[match.end(1):]

    CALENDAR.write_text(
        "\r\n".join(fold(line) for line in lines) + "\r\n",
        encoding="utf-8",
        newline="",
    )
    print(f"Event cover conversion complete. Unique images: {len(converted)}; failures: {failures}.")
    if failures:
        print("Some source images were left unchanged; check the warnings above.")

if __name__ == "__main__":
    main()
