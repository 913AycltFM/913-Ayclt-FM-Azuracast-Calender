import json
import urllib.request
from datetime import datetime, timezone, timedelta

AZURACAST_URL = "https://913aycltfm.com"
# Let's test using the first station string
STATION_ID = "91.3_ayclt_fm" 

now = datetime.now(timezone.utc)
start_date = now.strftime("%Y-%m-%d")
end_date = (now + timedelta(days=7)).strftime("%Y-%m-%d")
url = f"{AZURACAST_URL}/api/station/{STATION_ID}/schedule?start={start_date}&end={end_date}"

print(f"--- TRIGGERING TEST API CALL ---")
print(f"Target URL: {url}\n")

try:
    req = urllib.request.Request(url, headers={'User-Agent': '913AycltFM-Debug'})
    with urllib.request.urlopen(req, timeout=15) as response:
        raw_data = response.read().decode()
        parsed_json = json.loads(raw_data)
        
        print("SUCCESS! Connection established.")
        print(f"Total raw items returned from API: {len(parsed_json)}")
        
        if len(parsed_json) > 0:
            print("\n--- SAMPLE FIRST EVENT KEYS & DATA ---")
            print(json.dumps(parsed_json[0], indent=2))
        else:
            print("\nWARNING: The API returned an empty list [].")
            print("This means the station identifier '91.3_ayclt_fm' is likely incorrect in the API context.")
            print("Try changing your station IDs to integers (e.g., '1', '2', '3') in the STATIONS dictionary.")

except Exception as e:
    print(f"CRITICAL NETWORK OR API ERROR: {e}")
