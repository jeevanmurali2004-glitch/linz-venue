"""
Linz Sports Hall Scraper
Fetches availability from book.venuzle.at and saves to data.json
Run automatically by GitHub Actions every day.
"""

import requests
from bs4 import BeautifulSoup
import json
import time
from datetime import date, timedelta

REGIONS = {
    5: {"name": "Linz-East",  "code": "LO"},
    6: {"name": "Linz-North", "code": "LN"},
    7: {"name": "Linz-South", "code": "LS"},
    8: {"name": "Linz-West",  "code": "LW"},
}

BASE_URL = "https://book.venuzle.at/stadt-linz/venues/c/{region}/{date}/ajax/"
START_DATE = date.today()
END_DATE = START_DATE + timedelta(days=30)  # 30 days ahead
DELAY = 0.4

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "text/html, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://book.venuzle.at/stadt-linz/venues/",
}


def parse_html(html, region_id, date_str):
    soup = BeautifulSoup(html, "html.parser")
    venues = []

    for row in soup.find_all("tr"):
        link = row.find("a", class_="timetable-row-link")
        if not link:
            continue

        href = link.get("href", "")
        parts = href.strip("/").split("/")
        try:
            venue_id = parts[parts.index("v") + 1]
        except (ValueError, IndexError):
            continue

        facility_el = link.find("span", class_="facility_name")
        facility = facility_el.get_text(strip=True) if facility_el else ""
        hall = link.get_text(strip=True).replace(facility, "").strip()

        slots = []
        cursor = 0  # 15-min units from 07:00

        for cell in row.find_all("td", class_="slot"):
            colspan = int(cell.get("colspan", 1))
            classes = " ".join(cell.get("class", []))

            if "noDisplay" in classes and "timeframe" not in classes:
                status = "n"
            elif "free-slot" in classes:
                status = "a"
            elif "blocked-slot" in classes:
                status = "b"
            elif "unavailable-slot" in classes:
                status = "u"
            elif "timeframe" in classes:
                status = "b"
            else:
                status = "n"

            start_min = 7 * 60 + cursor * 15
            end_min = start_min + colspan * 15

            if start_min < 22 * 60 and end_min > 7 * 60:
                slots.append({
                    "start": max(start_min, 7 * 60),
                    "end": min(end_min, 22 * 60),
                    "status": status,
                })

            cursor += colspan

        venues.append({
            "id": venue_id,
            "facility": facility,
            "hall": hall,
            "name": f"{facility} · {hall}" if hall else facility,
            "region": REGIONS[region_id]["code"],
            "date": date_str,
            "slots": slots,
        })

    return venues


def scrape():
    session = requests.Session()
    session.headers.update(HEADERS)

    all_entries = []
    current = START_DATE

    while current <= END_DATE:
        date_str = current.strftime("%Y-%m-%d")
        date_compact = current.strftime("%Y%m%d")

        for region_id, region_info in REGIONS.items():
            url = BASE_URL.format(region=region_id, date=date_compact)
            try:
                resp = session.get(url, timeout=10)
                if resp.status_code == 200:
                    entries = parse_html(resp.text, region_id, date_str)
                    all_entries.extend(entries)
                    print(f"✓ {date_str} {region_info['code']} → {len(entries)} venues")
                else:
                    print(f"✗ {date_str} {region_info['code']} → HTTP {resp.status_code}")
            except Exception as e:
                print(f"✗ {date_str} {region_info['code']} → {e}")

            time.sleep(DELAY)

        current += timedelta(days=1)

    return all_entries


def group_by_venue(entries):
    venues = {}
    for entry in entries:
        key = entry["id"]
        if key not in venues:
            venues[key] = {
                "id": entry["id"],
                "name": entry["name"],
                "facility": entry["facility"],
                "hall": entry["hall"],
                "region": entry["region"],
                "days": [],
            }
        venues[key]["days"].append({
            "date": entry["date"],
            "slots": entry["slots"],
        })

    result = list(venues.values())
    for v in result:
        v["days"].sort(key=lambda d: d["date"])
    result.sort(key=lambda v: (v["region"], v["name"]))
    return result


if __name__ == "__main__":
    print(f"Scraping {START_DATE} → {END_DATE}\n")
    raw = scrape()
    grouped = group_by_venue(raw)
    print(f"\n✓ {len(grouped)} unique venues found")

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump({
            "updated": START_DATE.isoformat(),
            "venues": grouped
        }, f, ensure_ascii=False, indent=2)

    print("✓ Saved to data.json")
