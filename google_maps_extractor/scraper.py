import re
import urllib.parse
from playwright.sync_api import sync_playwright

from .utils import get_logger
from .database import update_job_status, update_job_current_business, insert_business
from .linkedin_extractor import run_linkedin_pipeline

def clean_extracted_text(text: str) -> str:
    """Clean extracted text by removing private use area symbols, formatting spaces, and newlines."""
    if not text:
        return ""
    # Replace newlines with spaces
    text = text.replace("\n", " ")
    # Strip private use area symbols (commonly used for icons like \ue0b0 / )
    text = re.sub(r'[\uE000-\uF8FF]', '', text)
    # Collapse multiple whitespaces
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def handle_consent(page, logger) -> None:
    """Handle the Google Maps cookie consent button if it appears."""
    try:
        consent_selectors = [
            "button:has-text('Accept all')", 
            "button:has-text('Accept')", 
            "button:has-text('Agree')", 
            "button:has-text('I agree')",
            "form[action*='consent.google.com'] button"
        ]
        for sel in consent_selectors:
            btn = page.locator(sel).first
            if btn.is_visible():
                logger.info(f"Clicking cookie consent button: '{sel}'")
                btn.click()
                page.wait_for_timeout(2000)
                return
    except Exception as e:
        logger.debug(f"Cookie consent check skipped or button not found: {e}")

def parse_coords(url: str) -> tuple:
    """Extract latitude and longitude from Google Maps URL."""
    match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if match:
        return float(match.group(1)), float(match.group(2))
    return None, None

def gather_business_urls(page, feed_locator, max_results: int, stop_event, logger) -> list:
    """Scroll the search results pane to gather listing URLs up to max_results."""
    urls = set()
    last_count = 0
    no_change_count = 0
    scroll_attempts = 0
    
    while len(urls) < max_results:
        if stop_event.is_set():
            logger.info("Search listing scrolling stopped by user request.")
            break
            
        # Find all business card link elements
        # Matches typical Google Maps place listings
        links = page.locator('a[href*="/maps/place/"]').all()
        for link in links:
            try:
                href = link.get_attribute('href')
                if href:
                    # Clean URL to base format to avoid duplicates
                    # Typical href: https://www.google.com/maps/place/Business+Name/...
                    base_url = href.split("?")[0] if "?" in href else href
                    urls.add(base_url)
            except Exception:
                continue
                
        logger.info(f"Gathered {len(urls)} listing URLs so far...")
        
        if len(urls) >= max_results:
            break
            
        # Scroll the feed down by one viewport height
        feed_locator.evaluate("el => el.scrollBy(0, el.clientHeight)")
        page.wait_for_timeout(1500)
        
        # Check if list has ended or stopped loading new items
        current_count = len(urls)
        if current_count == last_count:
            no_change_count += 1
            if no_change_count >= 8:
                # Look for end of list indicator text
                end_list_text = page.locator("text=\"You've reached the end of the list.\"").first
                if end_list_text.is_visible():
                    logger.info("Reached end of search results list.")
                    break
                else:
                    logger.info("No more listings loaded after multiple scroll attempts. Stopping.")
                    break
        else:
            no_change_count = 0
            last_count = current_count
            
        scroll_attempts += 1
        if scroll_attempts > 150:
            logger.info("Safety limit of 150 scrolls reached.")
            break
            
    return list(urls)[:max_results]

