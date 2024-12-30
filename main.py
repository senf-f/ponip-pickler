#!/usr/bin/python3

import csv
import hashlib
import json
import logging
import os
import traceback
from datetime import datetime

import requests
from deepdiff import DeepDiff
from selectolax.parser import HTMLParser
from config import urls

CWD = "/opt/ponip/pickler/"
DODANE_INFORMACIJE = ["Datum", "Hash", "ID"]
CSV_FILE_NAME = "ponip_pickles"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"{CWD}ponip_pickled.log"),
        logging.FileHandler("/var/log/scrapers/ponip_pickle_log.txt"),
        logging.StreamHandler()
    ]
)

# Utility function for hashing
def hash_data(json_input):
    return hashlib.sha256(json.dumps(json_input, ensure_ascii=False).encode('utf-8')).hexdigest()


# Refactored functions

def get_html(url):
    """Fetch the HTML content from a URL."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logging.error(f"Failed to fetch URL {url}: {e}")
        raise


def parse_html(html_input):
    """Parse HTML content and extract data."""
    data = {}
    html = HTMLParser(html_input)
    try:
        vrijednosti_lijevo = html.css(".main-container [role='main'] .row div p.text-right")
        for vrijednost in vrijednosti_lijevo:
            podaci_desno = vrijednost.parent.parent.css("div:nth-child(2) > p")
            for podatak in podaci_desno:
                key = vrijednost.text(strip=True)
                value = podatak.text(strip=True) if podatak.text(strip=True) else "N/A"
                data[key] = value

        return data
    except Exception as e:
        logging.error(f"Failed to parse HTML: {e}")
        raise


def unpack_csv_row(csv_file, id_nadmetanja):
    """Retrieve the original dictionary for a given ID from the CSV file."""
    try:
        with open(csv_file, "r", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            keys_list = [key for key in reader.fieldnames if key not in DODANE_INFORMACIJE]
            for row in reader:
                if row["ID"] == id_nadmetanja:
                    # Return only the original fields, excluding metadata
                    return {key: row[key] for key in keys_list}
    except FileNotFoundError:
        logging.error(f"File {csv_file} not found.")
    except Exception as e:
        logging.error(f"Error unpacking row from {csv_file}: {e}")
    return None


def compare_and_notify(new_data, id_nadmetanja):
    """Compare new data with existing data and notify changes."""
    csv_file = f"{CWD}{CSV_FILE_NAME}_{id_nadmetanja}.csv"

    if os.path.isfile(csv_file):
        logging.info(f"Existing file found for ID {id_nadmetanja}. Comparing data...")
        existing_data = unpack_csv_row(csv_file, id_nadmetanja)
        if not existing_data:
            logging.warning(f"Empty or invalid data in {csv_file}.")
            return

        changes = DeepDiff(existing_data, new_data)
        if changes:
            send_to_telegram(f"Changes detected for ID {id_nadmetanja}:\n{changes}")
            logging.info(f"Changes sent to Telegram for ID {id_nadmetanja}.")
        else:
            logging.info(f"No changes detected for ID {id_nadmetanja}.")
    else:
        logging.info(f"No existing file for ID {id_nadmetanja}. Writing new data.")
        send_to_telegram(f"New entry detected: ID {id_nadmetanja}")


def write_new_record(data, id_nadmetanja):
    """Write new data to a CSV file."""
    try:
        csv_file = f"{CWD}{CSV_FILE_NAME}_{id_nadmetanja}.csv"
        data_hash = hash_data(data)
        with open(csv_file, 'w+', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=list(data.keys()) + DODANE_INFORMACIJE)
            if file.tell() == 0:
                writer.writeheader()
            writer.writerow(
                {**data, "Datum": datetime.today().date(), "Hash": data_hash, "ID": id_nadmetanja}
            )
        logging.info(f"Data for ID {id_nadmetanja} written to {csv_file}.")
    except Exception as e:
        logging.error(f"Failed to write record for ID {id_nadmetanja}: {e}")
        raise


def process_url(url):
    """Process a single URL."""
    try:
        raw_html = get_html(url)
        data = parse_html(raw_html)

        if "ID nadmetanja" not in data:
            logging.warning(f"ID nadmetanja not found for URL {url}. Skipping.")
            return

        id_nadmetanja = data["ID nadmetanja"]
        compare_and_notify(data, id_nadmetanja)
        write_new_record(data, id_nadmetanja)
    except Exception as e:
        logging.error(f"Error processing URL {url}: {traceback.format_exc()}")


# Main function

def main():
    """Main script entry point."""
    logging.info("Starting Ponip Pickler...")
    for url in urls:
        process_url(url)
    logging.info("Ponip Pickler finished execution.")


# Telegram integration
def send_to_telegram(content):
    """Send a message to Telegram."""
    import creds
    api_token = creds.TELEGRAM_API_TOKEN_TECH
    chat_id = creds.TELEGRAM_CHAT_ID
    api_url = f"https://api.telegram.org/bot{api_token}/sendMessage"

    try:
        requests.post(api_url, json={'chat_id': chat_id, 'text': content})
        logging.info("Message sent to Telegram.")
    except Exception as e:
        logging.error(f"Failed to send Telegram message: {e}")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logging.error(f"Unhandled exception: {traceback.format_exc()}")
