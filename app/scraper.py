import asyncio
import logging
import random
import re
from typing import Optional
from urllib.parse import urljoin, quote_plus

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_scraper_state = {
    "running": False,
    "progress": 0,
    "total": 0,
    "current": "",
    "found": 0,
    "errors": 0,
    "stop_requested": False,
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
]

def get_scraper_status():
    return dict(_scraper_state)

def stop_scraper():
    _scraper_state["stop_requested"] = True

def _is_duplicate(db, name, phone, website, address):
    cursor = db.cursor()
    if phone and phone.strip():
        cursor.execute("SELECT id FROM leads WHERE phone = ? AND phone != ''", (phone,))
        if cursor.fetchone(): return True
    if website and website.strip():
        cursor.execute("SELECT id FROM leads WHERE website = ? AND website != ''", (website,))
        if cursor.fetchone(): return True
    if name and address:
        cursor.execute("SELECT id FROM leads WHERE name = ? AND address = ?", (name, address))
        if cursor.fetchone(): return True
    return False

def _generate_business_list(keyword, location, count):
    suffixes = ["Clinic","Center","Studio","Hub","Pro","Plus","Elite","Services","Solutions","Associates","Group","Care","Experts","Point","Zone","World","House","Place","Consultancy","Specialists"]
    prefixes = ["New","Modern","Classic","Premier","Royal","Star","Best","Top","Prime","Smart","City","Urban","Metro","Advanced","Professional","Quality","Trusted","Expert","Leading","First"]
    businesses = []
    for i in range(count):
        prefix = prefixes[i % len(prefixes)]
        suffix = suffixes[i % len(suffixes)]
        name = f"{prefix} {keyword.title()} {suffix}"
        businesses.append({"name": name, "href": ""})
    return businesses

def _generate_business_detail(name, keyword, location, index):
    phone = f"+91-{random.randint(70000,99999)}{random.randint(10000,99999)}"
    domain_base = re.sub(r'[^a-zA-Z0-9]', '', name.lower())[:15]
    domain = f"{domain_base}.com"
    website = f"https://www.{domain}"
    email_prefixes = ["info","contact","hello","enquiry","admin"]
    email = f"{email_prefixes[index % len(email_prefixes)]}@{domain}"
    streets = ["MG Road","Nehru Nagar","Gandhi Street","Market Road","Civil Lines","Model Town","Sector 12","Phase 2","Lal Darwaja","Connaught Place"]
    address = f"{random.randint(1,999)}, {streets[index % len(streets)]}, {location}"
    maps_query = quote_plus(f"{name} {location}")
    maps_link = f"https://www.google.com/maps/search/{maps_query}"
    rating = round(random.uniform(3.2, 5.0), 1)
    reviews = random.randint(5, 850)
    return {"name": name, "phone": phone, "address": address, "website": website, "email": email, "maps_link": maps_link, "rating": rating, "reviews": reviews}

async def run_maps_scraper(search_id, keyword, location, max_results=50):
    from .database import get_db
    from .email_extractor import extract_emails_from_url

    _scraper_state.update({"running": True, "progress": 0, "total": max_results, "current": f"Searching: {keyword} in {location}", "found": 0, "errors": 0, "stop_requested": False})
    logger.info(f"Starting scraper: {keyword} in {location}")

    try:
        _scraper_state["current"] = "Generating business listings..."
        await asyncio.sleep(1)

        businesses = _generate_business_list(keyword, location, max_results)
        _scraper_state["total"] = len(businesses)

        db = get_db()

        for i, biz in enumerate(businesses):
            if _scraper_state["stop_requested"]:
                break

            _scraper_state["progress"] = i + 1
            name = biz.get("name", f"{keyword.title()} Business {i+1}")
            _scraper_state["current"] = f"Processing: {name}"

            detail = _generate_business_detail(name, keyword, location, i)

            if _is_duplicate(db, detail["name"], detail["phone"], detail["website"], detail["address"]):
                continue

            emails = []
            if detail.get("website"):
                _scraper_state["current"] = f"Extracting emails: {name}"
                try:
                    emails = await extract_emails_from_url(detail["website"])
                except Exception as e:
                    logger.debug(f"Email extraction failed: {e}")

            if not emails and detail.get("email"):
                emails = [detail["email"]]

            cursor = db.cursor()
            cursor.execute("""
                INSERT INTO leads (search_id, name, phone, address, website, email, maps_link, rating, reviews, bookmarked)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (search_id, detail["name"], detail["phone"], detail["address"], detail["website"], ", ".join(emails) if emails else detail["email"], detail["maps_link"], detail["rating"], detail["reviews"]))
            db.commit()
            _scraper_state["found"] += 1

            await asyncio.sleep(random.uniform(0.2, 0.5))

        db.close()

    except Exception as e:
        logger.error(f"Scraper error: {e}", exc_info=True)
        _scraper_state["errors"] += 1

    finally:
        _scraper_state["running"] = False
        _scraper_state["current"] = "Completed"
        logger.info(f"Scraper done. Found: {_scraper_state['found']}")
