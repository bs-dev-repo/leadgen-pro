import asyncio
import logging
import re
import random
from typing import List
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(
    r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b'
)

CONTACT_PATHS = [
    "/",
    "/contact",
    "/contact-us",
    "/contactus",
    "/about",
    "/about-us",
    "/aboutus",
    "/support",
    "/reach-us",
    "/get-in-touch",
    "/info",
]

EXCLUDED_DOMAINS = {
    "example.com", "sentry.io", "wix.com", "godaddy.com",
    "wordpress.com", "squarespace.com", "schema.org", "w3.org",
    "googleapis.com", "google.com", "facebook.com", "twitter.com",
    "instagram.com", "linkedin.com", "youtube.com", "apple.com",
    "microsoft.com", "amazon.com",
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/119.0 Safari/537.36",
]


def _clean_url(url: str) -> str:
    """Normalize URL."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _is_valid_email(email: str) -> bool:
    """Filter out obviously fake or system emails."""
    email = email.lower()
    
    # Skip image/file extensions
    if re.search(r'\.(png|jpg|jpeg|gif|svg|css|js|woff|ttf|eot|ico)$', email):
        return False
    
    # Skip excluded domains
    domain = email.split("@")[-1]
    if domain in EXCLUDED_DOMAINS:
        return False
    
    # Skip emails with numbers at start of domain (likely generated)
    if re.match(r'^\d', domain):
        return False
    
    # Skip very short local parts
    local = email.split("@")[0]
    if len(local) < 2:
        return False
    
    return True


def _extract_emails_from_html(html: str) -> List[str]:
    """Extract emails from HTML content."""
    # Try plain text first
    emails = set(EMAIL_REGEX.findall(html))
    
    # Also parse mailto: links
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if href.startswith("mailto:"):
            email = href[7:].split("?")[0].strip()
            if EMAIL_REGEX.match(email):
                emails.add(email)
    
    return [e.lower() for e in emails if _is_valid_email(e)]


async def extract_emails_from_url(url: str, max_pages: int = 5) -> List[str]:
    """Visit a website and extract emails from multiple pages."""
    url = _clean_url(url)
    all_emails = set()
    
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
    }
    
    async with httpx.AsyncClient(
        headers=headers,
        timeout=10,
        follow_redirects=True,
        verify=False,
    ) as client:
        
        base_url = url
        pages_checked = 0
        
        for path in CONTACT_PATHS:
            if pages_checked >= max_pages:
                break
            
            page_url = urljoin(base_url, path)
            
            try:
                resp = await client.get(page_url)
                if resp.status_code == 200:
                    emails = _extract_emails_from_html(resp.text)
                    all_emails.update(emails)
                    pages_checked += 1
                    
                    if emails:
                        logger.info(f"Found {len(emails)} emails at {page_url}")
                
                await asyncio.sleep(random.uniform(0.3, 0.8))
            
            except Exception as e:
                logger.debug(f"Failed to fetch {page_url}: {e}")
                continue
    
    return list(all_emails)


async def extract_emails_from_sites(search_id: int, websites: List[str]):
    """Extract emails from a list of websites and store in DB."""
    from .database import get_db
    
    logger.info(f"Extracting emails from {len(websites)} websites for search {search_id}")
    
    db = get_db()
    
    for i, website in enumerate(websites):
        url = _clean_url(website)
        logger.info(f"Processing {i+1}/{len(websites)}: {url}")
        
        try:
            emails = await extract_emails_from_url(url)
            
            cursor = db.cursor()
            cursor.execute("""
                INSERT INTO leads (search_id, name, phone, address, website, email, maps_link, rating, reviews, bookmarked)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                search_id,
                url,
                "",
                "",
                url,
                ", ".join(emails) if emails else "",
                "",
                0,
                0,
            ))
            db.commit()
        
        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
        
        await asyncio.sleep(random.uniform(0.5, 1.5))
    
    db.close()
    logger.info(f"Email extraction complete for search {search_id}")
