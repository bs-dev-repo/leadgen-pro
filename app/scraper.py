import asyncio
import logging
import random
import re
from urllib.parse import quote_plus
import os

import httpx

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


def get_scraper_status():
    return dict(_scraper_state)


def stop_scraper():
    _scraper_state["stop_requested"] = True


def _is_duplicate(db, name, phone, website, address):
    cursor = db.cursor()
    if phone and phone.strip():
        cursor.execute("SELECT id FROM leads WHERE phone = ? AND phone != ''", (phone,))
        if cursor.fetchone():
            return True
    if website and website.strip():
        cursor.execute("SELECT id FROM leads WHERE website = ? AND website != ''", (website,))
        if cursor.fetchone():
            return True
    if name and address:
        cursor.execute("SELECT id FROM leads WHERE name = ? AND address = ?", (name, address))
        if cursor.fetchone():
            return True
    return False


async def _fetch_serpapi_results(keyword: str, location: str, api_key: str, max_results: int) -> list:
    """Fetch real Google Maps data from SerpApi."""
    businesses = []
    start = 0

    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        while len(businesses) < max_results:
            if _scraper_state["stop_requested"]:
                break

            params = {
                "engine": "google_maps",
                "q": f"{keyword} {location}",
                "type": "search",
                "api_key": api_key,
                "start": start,
            }

            _scraper_state["current"] = f"Fetching page {start // 20 + 1} from Google Maps..."
            logger.info(f"SerpApi request: {keyword} in {location}, start={start}")

            try:
                resp = await client.get("https://serpapi.com/search", params=params)
                data = resp.json()

                if "error" in data:
                    logger.error(f"SerpApi error: {data['error']}")
                    _scraper_state["current"] = f"API Error: {data['error']}"
                    break

                results = data.get("local_results", [])
                if not results:
                    logger.info("No more results from SerpApi")
                    break

                for r in results:
                    if len(businesses) >= max_results:
                        break
                    businesses.append(r)

                # SerpApi returns 20 per page
                if len(results) < 20:
                    break

                start += 20
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"SerpApi fetch error: {e}")
                _scraper_state["errors"] += 1
                break

    return businesses


def _parse_serpapi_result(r: dict) -> dict:
    """Parse a single SerpApi local result into our lead format."""

    name = r.get("title", "")
    address = r.get("address", "")
    phone = r.get("phone", "")
    website = r.get("website", "")
    rating = r.get("rating", 0) or 0
    reviews = r.get("reviews", 0) or 0

    # Maps link
    maps_link = r.get("link", "")
    if not maps_link:
        place_id = r.get("place_id", "")
        if place_id:
            maps_link = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
        else:
            maps_link = f"https://www.google.com/maps/search/{quote_plus(name + ' ' + address)}"

    return {
        "name": name,
        "phone": phone,
        "address": address,
        "website": website,
        "maps_link": maps_link,
        "rating": float(rating) if rating else 0,
        "reviews": int(str(reviews).replace(",", "")) if reviews else 0,
    }


async def run_maps_scraper(search_id: int, keyword: str, location: str, max_results: int = 50):
    from .database import get_db
    from .email_extractor import extract_emails_from_url

    _scraper_state.update({
        "running": True,
        "progress": 0,
        "total": max_results,
        "current": f"Searching: {keyword} in {location}",
        "found": 0,
        "errors": 0,
        "stop_requested": False,
    })

    logger.info(f"Starting scraper: {keyword} in {location}, max={max_results}")

    # Get API key from environment variable
    api_key = os.environ.get("SERPAPI_KEY", "").strip()

    if not api_key:
        _scraper_state["current"] = "Error: SERPAPI_KEY not set. Please add it in Render environment variables."
        logger.error("SERPAPI_KEY environment variable not set")
        _scraper_state["running"] = False
        return

    try:
        raw_results = await _fetch_serpapi_results(keyword, location, api_key, max_results)

        if not raw_results:
            _scraper_state["current"] = "No results found. Try a different keyword or location."
            logger.warning("No results from SerpApi")
            _scraper_state["running"] = False
            return

        _scraper_state["total"] = len(raw_results)
        _scraper_state["current"] = f"Found {len(raw_results)} businesses, extracting emails..."
        logger.info(f"Got {len(raw_results)} results from SerpApi")

        db = get_db()

        for i, raw in enumerate(raw_results):
            if _scraper_state["stop_requested"]:
                logger.info("Scraper stopped by user")
                break

            _scraper_state["progress"] = i + 1
            detail = _parse_serpapi_result(raw)
            _scraper_state["current"] = f"Processing: {detail['name']}"

            if not detail["name"]:
                continue

            if _is_duplicate(db, detail["name"], detail["phone"], detail["website"], detail["address"]):
                logger.info(f"Duplicate skipped: {detail['name']}")
                continue

            # Extract real emails from website
            emails = []
            if detail.get("website"):
                _scraper_state["current"] = f"Extracting emails: {detail['name']}"
                try:
                    emails = await extract_emails_from_url(detail["website"])
                    if emails:
                        logger.info(f"Found emails for {detail['name']}: {emails}")
                except Exception as e:
                    logger.debug(f"Email extraction failed for {detail['website']}: {e}")

            cursor = db.cursor()
            cursor.execute("""
                INSERT INTO leads (search_id, name, phone, address, website, email, maps_link, rating, reviews, bookmarked)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                search_id,
                detail["name"],
                detail["phone"],
                detail["address"],
                detail["website"],
                ", ".join(emails) if emails else "",
                detail["maps_link"],
                detail["rating"],
                detail["reviews"],
            ))
            db.commit()
            _scraper_state["found"] += 1

            await asyncio.sleep(random.uniform(0.3, 0.7))

        db.close()

    except Exception as e:
        logger.error(f"Scraper error: {e}", exc_info=True)
        _scraper_state["current"] = f"Error: {str(e)}"
        _scraper_state["errors"] += 1

    finally:
        _scraper_state["running"] = False
        _scraper_state["current"] = f"Completed — {_scraper_state['found']} leads saved"
        logger.info(f"Scraper done. Found: {_scraper_state['found']}")
