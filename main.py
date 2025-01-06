#!/usr/bin/python3

import hashlib
import json
import logging

import requests
from deepdiff import DeepDiff
from selectolax.parser import HTMLParser

from config import engine, SessionLocal
from data import Base
from data import SalesInfo
from urls import urls

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


def initialize_database():
    logging.info("Initializing database...")
    Base.metadata.create_all(engine, checkfirst=True)
    logging.info("Database initialized.")


def hash_data(json_input):
    return hashlib.sha256(json.dumps(json_input, ensure_ascii=False).encode('utf-8')).hexdigest()


def get_html(url):
    """Fetch the HTML content from a URL."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except requests.RequestException as err:
        logging.error(f"Failed to fetch URL {url}: {err}")
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
    except Exception as err:
        logging.error(f"Failed to parse HTML: {err}")
        raise


def write_sales_info(session, data):
    """Write or update sales info in the database."""
    data_hash = hash_data(data)  # Generate hash for the JSON data
    json_data = json.dumps(data, ensure_ascii=False)  # Serialize the JSON data

    # Check if the record already exists
    existing_record = session.query(SalesInfo).filter_by(id=data["ID nadmetanja"]).first()

    if existing_record:
        # Update existing record
        existing_record.iznos_najvise_ponude = data.get("iznos_najvise_ponude")
        existing_record.status_nadmetanja = data.get("status_nadmetanja", "UNKNOWN")
        existing_record.broj_uplatitelja = data.get("broj_uplatitelja")
        existing_record.data_hash = data_hash
        existing_record.json_data = json_data
        logging.info(f"Updated sales info for ID {data['ID nadmetanja']}.")
        try:
            session.commit()  # Add this line to persist changes
        except Exception as err:
            session.rollback()
            logging.error(f"Failed to commit transaction: {err}")
            raise
    else:
        # Add a new record
        new_record = SalesInfo(
            id=data["ID nadmetanja"],
            iznos_najvise_ponude=data.get("iznos_najvise_ponude"),
            broj_uplatitelja=data.get("broj_uplatitelja"),
            data_hash=data_hash,
            json_data=json_data
        )
        try:
            session.add(new_record)
            session.commit()
            logging.info(f"Added new sales info for ID {data['ID nadmetanja']}.")
        except Exception as err:
            session.rollback()
            logging.error(f"Failed to commit transaction: {err}")
            raise


def read_sales_info(session, id_nadmetanja):
    """Retrieve sales info from the database."""
    record = session.query(SalesInfo).filter_by(id=id_nadmetanja).first()
    if record:
        return {
            "id": record.id,
            "iznos_najvise_ponude": record.iznos_najvise_ponude,
            "status_nadmetanja": record.status_nadmetanja,
            "broj_uplatitelja": record.broj_uplatitelja,
            "data_hash": record.data_hash,
            "json_data": json.loads(record.json_data)  # Deserialize the JSON
        }
    return None


def compare_and_notify_sales(session, new_data):
    """Compare new sales data with existing records and notify changes."""
    existing_data = read_sales_info(session, new_data["ID nadmetanja"])
    if existing_data:
        # Compare hashes to detect changes
        if existing_data["data_hash"] != hash_data(new_data):
            changes = DeepDiff(existing_data["json_data"], new_data)
            send_to_telegram(f"Changes detected for ID {new_data['ID nadmetanja']}:\n{changes}")
            logging.info(f"Changes detected and notified for ID {new_data['ID nadmetanja']}.")
            write_sales_info(session, new_data)
        else:
            logging.info(f"No changes detected for ID {new_data['ID nadmetanja']}.")
    else:
        send_to_telegram(f"New entry detected: ID {new_data['ID nadmetanja']}")
        logging.info(f"New sales info added for ID {new_data['ID nadmetanja']}.")
        write_sales_info(session, new_data)


def process_urls(session):
    """Process all URLs and handle their data."""
    for url in urls:
        logging.info(f"Processing URL: {url}")
        try:
            # Fetch and parse the HTML data
            raw_html = get_html(url)
            data = parse_html(raw_html)

            # Log parsed data for debugging
            logging.debug(f"Parsed data: {data}")

            if "ID nadmetanja" not in data:
                logging.warning(f"No 'ID nadmetanja' found for URL: {url}. Skipping.")
                continue

            # Compare the new data with existing data in the database
            compare_and_notify_sales(session, data)

        except Exception as err:
            logging.error(f"Error processing URL {url}: {err}")


def main():
    """Main entry point for the pickler app."""
    logging.info("Starting Ponip Pickler...")

    # Create a database session
    session = SessionLocal()

    try:
        process_urls(session)
    except Exception as err:
        logging.error(f"Unhandled exception: {err}")
    finally:
        session.close()
        logging.info("Database session closed.")
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
    except Exception as err:
        logging.error(f"Failed to send Telegram message: {err}")


if __name__ == '__main__':
    try:
        initialize_database()
        main()
    except Exception as e:
        logging.error(f"Unhandled exception: {e}")
