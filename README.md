# Ponip Pickler

Monitors auction listings on [ponip.fina.hr](https://ponip.fina.hr/ocevidnik-web/pretrazivanje/nekretnina) for changes (price, bidder count, status) and sends Telegram notifications when something changes.

## Local Development (Windows)

```bash
git clone git@github.com:senf-f/ponip-pickler.git
cd ponip-pickler
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

A `config.dev.json` overrides `config.json` on Windows automatically:

```json
{
  "send_to_telegram": "0",
  "log_files": "ponip_pickle_log.txt"
}
```

Run:

```bash
python main.py
```

## VPS Setup (Ubuntu/Debian)

### 1. Install dependencies

```bash
sudo apt update && sudo apt install -y python3 python3-pip python3-venv git
```

### 2. Clone and set up

```bash
cd /opt
sudo git clone git@github.com:senf-f/ponip-pickler.git
cd ponip-pickler
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Create the log directory

```bash
sudo mkdir -p /var/log/scrapers
sudo chown $USER:$USER /var/log/scrapers
```

### 4. Configure environment

Create `.env`:

```bash
cat > .env << 'EOF'
ENVIRONMENT=production
DATABASE_URL=postgresql://user:password@localhost:5432/ponip_pickler
EOF
```

For SQLite instead of PostgreSQL, use `ENVIRONMENT=development` (no DATABASE_URL needed).

### 5. Create `creds.py`

```bash
cat > creds.py << 'EOF'
TELEGRAM_API_TOKEN_TECH = "your-bot-token-here"
TELEGRAM_CHAT_ID = "your-chat-id-here"
EOF
```

### 6. (Optional) Set up PostgreSQL

```bash
sudo apt install -y postgresql
sudo -u postgres createuser ponip
sudo -u postgres createdb ponip_pickler -O ponip
sudo -u postgres psql -c "ALTER USER ponip PASSWORD 'your-password';"
```

Update DATABASE_URL in `.env` to match.

### 7. Test manually

```bash
source .venv/bin/activate
python3 main.py
```

### 8. Set up cron job

```bash
crontab -e
```

Add (runs every 30 minutes):

```
*/30 * * * * cd /opt/ponip-pickler && .venv/bin/python main.py >> /var/log/scrapers/cron.log 2>&1
```

## Running Tests

```bash
pip install pytest
pytest test_main.py -v
```

## Configuration

| File | Purpose |
|------|---------|
| `config.json` | Base config (production defaults) |
| `config.dev.json` | Local overrides (auto-loaded on Windows) |
| `.env` | Database URL and environment |
| `creds.py` | Telegram bot token and chat ID |

## Adding URLs to Monitor

Add auction URLs to `urls.py`:

```python
urls = [
    "https://ponip.fina.hr/ocevidnik-web/predmet_prodaje/<uuid>",
    ...
]
```
