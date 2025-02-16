#!/usr/bin/python3
import datetime
import hashlib
import json
import logging

import requests
from deepdiff import DeepDiff
from selectolax.parser import HTMLParser

from config import engine, SessionLocal
from configurator import load_config
from data import Base, SalesInfo, Nekretnina
from urls import urls

CONFIG = load_config()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding="UTF-8",
    handlers=[
        logging.FileHandler(CONFIG["log_files"]),
        logging.StreamHandler()
    ]
)


def initialize_database():
    logging.info("Initializing database...")
    Base.metadata.create_all(engine, checkfirst=True)
    logging.info(f"Database initialized. Time: {datetime.datetime.now()}")


def hash_data(json_input):
    json_string = json.dumps(json_input, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(json_string.encode('utf-8')).hexdigest()


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
                if key.startswith("Trenutačna cijena"):
                    value = html.css_first("#trenutna-cijena").text(strip=True)
                else:
                    value = podatak.text(strip=True) if podatak.text(strip=True) else "N/A"
                data[key] = value
        return data
    except Exception as err:
        logging.error(f"Failed to parse HTML: {err}")
        raise


def update_if_changed(obj, attr, value):
    if getattr(obj, attr) != value:
        setattr(obj, attr, value)


def commit_session(session):
    try:
        session.commit()
    except Exception as err:
        session.rollback()
        logging.error(f"Failed to commit transaction: {err}")
        raise


def write_sales_info(session, data):
    """Write or update sales info in the database."""
    data_hash = hash_data(data)  # Generate hash for the JSON data
    json_data = json.dumps(data, ensure_ascii=False)  # Serialize the JSON data

    # Check if the record already exists
    existing_record = session.query(SalesInfo).filter_by(id=data["ID nadmetanja"]).first()

    if existing_record:
        trenutna_cijena_key = 'Trenutačna cijena predmeta prodaje u\xa0nadmetanju'
        logging.debug(f"Updating existing record for ID {data['ID nadmetanja']}.")
        existing_record.iznos_najvise_ponude = data.get(trenutna_cijena_key, existing_record.iznos_najvise_ponude)
        auction_date = datetime.datetime.strptime(data.get('Datum i vrijeme završetka nadmetanja').split(' ')[0],
                                                  "%d.%m.%Y.")
        if auction_date.date() < datetime.datetime.today().date():
            existing_record.status_nadmetanja = "DOVRŠENO"
        else:
            existing_record.status_nadmetanja = data.get("status_nadmetanja", "-")
        existing_record.broj_uplatitelja = data.get("Trenutačni brojuplatitelja jamčevine",
                                                    existing_record.broj_uplatitelja)
        existing_record.data_hash = data_hash
        existing_record.json_data = json_data
        logging.info(f"Updated sales info for ID {data['ID nadmetanja']}.")

    else:
        logging.debug(f"Creating new record for ID {data['ID nadmetanja']}.")
        new_record = SalesInfo(
            id=data["ID nadmetanja"],
            iznos_najvise_ponude=data.get("iznos_najvise_ponude"),
            broj_uplatitelja=data.get("broj_uplatitelja"),
            data_hash=data_hash,
            json_data=json_data
        )
        session.add(new_record)

    commit_session(session)
    session.refresh(existing_record)


def read_sales_info(session, id_nadmetanja):
    """Retrieve sales info from the database."""
    record = session.query(
        Nekretnina.id,
        SalesInfo.iznos_najvise_ponude,
        SalesInfo.status_nadmetanja,
        SalesInfo.broj_uplatitelja,
        SalesInfo.data_hash,
        SalesInfo.json_data
    ).outerjoin(SalesInfo, Nekretnina.id == SalesInfo.id).filter_by(id=id_nadmetanja).first()
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
            changes = DeepDiff(existing_data["json_data"], new_data, verbose_level=1)
            send_to_telegram(f"Changes detected for ID {new_data['ID nadmetanja']}:\n{changes.pretty()}")
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
            raw_html = get_html(url)
            data = parse_html(raw_html)

            logging.debug(f"Parsed data: {data}")

            if "ID nadmetanja" not in data:
                logging.warning(f"No 'ID nadmetanja' found for URL: {url}. Skipping.")
                send_to_telegram(f"No 'ID nadmetanja' found for URL: {url}. Skipping.")
                continue

            compare_and_notify_sales(session, data)

        except Exception as err:
            logging.error(f"Error processing URL {url}: {err}")
            send_to_telegram(f"Error processing URL {url}: {err}. \nMaybe the case is closed?")


def main():
    """Main entry point for the pickler app."""
    logging.info("Starting Ponip Pickler...")
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
    ponip_url = "https://ponip.fina.hr/ocevidnik-web/pretrazivanje/nekretnina"

    if CONFIG["send_to_telegram"] == "1":
        try:
            requests.post(api_url, json={'chat_id': chat_id, 'text': f"{content}\n{ponip_url}"})
            logging.info("Message sent to Telegram.")
        except Exception as err:
            logging.error(f"Failed to send Telegram message: {err}")


if __name__ == '__main__':
    try:
        initialize_database()
        main()
    except Exception as e:
        logging.error(f"Unhandled exception: {e}")
