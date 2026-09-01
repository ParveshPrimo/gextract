import re
import urllib.parse
from typing import Optional, List, Tuple
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from .database import (
    get_cached_linkedin,
    set_cached_linkedin,
    update_business_linkedin,
    get_job_results,
    update_job_status,
    update_job_current_business
)

LINKEDIN_URL_PATTERN = re.compile(
    r'https?://(www\.)?linkedin\.com/(company|school|showcase|in)/[^/\s"\'>]+',
    re.IGNORECASE
)

def normalize_url(raw_url: str) -> Optional[str]:
    """Sanitize and normalize input business URL."""
    if not raw_url:
        return None
    url = raw_url.strip()
    if not url:
        return None
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "http://" + url
    try:
        parsed = urllib.parse.urlparse(url)
        if not parsed.netloc:
            return None
        return url
    except Exception:
        return None

def extract_linkedin_urls(html_content: str) -> List[str]:
    """Parse HTML DOM and extract valid LinkedIn URLs excluding share links."""
    if not html_content:
        return []

    urls_found = []
    soup = BeautifulSoup(html_content, 'html.parser')

    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href'].strip()
        match = LINKEDIN_URL_PATTERN.search(href)
        if match:
            url = match.group(0)
            if 'linkedin.com/shareArticle' in href or 'linkedin.com/sharing' in href:
                continue
            if url not in urls_found:
                urls_found.append(url)
    return urls_found

def select_best_linkedin_url(urls: List[str]) -> Optional[str]:
    """Select highest priority LinkedIn profile from matched URLs."""
    if not urls:
        return None
    for priority_path in ['/company/', '/showcase/', '/school/', '/in/']:
        for url in urls:
            if priority_path in url.lower():
                return url
    return urls[0]

def discover_linkedin_for_website(page, website_url: str, logger) -> Tuple[Optional[str], str, Optional[str]]:
    """
    Crawls website homepage (and fallback about/contact pages if needed) to extract LinkedIn URL.
    
    Returns:
        (linkedin_url, status, error_msg)
    """
    normalized = normalize_url(website_url)
    if not normalized:
        return None, "Failed", "Invalid URL format"

    # Block heavy resources to ensure super-fast DOM rendering
    def block_resources(route):
        if route.request.resource_type in ["image", "media", "font", "stylesheet"]:
            route.abort()
        else:
            route.continue_()

    try:
        page.route("**/*", block_resources)
    except Exception:
        pass

    try:
        logger.info(f"Crawling homepage: {normalized}")
        page.goto(normalized, wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(1000)
        html = page.content()

        found_urls = extract_linkedin_urls(html)
        best_url = select_best_linkedin_url(found_urls)
        if best_url:
            return best_url, "Success", None

        # Fallback: check secondary /contact or /about pages
        logger.info(f"No LinkedIn URL on homepage of {normalized}. Searching for About/Contact links...")
        soup = BeautifulSoup(html, 'html.parser')
        secondary_url = None
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href'].strip()
            href_lower = href.lower()
            if 'about' in href_lower or 'contact' in href_lower:
                secondary_url = urllib.parse.urljoin(normalized, href)
                break

        if secondary_url:
            logger.info(f"Crawling secondary page: {secondary_url}")
            page.goto(secondary_url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(1000)
            secondary_html = page.content()
            found_urls = extract_linkedin_urls(secondary_html)
            best_url = select_best_linkedin_url(found_urls)
            if best_url:
                return best_url, "Success", None

        return None, "Success", "No LinkedIn link found"

    except Exception as ex:
        err_msg = str(ex).split("\n")[0]
        logger.warning(f"Error crawling {normalized}: {err_msg}")
        return None, "Failed", f"Crawl error: {err_msg}"
    finally:
        try:
            page.unroute("**/*")
        except Exception:
            pass

def run_linkedin_pipeline(job_id: int, stop_event, headless: bool = True, logger=None) -> None:
    """Sequential pipeline step to extract LinkedIn URLs for all websites collected in the job."""
    if logger:
        logger.info(f"Starting Phase 2: LinkedIn Profile Extraction for Job #{job_id}")
    
    update_job_status(job_id, status="running", phase="linkedin")

    results = get_job_results(job_id)
    if not results:
        if logger:
            logger.info("No business records found to process for LinkedIn.")
        return

    # Filter items that have a website
    pending_items = [r for r in results if r.get("website")]
    total_count = len(pending_items)

    if total_count == 0:
        if logger:
            logger.info("No business websites present in extracted results.")
        return

    if logger:
        logger.info(f"Found {total_count} business records with websites to analyze.")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                headless=headless,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
                ignore_https_errors=True
            )
            page = context.new_page()

            for idx, item in enumerate(pending_items, 1):
                if stop_event.is_set():
                    if logger:
                        logger.info("LinkedIn pipeline stopped by user request.")
                    break

                rec_id = item["id"]
                biz_name = item.get("name", f"Record #{rec_id}")
                raw_website = item["website"]

                update_job_current_business(job_id, f"[LinkedIn] {biz_name}")

                normalized = normalize_url(raw_website)
                if not normalized:
                    update_business_linkedin(rec_id, None, "failed", "Invalid URL format")
                    continue

                # 1. Check persistent SQLite cache
                cached = get_cached_linkedin(normalized)
                if cached:
                    if logger:
                        logger.info(f"[{idx}/{total_count}] Cache Hit for {normalized} -> {cached.get('linkedin_url')}")
                    update_business_linkedin(
                        rec_id,
                        cached.get("linkedin_url"),
                        cached.get("status", "completed"),
                        cached.get("error")
                    )
                    continue

                # 2. Cache miss: Crawl website
                if logger:
                    logger.info(f"[{idx}/{total_count}] Processing ({biz_name}): {normalized}")

                link_url, status, error_msg = discover_linkedin_for_website(page, normalized, logger)

                # 3. Store into persistent cache & update database incrementally
                set_cached_linkedin(normalized, link_url, status, error_msg)
                update_business_linkedin(rec_id, link_url, status, error_msg)

            browser.close()

        except Exception as e:
            if logger:
                logger.error(f"Error during LinkedIn browser execution: {e}")
