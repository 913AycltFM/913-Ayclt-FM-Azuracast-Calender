import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

AZURACAST_URL = "https://radio.913aycltfm.com"
OUTPUT_FILE = "azuracast_schedule.ics"
API_KEY = os.environ.get("AZURACAST_API_KEY", "")

ALLOWED_SHORTCODES = [
    "91.3_ayclt_fm",
    "91.3_ayclt_fm_hd2",
    "91.3_ayclt_fm_hd3",
]

WINDOW_HOURS = 24 * 7
HTTP_TIMEOUT = 30
HTTP_RETRIES = 3


def clean_text(value, fallback="Scheduled Programming"):
    text = str(value or "").strip()
    if not text:
        return fallback

    # Remove characters that iCalendar does not allow in text values.
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)
    text = text.replace("\r", " ").replace("\n", " ")

    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
    ).strip()


def fold_line(line):
    """Fold an iCalendar content line at 75 UTF-8 octets."""
    if len(line.encode("utf-8")) <= 75:
        return line

    parts = []
    remaining = line
    first = True

    while remaining:
        limit = 75 if first else 74
        encoded = remaining.encode("utf-8")

        if len(encoded) <= limit:
            parts.append(remaining if first else " " + remaining)
            break

        cut = limit
        while cut > 0:
            try:
                piece = encoded[:cut].decode("utf-8")
                break
            except UnicodeDecodeError:
                cut -= 1

        if cut == 0:
            raise ValueError("Unable to safely fold UTF-8 iCalendar line.")

        parts.append(piece if first else " " + piece)
        remaining = remaining[len(piece):]
        first = False

    return "\r\n".join(parts)


def build_request(url):
    headers = {
        "User-Agent": "913AycltFM-AzuraCast-iCal/3.0",
        "Accept": "application/json",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    return urllib.request.Request(url, headers=headers)


def get_json(url):
    last_error = None

    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            request = build_request(url)
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw)

        except urllib.error.HTTPError as exc:
            last_error = exc

            # Retry rate limits and temporary server failures.
            if exc.code not in (429, 500, 502, 503, 504) or attempt == HTTP_RETRIES:
                raise

            retry_after = exc.headers.get("Retry-After")
            try:
                delay = max(1, min(int(retry_after), 15)) if retry_after else 2 ** (attempt - 1)
            except (TypeError, ValueError):
                delay = 2 ** (attempt - 1)

            print(
                f"HTTP {exc.code} from AzuraCast; "
                f"retrying in {delay}s (attempt {attempt}/{HTTP_RETRIES})..."
            )
            time.sleep(delay)

        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc

            if attempt == HTTP_RETRIES:
                raise

            delay = 2 ** (attempt - 1)
            print(
                f"Temporary AzuraCast/API error: {exc}; "
                f"retrying in {delay}s (attempt {attempt}/{HTTP_RETRIES})..."
            )
            time.sleep(delay)

    raise RuntimeError(f"Unable to fetch JSON from {url}: {last_error}")


def get_filtered_stations():
    stations_data = get_json(f"{AZURACAST_URL}/api/stations")

    if not isinstance(stations_data, list):
        raise RuntimeError("AzuraCast /api/stations did not return a list.")

    stations = {}

    for station in stations_data:
        if not isinstance(station, dict):
            continue

        shortcode = str(station.get("shortcode", "")).strip()
        if shortcode not in ALLOWED_SHORTCODES:
            continue

        station_id = str(station.get("id", "")).strip()
        if not station_id:
            raise RuntimeError(f"Approved station '{shortcode}' has no ID.")

        if station_id in stations:
            raise RuntimeError(
                f"Duplicate AzuraCast station ID '{station_id}' detected."
            )

        stations[station_id] = {
            "name": str(station.get("name") or shortcode).strip(),
            "shortcode": shortcode,
            "public_url": f"{AZURACAST_URL}/public/{shortcode}",
        }

    found = {station["shortcode"] for station in stations.values()}
    missing = [shortcode for shortcode in ALLOWED_SHORTCODES if shortcode not in found]

    if missing:
        raise RuntimeError(
            "Approved station(s) not found in AzuraCast: " + ", ".join(missing)
        )

    return stations


def fetch_schedule(station_id, start_dt, end_dt):
    params = urllib.parse.urlencode(
        {
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "_": int(datetime.now(timezone.utc).timestamp()),
        }
    )

    url = f"{AZURACAST_URL}/api/station/{station_id}/schedule?{params}"
    data = get_json(url)

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in ("schedule", "data", "items", "results"):
            value = data.get(key)
            if isinstance(value, list):
                return value

    raise RuntimeError(
        f"Unexpected schedule response for station {station_id}: "
        f"{type(data).__name__}"
    )


