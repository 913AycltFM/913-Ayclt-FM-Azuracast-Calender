import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
import os
import re

AZURACAST_URL = "https://radio.913aycltfm.com"
OUTPUT_FILE = "azuracast_schedule.ics"
API_KEY = os.environ.get("AZURACAST_API_KEY", "")

# --- ALLOWED STATIONS FILTER LIST ---
# Only stations that match these exact shortcodes will be processed.
ALLOWED_SHORTCODES = ["91.3_ayclt_fm", "91.3_ayclt_fm_hd2", "91.3_ayclt_fm_hd3"]
# ------------------------------------

def clean_text(text):
    if not text:
        return "Scheduled Programming"
    text = str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    text = text.replace("\n", "\\n").replace("\r", "")
    return re.sub(r'[\x00-\x1F\x7F]', '', text).strip()

def fold_line(line):
    if len(line.encode('utf-8')) <= 75:
        return line
    parts = []
    while len(line.encode('utf-8')) > 75:
        cut = 75
        while len(line[:cut].encode('utf-8')) > 75:
            cut -= 1
        parts.append(line[:cut])
        line = " " + line[cut:]
    parts.append(line)
    return "\r\n".join(parts)

def build_authenticated_request(url):
    headers = {
        'User-Agent': '913AycltFM-Secure-iCal-Exporter',
        'Accept': 'application/json'
    }
    if API_KEY:
        headers['Authorization'] = f"Bearer {API_KEY}"
    return urllib.request.Request(url, headers=headers)

def get_filtered_stations():
    url = f"{AZURACAST_URL}/api/stations"
    try:
        req = build_authenticated_request(url)
        with urllib.request.urlopen(req, timeout=15) as response:
            stations_data = json.loads(response.read().decode())
            discovered = {}
            for station in stations_data:
                s_id = str(station.get("id"))
                s_name = station.get("name", f"Station {s_id}")
                s_short = station.get("shortcode", s_id)
                
                # STRICT FILTERING RULE HERE
                if s_short not in ALLOWED_SHORTCODES:
                    print(f"Skipping unapproved station: '{s_name}' ({s_short})")
                    continue
                    
                discovered[s_id] = {
                    "name": s_name,
                    "public_url": f"{AZURACAST_URL}/public/{s_short}"
                }
            print(f"Filter active. Approved stations ready for extraction: {list(discovered.keys())}")
            return discovered
    except Exception as e:
        print(f"Error fetching stations list: {e}")
        return {}

def fetch_schedule(station_id):
    now = datetime.now(timezone.utc)
    start_iso = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end_iso = (now + timedelta(days=7)).replace(hour=23, minute=59, second=59, microsecond=0).isoformat()
    
    params = urllib.parse.urlencode({
        'start': start_iso,
        'end': end_iso,
        '_': int(now.timestamp())
    })
    
    url = f"{AZURACAST_URL}/api/station/{station_id}/schedule?{params}"
    try:
        req = build_authenticated_request(url)
        with urllib.request.urlopen(req, timeout=15) as response:
            raw_response = response.read().decode()
            return json.loads(raw_response)
    except Exception as e:
        print(f"Network error querying schedule for station {station_id}: {e}")
        return []

def format_ical_date(timestamp):
    try:
        dt = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
        return dt.strftime("%Y%m%dT%H%M%SZ")
    except Exception:
        return None

def main():
    os.makedirs(os.path.dirname(OUTPUT_FILE) if os.path.dirname(OUTPUT_FILE) else '.', exist_ok=True)
    now_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    
    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//91.3 Ayclt FM//Restricted Secure Exporter//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH"
    ]
    
    stations = get_filtered_stations()
    event_count = 0
    
    for station_id, info in stations.items():
        station_name = info["name"]
        public_url = info["public_url"]
        
        print(f"Extracting schedule for {station_name}...")
        schedule_data = fetch_schedule(station_id)
        
        for event in schedule_data:
            summary = clean_text(event.get("name") or event.get("title"))
            start_ts = event.get("start_timestamp")
            end_ts = event.get("end_timestamp")
            
            if not start_ts or not end_ts or not summary:
                continue
                
            start_str = format_ical_date(start_ts)
            end_str = format_ical_date(end_ts)
            
            if not start_str or not end_str:
                continue
                
            uid = f"ayclt-prog-{station_id}-{event.get('id', start_ts)}@913aycltfm"
            tagged_summary = clean_text(f"[{station_name}] {summary}")
            
            event_lines = [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{now_str}",
                f"DTSTART:{start_str}",
                f"DTEND:{end_str}",
                f"SUMMARY:{tagged_summary}",
                f"LOCATION:{public_url}",
                "END:VEVENT"
            ]
            
            for line in event_lines:
                ics_lines.append(fold_line(line))
            event_count += 1

    if event_count == 0:
        fallback_start = datetime.now(timezone.utc).strftime("%Y%m%dT%H0000Z")
        fallback_end = datetime.now(timezone.utc).strftime("%Y%m%dT%H3000Z")
        fallback_lines = [
            "BEGIN:VEVENT",
            "UID:fallback-maintenance@913aycltfm",
            f"DTSTAMP:{now_str}",
            f"DTSTART:{fallback_start}",
            f"DTEND:{fallback_end}",
            "SUMMARY:[System] No Broadcasts Scheduled",
            f"LOCATION:{AZURACAST_URL}/public",
            "END:VEVENT"
        ]
        for line in fallback_lines:
            ics_lines.append(fold_line(line))

    ics_lines.append("END:VCALENDAR")
    
    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as f:
        f.write("\r\n".join(ics_lines) + "\r\n")
    print(f"Export complete. File written with {event_count} approved schedule entries.")

if __name__ == "__main__":
    main()
