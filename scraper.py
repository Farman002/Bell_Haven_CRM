
import requests
import pandas as pd
import json
import re
import os

from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://analyst-assessment-production.up.railway.app"
DIRECTORY_URL = f"{BASE_URL}/communities"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

OUTPUT_DIR = "data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

session = requests.Session()
session.headers.update(HEADERS)


def get_soup(url):
    response = session.get(url, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def extract_facility_links():

    links = {}

    # Check homepage for newly announced facilities
    homepage = get_soup(BASE_URL)

    for a in homepage.find_all("a", href=True):
        href = a["href"]

        if "/communities/" in href and href != "/communities":
            links[urljoin(BASE_URL, href)] = a.get_text(" ", strip=True)

    # Scrape all directory pages
    for page in range(1, 11):

        url = DIRECTORY_URL if page == 1 else f"{DIRECTORY_URL}?page={page}"

        soup = get_soup(url)

        page_links = []

        for a in soup.find_all("a", href=True):

            href = a["href"]

            if "/communities/" in href and href != "/communities":
                full_url = urljoin(BASE_URL, href)

                name = a.get_text(" ", strip=True)

                links[full_url] = name
                page_links.append(full_url)

        print(f"Directory page {page}: {len(page_links)} facilities")

        if not page_links:
            break

    return links


def extract_facility_details(url):

    soup = get_soup(url)

    text = list(soup.stripped_strings)

    h1 = soup.find("h1")
    name = h1.get_text(" ", strip=True) if h1 else ""

    def get_section(label, stop_labels):

        try:
            index = text.index(label)

            values = []

            for item in text[index + 1:]:

                if item in stop_labels:
                    break

                values.append(item)

            return values

        except ValueError:
            return []

    address_lines = get_section(
        "Address",
        ["Care Offerings", "Administrator", "Phone"]
    )

    care_lines = get_section(
        "Care Offerings",
        ["Administrator", "Phone"]
    )

    street = address_lines[0] if address_lines else ""

    city_state_zip = " ".join(address_lines[1:])

    match = re.search(
        r"^(.*?),\s*([A-Z]{2})\s+(\d{5})(?:-\d{4})?$",
        city_state_zip
    )

    city = ""
    state = ""
    zip_code = ""

    if match:

        city = match.group(1).strip()
        state = match.group(2)
        zip_code = match.group(3)

    return {
        "name": name,
        "address": street,
        "city": city,
        "state": state,
        "zip": zip_code,
        "care_offerings": " | ".join(care_lines),
        "source_url": url
    }


def scrape_all_facilities():

    links = extract_facility_links()

    facilities = []

    print("\nExtracting facility details...\n")

    for url in links:

        try:

            facility = extract_facility_details(url)

            if facility["name"]:

                facilities.append(facility)

                print(
                    f"Extracted: {facility['name']} | "
                    f"{facility['city']}, {facility['state']}"
                )

        except Exception as e:

            print(f"Failed: {url} | {e}")

    df = pd.DataFrame(facilities)

    # Remove duplicate URLs
    df = df.drop_duplicates(subset=["source_url"])

    df.to_csv(
        f"{OUTPUT_DIR}/bellhaven_facilities.csv",
        index=False
    )

    with open(
        f"{OUTPUT_DIR}/bellhaven_facilities.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            facilities,
            f,
            indent=4,
            ensure_ascii=False
        )

    print("\n========== SCRAPING SUMMARY ==========")
    print("Facilities discovered:", len(links))
    print("Facilities extracted:", len(df))
    print(
        "Missing ZIP codes:",
        df["zip"].eq("").sum()
    )
    print(
        "Missing addresses:",
        df["address"].eq("").sum()
    )

    print("\nFiles saved:")
    print("data/bellhaven_facilities.csv")
    print("data/bellhaven_facilities.json")

    return df


if __name__ == "__main__":
    scrape_all_facilities()