def timestamp_to_datetime(value):
    if value is None or value == "":
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)

    text = str(value).strip()

    if not text:
        return None

    if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return datetime.fromtimestamp(float(text), tz=timezone.utc)

    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def event_times(event):
    if not isinstance(event, dict):
        return None, None

    start_value = (
        event.get("start_timestamp")
        if event.get("start_timestamp") is not None
        else event.get("start")
    )
    end_value = (
        event.get("end_timestamp")
        if event.get("end_timestamp") is not None
        else event.get("end")
    )

    start_dt = timestamp_to_datetime(start_value)
    end_dt = timestamp_to_datetime(end_value)

    if not start_dt or not end_dt or end_dt <= start_dt:
        return None, None

    return start_dt, end_dt


def format_ical_date(dt):
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def stable_uid(station_id, event, start_dt, end_dt):
    event_id = str(
        event.get("id")
        or event.get("schedule_id")
        or event.get("station_schedule_id")
        or "event"
    )

    start = int(start_dt.timestamp())
    end = int(end_dt.timestamp())

    return f"ayclt-{station_id}-{event_id}-{start}-{end}@913aycltfm"


def make_event(station_id, station, event, start_dt, end_dt):
    name = (
        event.get("name")
        or event.get("title")
        or event.get("playlist_name")
        or event.get("streamer_name")
        or "Scheduled Programming"
    )

    summary = clean_text(f"[{station['name']}] {name}")

    lines = [
        "BEGIN:VEVENT",
        f"UID:{stable_uid(station_id, event, start_dt, end_dt)}",
        f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT000000Z')}",
        f"DTSTART:{format_ical_date(start_dt)}",
        f"DTEND:{format_ical_date(end_dt)}",
        f"SUMMARY:{summary}",
        f"LOCATION:{station['public_url']}",
        "END:VEVENT",
    ]

    return [fold_line(line) for line in lines]


def main():
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(hours=WINDOW_HOURS)

    print(
        "Building rolling 7-day calendar: "
        f"{format_ical_date(now)} through {format_ical_date(window_end)}"
    )

    stations = get_filtered_stations()
    events = []
    seen = set()

    for station_id, station in stations.items():
        print(f"Fetching {station['name']} ({station['shortcode']})...")

        try:
            schedule_data = fetch_schedule(station_id, now, window_end)
        except Exception as exc:
            raise RuntimeError(
                f"Could not fetch schedule for {station['shortcode']}: {exc}"
            ) from exc

        print(f"  AzuraCast returned {len(schedule_data)} schedule records.")

        for event in schedule_data:
            start_dt, end_dt = event_times(event)

            if not start_dt or not end_dt:
                continue

            # Keep events that overlap the exact rolling 7-day window.
            if end_dt <= now or start_dt >= window_end:
                continue

            key = (
                station_id,
                str(
                    event.get("id")
                    or event.get("schedule_id")
                    or event.get("station_schedule_id")
                    or ""
                ),
                int(start_dt.timestamp()),
                int(end_dt.timestamp()),
            )

            if key in seen:
                continue

            seen.add(key)
            events.append((start_dt, end_dt, station_id, station, event))

    events.sort(key=lambda item: (item[0], item[2], item[1]))

    # Fail loudly if duplicate UIDs would be generated.
    uids = set()
    for start_dt, end_dt, station_id, station, event in events:
        uid = stable_uid(station_id, event, start_dt, end_dt)
        if uid in uids:
            raise RuntimeError(f"Duplicate iCalendar UID generated: {uid}")
        uids.add(uid)

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//91.3 Ayclt FM//AzuraCast Rolling Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:91.3 Ayclt FM",
        # DTSTART/DTEND are explicit UTC values ending in Z.
        # Do not declare a conflicting X-WR-TIMEZONE.
    ]

    for start_dt, end_dt, station_id, station, event in events:
        lines.extend(make_event(station_id, station, event, start_dt, end_dt))

    lines.append("END:VCALENDAR")

    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as handle:
        handle.write("\r\n".join(lines) + "\r\n")

    print(
        f"Export complete: {len(events)} events across {len(stations)} stations. "
        "Window is exactly 7 rolling days."
    )


if __name__ == "__main__":
    main()
