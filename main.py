#!/usr/bin/python3

import csv
import hashlib
import json
import os
import sys
import traceback
from datetime import datetime

import requests
from deepdiff import DeepDiff
from selectolax.parser import HTMLParser

urls = ["https://ponip.fina.hr/ocevidnik-web/predmet_prodaje/035d3e38-bd9e-6bf1-b4ae-0cd6d5eaa5c6",
        "https://ponip.fina.hr/ocevidnik-web/predmet_prodaje/7203909b-2067-f5eb-97cd-3efeb6944857",
        "https://ponip.fina.hr/ocevidnik-web/predmet_prodaje/035d3e38-bd9e-6bf1-b4ae-0cd6d5eaa5c6",
        "https://ponip.fina.hr/ocevidnik-web/predmet_prodaje/3f6d7273-81ed-d773-8cac-1dcddcbcc595",
        "https://ponip.fina.hr/ocevidnik-web/predmet_prodaje/cf97100c-4244-7eb8-eca9-022bb82a949f",
        "https://ponip.fina.hr/ocevidnik-web/predmet_prodaje/9ed6c068-c2cd-8ae1-2af9-f7280e9d91df",
        "https://ponip.fina.hr/ocevidnik-web/predmet_prodaje/fade13f5-df9e-ad6d-0837-5ea6fbbd192c",
        "https://ponip.fina.hr/ocevidnik-web/predmet_prodaje/85127244-04e7-3e8b-52cf-fa1596024337",
        "https://ponip.fina.hr/ocevidnik-web/predmet_prodaje/89453c2e-7d2f-a390-50ec-672a4a1ffeb3",
        "https://ponip.fina.hr/ocevidnik-web/predmet_prodaje/65d00642-341d-eb49-351d-afa85508466b", 
        "https://ponip.fina.hr/ocevidnik-web/predmet_prodaje/8b51d74a-2f2f-9289-6d7f-1afeed18f60a",
        "https://ponip.fina.hr/ocevidnik-web/predmet_prodaje/0647ff73-54a0-5d9d-e5c5-4bff327566b9",
        "https://ponip.fina.hr/ocevidnik-web/predmet_prodaje/ba6180cb-df26-45db-e8e4-109ca63267c4"]
directory_base = ""  #"/opt/ponip_pickler/"
DODANE_INFORMACIJE = ["Datum", "Hash", "ID"]
CSV_FILE_NAME = f"ponip_pickles"


def write_to_csv(data, id_nad=""):
    data_hash = hash_data(data)
    csv_file_path = f"{directory_base}{CSV_FILE_NAME}_{id_nad}.csv"
    with open(csv_file_path, 'w+', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=list(data.keys()) + DODANE_INFORMACIJE)
        if file.tell() == 0:
            writer.writeheader()
        writer.writerow(
            {**data, "Datum": datetime.today().date(), "Hash": data_hash, "ID": data["ID nadmetanja"]})


def read_from_csv(csv_file):
    with open(f"{directory_base}{csv_file}", encoding="utf-8") as f:
        zapisi = f.read().splitlines()
    return zapisi


def unpack_csv_row(csv_file, id_nadmetanja):
    with open(f"{directory_base}{csv_file}", "r", encoding="utf-8") as f:

        reader = csv.DictReader(f)
        keys_list = [key for key in reader.fieldnames if key not in DODANE_INFORMACIJE]
        original_dict = None

        for row in reader:
            # noinspection PyTypeChecker
            if row["ID"] == id_nadmetanja:
                original_dict = {key: row[key] for key in keys_list}

        return original_dict


def get_html(url):
    r = requests.get(url)
    return r.text


def parse_html(html_input):
    data = {}
    vrijednosti_lijevo = html_input.css(".main-container [role='main'] .row div p.text-right")
    for vrijednost in vrijednosti_lijevo:
        podaci_desno = vrijednost.parent.parent.css("div:nth-child(2) > p")
        for podatak in podaci_desno:
            if podatak.text(strip=True) == "":
                data[f"{vrijednost.text(strip=True)}"] = "N/A"
            else:
                # 'Napomena' se pojavljuje dvaput FIXME: dvaput se upise tekst iz druge napomene
                if vrijednost.text(strip=True) == "Napomena":
                    if "Napomena" not in data:
                        data["Napomena"] = podatak.text(strip=True)
                    else:
                        # data["Napomena 2"] = podatak.text(strip=True)
                        pass
                data[f"{vrijednost.text(strip=True)}"] = podatak.text(strip=True)

        # 'Ostali uvjeti prodaje' su u divu umjesto u p :(
        if vrijednost.text(strip=True) == "Ostali uvjeti prodaje":
            ostali_uvjeti = vrijednost.parent.parent.css("div:nth-child(2)")
            data[f"{vrijednost.text(strip=True)}"] = ostali_uvjeti[0].text(strip=True)
        if vrijednost.text(strip=True) == "Trenutačna cijena predmeta prodaje u nadmetanju":
            trenutacna_cijena = vrijednost.parent.parent.css("p#trenutna-cijena")
            data[f"{vrijednost.text(strip=True)}"] = trenutacna_cijena[0].text(strip=True)
        if vrijednost.text(strip=True) == "Iznos najviše ponude u nadmetanju":
            trenutacna_cijena = vrijednost.parent.parent.css("p#trenutna-cijena")
            data[f"{vrijednost.text(strip=True)}"] = trenutacna_cijena[0].text(strip=True)

    return data


def hash_data(json_input):
    return hashlib.sha256(json.dumps(json_input, ensure_ascii=False).encode('utf-8')).hexdigest()


def compare_hashes(hash_new, hash_old):
    return DeepDiff(t1=hash_new, t2=hash_old)


def send_to_telegram(content):
    import creds

    api_token = creds.TELEGRAM_API_TOKEN_TECH
    chat_id = creds.TELEGRAM_CHAT_ID
    api_url = f"https://api.telegram.org/bot{api_token}/sendMessage"

    try:
        requests.post(api_url, json={'chat_id': chat_id, 'text': content})
    except Exception as exception:
        print(exception)


def main():
    for url in urls:
        raw = get_html(url)
        html = HTMLParser(raw)

        novi_podaci = parse_html(html)
        if "ID nadmetanja" in novi_podaci:
            current_id = novi_podaci["ID nadmetanja"]
        else:
            print("ID nadmetanja nije pronađen. Moguće da je url uklonjen?")

        # check if file exists:
        if os.path.isfile(f"{CSV_FILE_NAME}_{current_id}.csv"):
            # compare data
            postojeci_podaci = read_from_csv(csv_file=f"{CSV_FILE_NAME}_{current_id}.csv")
            if bool(novi_podaci):
                if current_id in postojeci_podaci[1]:
                    # Vrati originalni dictionary
                    originalni_dict = unpack_csv_row(csv_file=f"{CSV_FILE_NAME}_{current_id}.csv",
                                                     id_nadmetanja=current_id)
                    changes = compare_hashes(hash_new=novi_podaci, hash_old=originalni_dict)
                    if bool(changes):
                        send_to_telegram(
                            f"Promjene na promatranoj nekretnini (ID {current_id}):\n\n{changes}")
                        print(f"Sent changes in {current_id} to telegram, {datetime.today()}")
        else:
            send_to_telegram(f"New file added: {current_id}")

        write_to_csv(novi_podaci, id_nad=current_id)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(e.args)
        send_to_telegram(f">>> ERROR: {e.args}")
    finally:
        print(f"Program executed, {datetime.today()}.")
