#!/usr/bin/python3

import csv
import hashlib
import json
from datetime import datetime

import requests
from deepdiff import DeepDiff
from selectolax.parser import HTMLParser

urls = ["https://ponip.fina.hr/ocevidnik-web/predmet_prodaje/035d3e38-bd9e-6bf1-b4ae-0cd6d5eaa5c6",
        "https://ponip.fina.hr/ocevidnik-web/predmet_prodaje/88ab522a-bc31-a67f-349d-e75be1dc9438",
        "https://ponip.fina.hr/ocevidnik-web/predmet_prodaje/01b71115-59b9-da56-4f9e-3e278d882bc0",
        "https://ponip.fina.hr/ocevidnik-web/predmet_prodaje/7203909b-2067-f5eb-97cd-3efeb6944857",
        "https://ponip.fina.hr/ocevidnik-web/predmet_prodaje/035d3e38-bd9e-6bf1-b4ae-0cd6d5eaa5c6",
        "https://ponip.fina.hr/ocevidnik-web/predmet_prodaje/3f6d7273-81ed-d773-8cac-1dcddcbcc595",
        "https://ponip.fina.hr/ocevidnik-web/predmet_prodaje/cf97100c-4244-7eb8-eca9-022bb82a949f"]
directory_base = "/opt/ponip_pickler/"
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
        # 'Ostali uvjeti prodaje' su u divu umjesto u p :(
        if vrijednost.text(strip=True) == "Ostali uvjeti prodaje":
            ostali_uvjeti = vrijednost.parent.parent.css("div:nth-child(2)")
            data[f"{vrijednost.text(strip=True)}"] = ostali_uvjeti[0].text(strip=True)
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

    return data


def hash_data(json_input):
    return hashlib.sha256(json.dumps(json_input, ensure_ascii=False).encode('utf-8')).hexdigest()


def compare_hashes(hash_new, hash_old):
    return DeepDiff(hash_new, hash_old)


def send_to_telegram(content):
    import creds

    api_token = creds.TELEGRAM_API_TOKEN_TECH
    chat_id = creds.TELEGRAM_CHAT_ID
    api_url = f"https://api.telegram.org/bot{api_token}/sendMessage"

    try:
        requests.post(api_url, json={'chat_id': chat_id, 'text': content})
    except Exception as e:
        print(e)


def main():
    for url in urls:
        raw = get_html(url)
        html = HTMLParser(raw)

        postojeci_podaci = read_from_csv(csv_file=f"{CSV_FILE_NAME}.csv")
        novi_podaci = parse_html(html)

        for i in range(0, len(postojeci_podaci) - 1):
            if bool(novi_podaci):
                if novi_podaci["ID nadmetanja"] in postojeci_podaci[i]:
                    # Vrati originalni dictionary
                    originalni_dict = unpack_csv_row(csv_file=f"{CSV_FILE_NAME}.csv",
                                                     id_nadmetanja=novi_podaci["ID nadmetanja"])
                    if bool(compare_hashes(hash_new=novi_podaci, hash_old=originalni_dict)):
                        send_to_telegram(
                            f"Promjene na promatranoj nekretnini:\n\n{compare_hashes(novi_podaci, originalni_dict)}")
                        print(f"Sent smt to telegram, {datetime.today()}")

        write_to_csv(novi_podaci, id_nad=novi_podaci["ID nadmetanja"])


if __name__ == '__main__':
    main()
    print(f"Program executed, {datetime.today()}.")