def extract_business_details(page, url: str, logger) -> dict:
    """Extract all publicly visible information from a business details panel."""
    data = {
        "name": "",
        "category": "",
        "rating": None,
        "reviews": None,
        "phone": "",
        "website": "",
        "address": "",
        "maps_url": url,
        "latitude": None,
        "longitude": None,
        "opening_hours": ""
    }
    
    # 1. Business Name
    try:
        h1_el = page.locator('h1').first
        h1_el.wait_for(state="visible", timeout=5000)
        data["name"] = clean_extracted_text(h1_el.inner_text())
    except Exception as e:
        logger.debug(f"Failed to find name h1: {e}")
        return data
        
    # 2. Category
    try:
        cat_el = page.locator('button[jsaction*="pane.rating.category"]').first
        if not cat_el.is_visible():
            cat_el = page.locator('button[jsaction*="category"]').first
        if cat_el.is_visible():
            data["category"] = clean_extracted_text(cat_el.inner_text())
    except Exception as e:
        logger.debug(f"Category extraction failed: {e}")
        
    # 3. Rating & Reviews
    try:
        rating_el = page.locator('div.F7nice span[aria-hidden="true"]').first
        if rating_el.is_visible():
            rating_str = rating_el.inner_text().strip().replace(",", ".")
            data["rating"] = float(rating_str)
            
        reviews_el = page.locator('button[jsaction*="pane.rating.moreReviews"]').first
        if not reviews_el.is_visible():
            reviews_el = page.locator('div.F7nice span[aria-label*="reviews"]').first
            
        if reviews_el.is_visible():
            reviews_str = reviews_el.inner_text().strip()
            reviews_str = re.sub(r'[^\d]', '', reviews_str)
            if reviews_str:
                data["reviews"] = int(reviews_str)
    except Exception as e:
        logger.debug(f"Rating/Reviews extraction failed: {e}")
        
    # 4. Address
    try:
        addr_el = page.locator('button[data-item-id^="address"]').first
        if not addr_el.is_visible():
            addr_el = page.locator('button[data-tooltip="Copy address"]').first
        if not addr_el.is_visible():
            addr_el = page.locator('button[aria-label*="Address:"]').first
            
        if addr_el.is_visible():
            address_text = addr_el.inner_text().strip()
            if address_text.lower().startswith("address:"):
                address_text = address_text[8:].strip()
            data["address"] = clean_extracted_text(address_text)
    except Exception as e:
        logger.debug(f"Address extraction failed: {e}")
        
    # 5. Phone
    try:
        phone_el = page.locator('button[data-item-id^="phone:tel:"]').first
        if not phone_el.is_visible():
            phone_el = page.locator('button[data-tooltip="Copy phone number"]').first
        if not phone_el.is_visible():
            phone_el = page.locator('button[aria-label*="Phone:"]').first
            
        if phone_el.is_visible():
            phone_text = phone_el.inner_text().strip()
            if phone_text.lower().startswith("phone:"):
                phone_text = phone_text[6:].strip()
            data["phone"] = clean_extracted_text(phone_text)
    except Exception as e:
        logger.debug(f"Phone extraction failed: {e}")
        
    # 6. Website
    try:
        web_el = page.locator('a[data-item-id="authority"]').first
        if not web_el.is_visible():
            web_el = page.locator('a[data-tooltip="Open website"]').first
        if not web_el.is_visible():
            web_el = page.locator('a[aria-label*="Website:"]').first
            
        if web_el.is_visible():
            data["website"] = web_el.get_attribute("href")
    except Exception as e:
        logger.debug(f"Website extraction failed: {e}")
        
    # 7. Coordinates
    try:
        for _ in range(6):
            lat, lon = parse_coords(page.url)
            if lat is not None:
                data["latitude"] = lat
                data["longitude"] = lon
                break
            page.wait_for_timeout(500)
    except Exception as e:
        logger.debug(f"Coordinates parsing failed: {e}")
        
    # 8. Opening Hours
    try:
        hours_btn = page.locator('button[data-item-id="oh"]').first
        if not hours_btn.is_visible():
            hours_btn = page.locator('div[jsaction*="hours"]').first
        if not hours_btn.is_visible():
            hours_btn = page.locator('[aria-label*="Hours"]').first
            
        if hours_btn.is_visible():
            hours_btn.click()
            page.wait_for_timeout(800)
            
        table = page.locator('table.e2maeb').first
        if table.is_visible():
            rows = table.locator('tr').all()
            row_texts = []
            for r in rows:
                row_texts.append(clean_extracted_text(r.inner_text().replace('\n', ': ')))
            data["opening_hours"] = "\n".join(row_texts)
        else:
            # Fallback text parsing
            parent = hours_btn.locator('..')
            parent_text = parent.inner_text().strip()
            lines = [line.strip() for line in parent_text.split('\n') if line.strip()]
            
            days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
                    "lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
            
            hours_list = []
            for i, line in enumerate(lines):
                is_day = any(d in line.lower() for d in days)
                if is_day:
                    has_time = any(char.isdigit() for char in line) or "closed" in line.lower() or "24" in line.lower()
                    if has_time and (":" in line or "–" in line or " - " in line):
                        hours_list.append(clean_extracted_text(line))
                    else:
                        hours_val = ""
                        if i + 1 < len(lines):
                            next_line = lines[i + 1]
                            if not any(d in next_line.lower() for d in days):
                                hours_val = next_line
                        if hours_val:
                            hours_list.append(clean_extracted_text(f"{line}: {hours_val}"))
                        else:
                            hours_list.append(clean_extracted_text(line))
            
            if hours_list:
                data["opening_hours"] = "\n".join(hours_list)
    except Exception as e:
        logger.debug(f"Opening hours extraction failed: {e}")
        
    return data

