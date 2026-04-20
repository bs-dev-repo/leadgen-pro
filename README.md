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



## Notes

- Google Maps scraping may be rate-limited. The tool adds random delays to mimic human behavior.
- If Playwright is unavailable, the system falls back to **mock data** for demo purposes.
- Email extraction crawls up to 5 pages per website (/, /contact, /about, etc.)
- Duplicate detection uses phone number, website URL, and name+address combinations.

---

## License

MIT — Free to use, modify, and deploy.
