import asyncio
import logging
import random
import re
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Global scraper state
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
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
]


def get_scraper_status():
    return dict(_scraper_state)


def stop_scraper():
    _scraper_state["stop_requested"] = True
    logger.info("Stop requested for scraper")


def _is_duplicate(db, name: str, phone: str, website: str, address: str) -> bool:
    """Check if a lead already exists."""
    cursor = db.cursor()
    
    # Check by phone
    if phone:
        cursor.execute("SELECT id FROM leads WHERE phone = ? AND phone != ''", (phone,))
        if cursor.fetchone():
            return True
    
    # Check by website
    if website:
        cursor.execute("SELECT id FROM leads WHERE website = ? AND website != ''", (website,))
        if cursor.fetchone():
            return True
    
    # Check by name + address
    if name and address:
        cursor.execute(
            "SELECT id FROM leads WHERE name = ? AND address = ?",
            (name, address)
        )
        if cursor.fetchone():
            return True
    
    return False


async def run_maps_scraper(search_id: int, keyword: str, location: str, max_results: int = 50):
    """Main scraper function that runs in background."""
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
    
    logger.info(f"Starting scraper: {keyword} in {location}")
    
    try:
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--no-first-run",
                    "--disable-extensions",
                ]
            )
            
            context = await browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1280, "height": 800},
                locale="en-US",
            )
            
            page = await context.new_page()
            
            # Block images and fonts to speed up
            await page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,eot}", lambda route: route.abort())
            
            search_query = f"{keyword} {location}"
            maps_url = f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}"
            
            logger.info(f"Navigating to: {maps_url}")
            _scraper_state["current"] = "Loading Google Maps..."
            
            await page.goto(maps_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(random.uniform(2, 4))
            
            # Accept cookies if prompted
            try:
                accept_btn = await page.query_selector('button[aria-label*="Accept"]')
                if accept_btn:
                    await accept_btn.click()
                    await asyncio.sleep(1)
            except:
                pass
            
            businesses = []
            scroll_attempts = 0
            max_scrolls = 30
            
            _scraper_state["current"] = "Scrolling and collecting listings..."
            
            while len(businesses) < max_results and scroll_attempts < max_scrolls:
                if _scraper_state["stop_requested"]:
                    logger.info("Scraper stopped by user")
                    break
                
                # Find all listing items
                try:
                    items = await page.query_selector_all('div[role="feed"] > div > div[jsaction]')
                    if not items:
                        items = await page.query_selector_all('a[href*="/maps/place/"]')
                    
                    logger.info(f"Found {len(items)} items after {scroll_attempts} scrolls")
                    
                    for item in items:
                        if len(businesses) >= max_results:
                            break
                        
                        try:
                            # Get the listing link/name
                            link = await item.query_selector('a[href*="/maps/place/"]')
                            if not link:
                                continue
                            
                            name_el = await item.query_selector('.qBF1Pd, .fontHeadlineSmall, [aria-label]')
                            name = ""
                            if name_el:
                                name = await name_el.inner_text()
                            if not name:
                                name = await link.get_attribute("aria-label") or ""
                            
                            if not name or name in [b.get("name") for b in businesses]:
                                continue
                            
                            href = await link.get_attribute("href") or ""
                            
                            businesses.append({"name": name.strip(), "href": href})
                        except:
                            pass
                except Exception as e:
                    logger.error(f"Error collecting items: {e}")
                
                # Scroll the results panel
                try:
                    feed = await page.query_selector('div[role="feed"]')
                    if feed:
                        await feed.evaluate("el => el.scrollBy(0, 1000)")
                    else:
                        await page.evaluate("window.scrollBy(0, 1000)")
                except:
                    pass
                
                await asyncio.sleep(random.uniform(1.5, 2.5))
                scroll_attempts += 1
            
            logger.info(f"Collected {len(businesses)} businesses, now extracting details")
            _scraper_state["total"] = len(businesses)
            
            db = get_db()
            
            for i, biz in enumerate(businesses):
                if _scraper_state["stop_requested"]:
                    break
                
                _scraper_state["progress"] = i + 1
                _scraper_state["current"] = f"Extracting: {biz['name']}"
                
                detail = await _extract_business_detail(context, biz["href"], biz["name"])
                
                if not detail:
                    _scraper_state["errors"] += 1
                    continue
                
                # Check duplicates
                if _is_duplicate(db, detail["name"], detail["phone"], detail["website"], detail["address"]):
                    logger.info(f"Duplicate skipped: {detail['name']}")
                    continue
                
                # Extract emails from website
                emails = []
                if detail.get("website"):
                    _scraper_state["current"] = f"Extracting emails: {detail['name']}"
                    try:
                        emails = await extract_emails_from_url(detail["website"])
                    except Exception as e:
                        logger.error(f"Email extraction error for {detail['website']}: {e}")
                
                cursor = db.cursor()
                cursor.execute("""
                    INSERT INTO leads (search_id, name, phone, address, website, email, maps_link, rating, reviews, bookmarked)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """, (
                    search_id,
                    detail.get("name", ""),
                    detail.get("phone", ""),
                    detail.get("address", ""),
                    detail.get("website", ""),
                    ", ".join(emails) if emails else "",
                    detail.get("maps_link", biz["href"]),
                    detail.get("rating", 0),
                    detail.get("reviews", 0),
                ))
                db.commit()
                _scraper_state["found"] += 1
                
                # Anti-blocking delay
                await asyncio.sleep(random.uniform(0.5, 1.5))
            
            db.close()
            await browser.close()
    
    except ImportError:
        logger.warning("Playwright not installed. Using mock data for demo.")
        await _generate_mock_data(search_id, keyword, location, max_results)
    
    except Exception as e:
        logger.error(f"Scraper error: {e}", exc_info=True)
        _scraper_state["current"] = f"Error: {str(e)}"
    
    finally:
        _scraper_state["running"] = False
        _scraper_state["current"] = "Completed"
        logger.info(f"Scraper finished. Found: {_scraper_state['found']}")


async def _extract_business_detail(context, href: str, name: str) -> Optional[dict]:
    """Visit a business page and extract details."""
    detail = {
        "name": name,
        "phone": "",
        "address": "",
        "website": "",
        "maps_link": href,
        "rating": 0,
        "reviews": 0,
    }
    
    if not href or "/maps/place/" not in href:
        return detail
    
    try:
        page = await context.new_page()
        await page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,eot}", lambda route: route.abort())
        
        await page.goto(href, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(random.uniform(1, 2))
        
        # Rating
        try:
            rating_el = await page.query_selector('div.F7nice span[aria-hidden]')
            if rating_el:
                rating_text = await rating_el.inner_text()
                detail["rating"] = float(rating_text.strip())
        except:
            pass
        
        # Reviews count
        try:
            reviews_el = await page.query_selector('div.F7nice span[aria-label*="review"]')
            if reviews_el:
                label = await reviews_el.get_attribute("aria-label") or ""
                nums = re.findall(r'[\d,]+', label)
                if nums:
                    detail["reviews"] = int(nums[0].replace(",", ""))
        except:
            pass
        
        # Address
        try:
            addr_el = await page.query_selector('button[data-item-id="address"] .Io6YTe')
            if not addr_el:
                addr_el = await page.query_selector('[data-tooltip="Copy address"] .Io6YTe')
            if addr_el:
                detail["address"] = await addr_el.inner_text()
        except:
            pass
        
        # Phone
        try:
            phone_el = await page.query_selector('button[data-tooltip="Copy phone number"] .Io6YTe')
            if not phone_el:
                phone_el = await page.query_selector('[data-item-id*="phone"] .Io6YTe')
            if phone_el:
                detail["phone"] = await phone_el.inner_text()
        except:
            pass
        
        # Website
        try:
            web_el = await page.query_selector('a[data-item-id="authority"]')
            if not web_el:
                web_el = await page.query_selector('a[aria-label*="website"]')
            if web_el:
                detail["website"] = await web_el.get_attribute("href") or ""
        except:
            pass
        
        await page.close()
    
    except Exception as e:
        logger.error(f"Detail extraction error for {name}: {e}")
        try:
            await page.close()
        except:
            pass
    
    return detail


async def _generate_mock_data(search_id: int, keyword: str, location: str, count: int):
    """Generate mock data when Playwright is unavailable."""
    from .database import get_db
    import random
    
    logger.info(f"Generating {count} mock leads for demo")
    
    mock_domains = [
        "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "business.com"
    ]
    
    db = get_db()
    
    for i in range(min(count, 20)):
        _scraper_state["progress"] = i + 1
        _scraper_state["current"] = f"Generating mock lead {i+1}..."
        
        name = f"{keyword.title()} {['Plus', 'Pro', 'Elite', 'Hub', 'Center', 'Studio'][i % 6]} {location} #{i+1}"
        domain = f"{keyword.lower().replace(' ', '')}{i+1}.com"
        email = f"info@{domain}"
        phone = f"+91-{random.randint(7000000000, 9999999999)}"
        
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO leads (search_id, name, phone, address, website, email, maps_link, rating, reviews, bookmarked)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            search_id,
            name,
            phone,
            f"{random.randint(1, 999)}, Sample Street, {location}",
            f"https://www.{domain}",
            email,
            f"https://maps.google.com/?q={name.replace(' ', '+')}",
            round(random.uniform(3.0, 5.0), 1),
            random.randint(10, 500),
        ))
        db.commit()
        _scraper_state["found"] += 1
        
        await asyncio.sleep(0.2)
    
    db.close()
    logger.info("Mock data generation complete")