def run_scraper(job_id: int, query: str, max_results: int, stop_event, headless: bool = True, extract_linkedin: bool = True) -> None:
    """Main extraction routine running in a background thread."""
    logger = get_logger(job_id)
    logger.info(f"Scraper thread started for job {job_id}. Query: '{query}'")
    
    try:
        update_job_status(job_id, "running")
    except Exception as e:
        logger.error(f"Failed to initialize job in DB: {e}")
        return

    # ── Phase 1: Google Maps Scraper ──────────────────────────────────────────
    phase1_success = False
    try:
        with sync_playwright() as p:
            logger.info("Launching browser for Phase 1 (Google Maps)...")
            browser = p.chromium.launch(
                headless=headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars",
                ]
            )
            
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )
            
            page = context.new_page()
            
            # Navigate to Search Query directly
            logger.info(f"Navigating to search page for '{query}'...")
            encoded_query = urllib.parse.quote_plus(query)
            search_url = f"https://www.google.com/maps/search/{encoded_query}"
            page.goto(search_url, wait_until="domcontentloaded")
            
            handle_consent(page, logger)
            page.wait_for_timeout(3000)
            
            # Check for no search results
            no_results_selectors = [
                "text=\"Google Maps can't find\"",
                "text=\"No results found\"",
                "div.Q2iC3c"
            ]
            has_no_results = False
            for sel in no_results_selectors:
                if page.locator(sel).first.is_visible():
                    has_no_results = True
                    break
                    
            if has_no_results:
                logger.info("No search results found.")
                update_job_status(job_id, "completed", 0)
                browser.close()
                return
                
            # Check direct redirect vs list feed
            current_url = page.url
            if "/maps/place/" in current_url:
                logger.info("Query redirected directly to place listing.")
                business_urls = [current_url]
            else:
                # Gather urls by scrolling
                feed_locator = page.locator('div[role="feed"]').first
                try:
                    feed_locator.wait_for(state="visible", timeout=6000)
                except Exception:
                    logger.warning("Feed scrollable container not found. Grabbing visible links.")
                    feed_locator = None
                    
                if feed_locator:
                    logger.info("Scrolling left panel feed...")
                    business_urls = gather_business_urls(page, feed_locator, max_results, stop_event, logger)
                else:
                    links = page.locator('a[href*="/maps/place/"]').all()
                    business_urls = list(set([link.get_attribute("href") for link in links if link.get_attribute("href")]))[:max_results]
            
            # Details Extraction phase
            total_urls = len(business_urls)
            logger.info(f"Total listings collected: {total_urls}. Starting details extraction...")
            
            processed_count = 0
            for url in business_urls:
                if stop_event.is_set():
                    logger.info("Extraction stopped by user request.")
                    break
                    
                processed_count += 1
                logger.info(f"Extracting details ({processed_count}/{total_urls}): {url}")
                
                try:
                    page.goto(url, wait_until="domcontentloaded")
                    page.wait_for_timeout(2000)
                    
                    data = extract_business_details(page, url, logger)
                    
                    if data and data.get("name"):
                        # Insert data incrementally into DB
                        insert_business(job_id, data)
                        update_job_current_business(job_id, data["name"])
                        logger.info(f"Successfully scraped: '{data['name']}'")
                    else:
                        logger.warning(f"Could not parse valid business name from: {url}")
                        
                except Exception as ex:
                    logger.error(f"Failed to extract details from {url}: {ex}")
                    continue
            
            browser.close()
            phase1_success = True

    except Exception as e:
        logger.error(f"Google Maps scraper error: {e}")
        update_job_status(job_id, "failed")
        return

    # ── Phase 2: LinkedIn Discovery ───────────────────────────────────────────
    if extract_linkedin and not stop_event.is_set() and phase1_success:
        logger.info("Google Maps extraction completed successfully. Starting LinkedIn extraction pipeline...")
        try:
            run_linkedin_pipeline(job_id, stop_event, headless=headless, logger=logger)
        except Exception as ex:
            logger.error(f"LinkedIn extraction pipeline failed: {ex}")
    elif not extract_linkedin:
        logger.info("LinkedIn extraction phase skipped per user setting.")

    # Final status update
    if stop_event.is_set():
        update_job_status(job_id, "stopped")
        logger.info("Scraper job stopped.")
    else:
        update_job_status(job_id, "completed")
        logger.info("Extraction job completed successfully.")



