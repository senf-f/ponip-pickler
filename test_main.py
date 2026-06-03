import datetime
import hashlib
import json
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from data import Base, SalesInfo, Nekretnina
from main import (
    hash_data,
    parse_html,
    update_if_changed,
    write_sales_info,
    read_sales_info,
    compare_and_notify_sales,
    send_to_telegram,
    get_html,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# --- hash_data ---

class TestHashData:
    def test_returns_sha256_hex(self):
        data = {"key": "value"}
        result = hash_data(data)
        expected = hashlib.sha256(
            json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        assert result == expected

    def test_same_input_same_hash(self):
        data = {"a": 1, "b": 2}
        assert hash_data(data) == hash_data(data)

    def test_different_key_order_same_hash(self):
        data1 = {"a": 1, "b": 2}
        data2 = {"b": 2, "a": 1}
        assert hash_data(data1) == hash_data(data2)

    def test_different_data_different_hash(self):
        assert hash_data({"a": 1}) != hash_data({"a": 2})

    def test_unicode_characters(self):
        data = {"ključ": "vrijednost", "cijena": "100.000,00 €"}
        result = hash_data(data)
        assert len(result) == 64  # SHA-256 hex length


# --- parse_html ---

SAMPLE_HTML = """
<html>
<body>
<div class="main-container">
  <div role="main">
    <div class="row">
      <div>
        <p class="text-right">ID nadmetanja</p>
        <div>
          <div><p>12345</p></div>
        </div>
      </div>
    </div>
    <div class="row">
      <div>
        <p class="text-right">Datum i vrijeme završetka nadmetanja</p>
        <div>
          <div><p>15.07.2025. 12:00</p></div>
        </div>
      </div>
    </div>
    <div class="row">
      <div>
        <p class="text-right">Trenutačna cijena predmeta prodaje</p>
        <div>
          <div><p id="trenutna-cijena">50.000,00</p></div>
        </div>
      </div>
    </div>
  </div>
</div>
</body>
</html>
"""


class TestParseHtml:
    def test_extracts_key_value_pairs(self):
        html = """
        <div class="main-container">
          <div role="main">
            <div class="row">
              <div>
                <p class="text-right">ID nadmetanja</p>
              </div>
              <div><p>99999</p></div>
            </div>
          </div>
        </div>
        """
        result = parse_html(html)
        assert "ID nadmetanja" in result
        assert result["ID nadmetanja"] == "99999"

    def test_empty_value_becomes_na(self):
        html = """
        <div class="main-container">
          <div role="main">
            <div class="row">
              <div>
                <p class="text-right">Some Field</p>
              </div>
              <div><p>   </p></div>
            </div>
          </div>
        </div>
        """
        result = parse_html(html)
        assert result.get("Some Field") == "N/A"

    def test_returns_dict(self):
        html = """
        <div class="main-container">
          <div role="main">
            <div class="row"></div>
          </div>
        </div>
        """
        result = parse_html(html)
        assert isinstance(result, dict)

    def test_trenutna_cijena_uses_special_selector(self):
        html = """
        <div class="main-container">
          <div role="main">
            <div class="row">
              <div>
                <p class="text-right">Trenutačna cijena something</p>
              </div>
              <div><p>ignored</p></div>
            </div>
            <p id="trenutna-cijena">75.000,00</p>
          </div>
        </div>
        """
        result = parse_html(html)
        assert "75.000,00" in str(result.values())


# --- update_if_changed ---

class TestUpdateIfChanged:
    def test_updates_when_different(self):
        obj = MagicMock()
        obj.name = "old"
        update_if_changed(obj, "name", "new")
        assert obj.name == "new"

    def test_no_update_when_same(self):
        class Obj:
            name = "same"
        o = Obj()
        update_if_changed(o, "name", "same")
        assert o.name == "same"


# --- write_sales_info ---

class TestWriteSalesInfo:
    def _make_data(self, id_val="12345"):
        return {
            "ID nadmetanja": id_val,
            "Trenutačna cijena predmeta prodaje u\xa0nadmetanju": "50.000,00",
            "Trenutačni brojuplatitelja jamčevine": "3",
            "Datum i vrijeme završetka nadmetanja": "15.07.2025. 12:00",
            "status_nadmetanja": "AKTIVNO",
        }

    def test_creates_new_record(self, db_session):
        data = self._make_data()
        write_sales_info(db_session, data, "http://example.com")
        record = db_session.query(SalesInfo).filter_by(id="12345").first()
        assert record is not None
        assert record.url == "http://example.com"
        assert record.data_hash is not None
        assert record.json_data is not None

    def test_updates_existing_record(self, db_session):
        data = self._make_data()
        write_sales_info(db_session, data, "http://example.com")

        # Insert the existing record first so the update path finds it
        existing = db_session.query(SalesInfo).filter_by(id="12345").first()
        assert existing is not None

        data["Trenutačna cijena predmeta prodaje u\xa0nadmetanju"] = "60.000,00"
        write_sales_info(db_session, data, "http://example.com/updated")
        db_session.expire_all()
        updated = db_session.query(SalesInfo).filter_by(id="12345").first()
        assert updated.url == "http://example.com/updated"
        assert updated.iznos_najvise_ponude == "60.000,00"

    def test_sets_status_dovrseno_if_past_date(self, db_session):
        data = self._make_data()
        data["Datum i vrijeme završetka nadmetanja"] = "01.01.2020. 12:00"
        write_sales_info(db_session, data, "http://example.com")

        # Update path
        write_sales_info(db_session, data, "http://example.com")
        db_session.expire_all()
        record = db_session.query(SalesInfo).filter_by(id="12345").first()
        assert record.status_nadmetanja == "DOVRŠENO"

    def test_stores_json_data(self, db_session):
        data = self._make_data()
        write_sales_info(db_session, data, "http://example.com")
        record = db_session.query(SalesInfo).filter_by(id="12345").first()
        stored = json.loads(record.json_data)
        assert stored["ID nadmetanja"] == "12345"


# --- read_sales_info ---

class TestReadSalesInfo:
    def test_returns_none_when_no_nekretnina(self, db_session):
        # Known bug: query starts from Nekretnina table, so without a
        # Nekretnina row, it always returns None even if SalesInfo exists
        data = {
            "ID nadmetanja": "99",
            "Trenutačna cijena predmeta prodaje u\xa0nadmetanju": "10",
            "Trenutačni brojuplatitelja jamčevine": "1",
            "Datum i vrijeme završetka nadmetanja": "01.01.2030. 12:00",
        }
        write_sales_info(db_session, data, "http://example.com")
        result = read_sales_info(db_session, "99")
        # Documents current (buggy) behavior: returns None
        assert result is None

    def test_returns_data_when_nekretnina_exists(self, db_session):
        # If a matching Nekretnina row exists, read_sales_info works
        nekretnina = Nekretnina(
            id=100,
            nadlezno_tijelo="Sud",
            poslovni_broj="PB-1",
            opis="Test",
            vrsta_predmeta="Nekretnina",
            opseg_imovine="Cijela",
            utvrdjena_vrijednost=100000.0,
            broj_drazbe="1",
            datum_odluke=datetime.datetime(2025, 1, 1),
            datum_pocetka=datetime.datetime(2025, 1, 1),
            datum_pocetka_nadmetanja=datetime.datetime(2025, 1, 1),
            datum_zavrsetka_nadmetanja=datetime.datetime(2025, 7, 1),
            min_cijena=50000.0,
            pocetna_cijena=60000.0,
            iznos_drazbenog_koraka=1000.0,
            jamcevina=5000.0,
        )
        db_session.add(nekretnina)
        db_session.commit()

        data = {
            "ID nadmetanja": "100",
            "Trenutačna cijena predmeta prodaje u\xa0nadmetanju": "70.000",
            "Trenutačni brojuplatitelja jamčevine": "2",
            "Datum i vrijeme završetka nadmetanja": "01.07.2025. 12:00",
        }
        write_sales_info(db_session, data, "http://example.com")
        result = read_sales_info(db_session, "100")
        assert result is not None
        assert result["id"] == 100


# --- compare_and_notify_sales ---

class TestCompareAndNotifySales:
    @patch("main.send_to_telegram")
    def test_new_entry_sends_notification(self, mock_telegram, db_session):
        data = {
            "ID nadmetanja": "555",
            "Trenutačna cijena predmeta prodaje u\xa0nadmetanju": "10",
            "Trenutačni brojuplatitelja jamčevine": "1",
            "Datum i vrijeme završetka nadmetanja": "01.01.2030. 12:00",
        }
        compare_and_notify_sales(db_session, data, "http://example.com")
        mock_telegram.assert_called_once()
        assert "New entry" in mock_telegram.call_args[0][0]

    @patch("main.send_to_telegram")
    def test_always_treats_as_new_without_nekretnina(self, mock_telegram, db_session):
        # Documents current bug: without Nekretnina row, every call is "new"
        data = {
            "ID nadmetanja": "555",
            "Trenutačna cijena predmeta prodaje u\xa0nadmetanju": "10",
            "Trenutačni brojuplatitelja jamčevine": "1",
            "Datum i vrijeme završetka nadmetanja": "01.01.2030. 12:00",
        }
        compare_and_notify_sales(db_session, data, "http://example.com")
        compare_and_notify_sales(db_session, data, "http://example.com")
        # Called twice because read_sales_info always returns None
        assert mock_telegram.call_count == 2


# --- send_to_telegram ---

class TestSendToTelegram:
    @patch("main.CONFIG", {"send_to_telegram": "0"})
    def test_does_nothing_when_disabled(self):
        # Should not raise even without creds module
        send_to_telegram("test message")

    @patch("main.CONFIG", {"send_to_telegram": "1"})
    @patch("main.requests.post")
    def test_sends_when_enabled(self, mock_post):
        with patch.dict("sys.modules", {"creds": MagicMock(
            TELEGRAM_API_TOKEN_TECH="token",
            TELEGRAM_CHAT_ID="123"
        )}):
            send_to_telegram("hello")
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args
            assert "hello" in str(call_kwargs)


# --- get_html ---

class TestGetHtml:
    @patch("main.requests.get")
    @patch("main.send_to_telegram")
    def test_returns_html_on_success(self, mock_telegram, mock_get):
        mock_get.return_value = MagicMock(
            text="<html></html>",
            raise_for_status=MagicMock()
        )
        result = get_html("http://example.com")
        assert result == "<html></html>"

    @patch("main.requests.get")
    @patch("main.send_to_telegram")
    def test_raises_on_failure(self, mock_telegram, mock_get):
        from requests.exceptions import ConnectionError
        mock_get.side_effect = ConnectionError("timeout")
        with pytest.raises(ConnectionError):
            get_html("http://example.com")
        mock_telegram.assert_called_once()


# --- configurator ---

class TestConfigurator:
    def test_load_config_returns_dict(self):
        from configurator import load_config
        config = load_config()
        assert isinstance(config, dict)
        assert "log_files" in config
        assert "send_to_telegram" in config
