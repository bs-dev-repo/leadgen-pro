# LeadGen Pro 🔍

A **free, full-stack lead generation tool** that scrapes Google Maps, extracts emails from business websites, and exports to Excel. No paid APIs required.

---

## Features

| Feature | Description |
|---------|-------------|
| 🗺️ Google Maps Scraper | Search businesses by keyword + location |
| 📧 Email Extractor | Auto-crawls websites for contact emails |
| 📊 Excel / CSV Export | One-click download of all results |
| ★ Bookmarks | Save promising leads |
| 📜 Search History | Re-open any previous search |
| ⬆ Import | Upload CSV/Excel of websites to extract emails |
| 🔢 Pagination | 25 per page with full controls |
| 🔍 Filter | Live search/filter across results |
| 🔁 Duplicate Detection | Prevents storing duplicate leads |

---

## Tech Stack

- **Backend**: Python + FastAPI
- **Scraping**: Playwright (Google Maps) + BeautifulSoup (email extraction)
- **Database**: SQLite
- **Data Export**: Pandas + openpyxl
- **Frontend**: HTML + CSS + Vanilla JavaScript
- **Deployment**: Render / Replit / Any VPS

---

## Project Structure

```
leadgen/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI routes + app
│   ├── scraper.py       # Google Maps Playwright scraper
│   ├── email_extractor.py # Website email crawler
│   └── database.py      # SQLite setup
├── templates/
│   ├── index.html       # Dashboard / Search page
│   ├── results.html     # Results + export
│   ├── bookmarks.html   # Saved leads
│   ├── history.html     # Search history
│   └── import.html      # CSV/Excel import
├── static/
│   ├── style.css        # Dark industrial UI
│   └── script.js        # Shared utilities
├── requirements.txt
├── render.yaml          # Render deployment config
├── .replit              # Replit deployment config
├── run.py               # Local run entrypoint
└── README.md
```

---

## Local Setup

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/leadgen-pro.git
cd leadgen-pro

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Install Playwright browser

```bash
playwright install chromium
playwright install-deps chromium  # Linux only
```

### 3. Run the server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 10000 --reload
```

Open: http://localhost:10000

---

## Deploy on Render (Free)

1. Push code to GitHub
2. Go to [render.com](https://render.com) → New → Web Service
3. Connect your GitHub repo
4. Render auto-detects `render.yaml` settings
5. **Build command**: `pip install -r requirements.txt && playwright install chromium && playwright install-deps chromium`
6. **Start command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
7. Click **Deploy**

> ⚠️ Free tier sleeps after 15 min of inactivity. First request may take ~30s.

---

## Deploy on Replit (Free)

1. Go to [replit.com](https://replit.com) → New Repl → Import from GitHub
2. Paste your GitHub repo URL
3. Click **Run** — Replit uses `.replit` config automatically
4. The app will install deps and start on port 8080

---

## Deploy on Railway (Free)

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and deploy
railway login
railway init
railway up
```

Set these env vars in Railway dashboard:
- `PORT` = `10000`

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/search` | Start Google Maps scrape |
| GET | `/api/search/status` | Scraper progress |
| POST | `/api/search/stop` | Stop scraper |
| GET | `/api/results` | Paginated results |
| POST | `/api/bookmark` | Toggle bookmark |
| GET | `/api/download` | Export Excel |
| GET | `/api/download/csv` | Export CSV |
| GET | `/api/history` | Search history |
| DELETE | `/api/history/{id}` | Delete search |
| POST | `/api/import` | Upload CSV/Excel |

---

## Usage

### Search for Leads
1. Enter keyword (e.g. `dentist`) and location (e.g. `Delhi`)
2. Set max results (5–200)
3. Click **SEARCH NOW**
4. Watch real-time progress
5. Auto-redirects to results when done

### Import Websites
1. Create a CSV/Excel with column header `website`
2. Go to **Import** page
3. Upload the file
4. System extracts emails from each site

### Export Results
From the Results page, click:
- **↓ CSV** — Download current search as CSV
- **↓ Excel** — Download current search as Excel
- **↓ All** — Download all leads as Excel

---

## Notes

- Google Maps scraping may be rate-limited. The tool adds random delays to mimic human behavior.
- If Playwright is unavailable, the system falls back to **mock data** for demo purposes.
- Email extraction crawls up to 5 pages per website (/, /contact, /about, etc.)
- Duplicate detection uses phone number, website URL, and name+address combinations.

---

## License

MIT — Free to use, modify, and deploy.
