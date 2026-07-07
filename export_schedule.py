import json
import urllib.request
from datetime import datetime, timezone, timedelta
import os
import re

# --- CONFIGURATION ---
AZURACAST_URL = "https://radio.913aycltfm.com"
STATIONS = {
    "1": {   # Replace with the actual database ID number for this station
        "name": "91.3 Ayclt FM",
        "public_url": f"{AZURACAST_URL}/public/91.3_ayclt_fm"
    },
    "2": {   # Replace with the actual database ID number for HD2
        "name": "91.3 Ayclt FM HD2",
        "public_url": f"{AZURACAST_URL}/public/91.3_ayclt_fm_hd2"
    },
    "3": {   # Replace with the actual database ID number for HD3
        "name": "91.3 Ayclt FM HD3",
        "public_url": f"{AZURACAST_URL}/public/91.3_ayclt_fm_hd3"
    }
}
OUTPUT_FILE = "azuracast_schedule.ics"
# ---------------------

def clean_text(text):
    if not text:
        return "Live DJ Broadcast"
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

def fetch_schedule(station_id):
    now = datetime.now(timezone.utc)
    start_date = now.strftime("%Y-%m-%d")
    end_date = (now + timedelta(days=7)).strftime("%Y-%m-%d")
    
    # Appended a dynamic timestamp query parameter to bypass AzuraCast server-side API caching
    cache_bust = int(now.timestamp())
    url = f"{AZURACAST_URL}/api/station/{station_id}/schedule?start={start_date}&end={end_date}&_={cache_bust}"
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': '913AycltFM-iCal-Exporter'})
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"Error fetching station {station_id}: {e}")
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
        "PRODID:-//91.3 Ayclt FM//Unified Schedule Exporter//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH"
    ]
    
    event_count = 0
    
    for station_id, info in STATIONS.items():
        station_name = info["name"]
        public_url = info["public_url"]
        
        print(f"Fetching schedule for {station_name}...")
        schedule_data = fetch_schedule(station_id)
        
        for event in schedule_data:
            # FIX: AzuraCast assigns a boolean field 'is_streamer' to flag direct live DJ connections
            is_streamer = event.get("is_streamer", False)
            if not is_streamer:
                continue
                
            summary = clean_text(event.get("name") or event.get("title"))
            start_ts = event.get("start_timestamp")
            end_ts = event.get("end_timestamp")
            
            if not start_ts or not end_ts or not summary:
                continue
                
            start_str = format_ical_date(start_ts)
            end_str = format_ical_date(end_ts)
            
            if not start_str or not end_str:
                continue
                
            uid = f"ayclt-dj-{station_id}-{event.get('id', start_ts)}@913aycltfm"
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
            "SUMMARY:[System] No Live DJs Scheduled",
            f"LOCATION:{AZURACAST_URL}/public",
            "END:VEVENT"
        ]
        for line in fallback_lines:
            ics_lines.append(fold_line(line))

    ics_lines.append("END:VCALENDAR")
    
    print(f"Writing {max(event_count, 1)} live DJ events to the single iCalendar file...")
    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as f:
        f.write("\r\n".join(ics_lines) + "\r\n")
    print(f"Successfully saved live DJ schedule to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
