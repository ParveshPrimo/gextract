# Technical Specification: LinkedIn Profile Extractor Feature

This document provides a detailed architectural specification and step-by-step functionality breakdown of the **LinkedIn Profile Extractor** feature. Software engineers and developers can use this guide to rebuild the feature in any language or technology stack (e.g., Python, Node.js, Go, C#).

---

## 1. Executive Summary & Core Objective

The **LinkedIn Extractor** is an automated data enrichment engine designed to process lists of corporate websites (from CSV or Excel files), discover official LinkedIn organization/profile pages linked on those websites, and export an enriched dataset.

### Key Capabilities:
1. **Automated Input Column Detection**: Accepts files containing company websites under various column names (`Website`, `URL`, `Domain`, `Web`).
2. **High-Performance Headless Web Crawling**: Uses headless browser automation with resource-blocking optimizations to handle dynamic JavaScript-rendered single-page applications (SPAs).
3. **Multi-Stage Discovery & Fallback Handling**: Inspects the main landing page first; if no link is found, automatically discovers and crawls secondary pages (`/about`, `/contact`).
4. **Regex & Semantic Hierarchy Ranking**: Filters out generic share buttons and prioritizes corporate page types (`/company/` > `/showcase/` > `/school/` > `/in/`).
5. **Local SQLite Persistence Caching**: Caches lookup results permanently to prevent redundant web requests and save bandwidth.
6. **Concurrent Worker Pipeline**: Supports configurable queue-based worker pools with polite inter-request delays and error handling.

---

## 2. System Architecture & Component Diagram

```mermaid
flowchart TD
    A[Input File: CSV / XLSX] --> B[Data Exporter / Reader]
    B --> C[Extract & Normalize URLs]
    C --> D[Queue & Worker Pool]
    
    subgraph Processing Loop (Per Worker)
        D --> E{SQLite Cache Check}
        E -- Cache Hit --> F[Retrieve Cached Result]
        E -- Cache Miss --> G[Headless Browser Engine]
        
        G --> H[Resource-Optimized Load Main Page]
        H --> I[Parse HTML DOM with Regex]
        I --> J{LinkedIn URL Found?}
        
        J -- Yes --> K[Prioritize & Select Best Link]
        J -- No --> L[Locate About/Contact Links]
        
        L -- Link Found --> M[Navigate to Secondary Page]
        M --> N[Parse Secondary HTML DOM]
        N --> K
        L -- No Link --> K
        
        K --> O[Write Result to Cache]
    end
    
    F --> P[Update In-Memory Dataset]
    O --> P
    P --> Q[Export Enriched CSV / XLSX]
```

---

## 3. Data Specifications & Schema

### 3.1 Input Detection Rules
The system must automatically scan input columns and identify the target URL column using case-insensitive matching for:
- `website`
- `url`
- `domain`
- `web`

### 3.2 Output Columns Schema
The output dataset appends 5 standardized enrichment columns to the original data:

| Column Name | Type | Description | Example |
| :--- | :--- | :--- | :--- |
| `LinkedIn URL` | String (Nullable) | Target LinkedIn page discovered. | `https://www.linkedin.com/company/acme-corp` |
| `LinkedIn Found (Yes/No)` | String | Binary flag indicating lookup status. | `Yes` / `No` |
| `Status` | String | Operation status. | `Success` / `Failed` |
| `Error` | String (Nullable) | Error reason if execution failed. | `Timeout`, `Invalid URL format` |
| `Processed Time (s)` | Float | Duration in seconds to process row. | `1.42` |

### 3.3 SQLite Cache Database Schema
```sql
CREATE TABLE IF NOT EXISTS cache (
    url TEXT PRIMARY KEY,
    linkedin_url TEXT,
    status TEXT,
    error TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 4. Step-by-Step Functional Workflow

### Step 1: URL Normalization & Sanitization
Before any network request is initiated:
1. Strip leading/trailing whitespace.
2. Verify if the scheme (`http://` or `https://`) is present. Prepend `http://` if missing.
3. Validate that a network domain (`netloc`) exists via standard URL parsing.
4. Flag missing or invalid URLs immediately with `Status: Failed`, `Error: Invalid URL format`, skipping the crawler.

### Step 2: Persistent Cache Lookup
1. Query the SQLite `cache` table using the normalized URL.
2. If hit:
   - Immediately update row with cached `linkedin_url`, `status`, `error`.
   - Mark processing time as `0` seconds.
3. If miss:
   - Dispatch job to the crawler pipeline.

### Step 3: Browser Session & Performance Optimizations
To ensure high speed and low bandwidth usage:
1. **User Agent**: Emulate a modern desktop browser (e.g., Chrome Windows).
2. **Viewport**: Set desktop dimensions (e.g., `1920x1080`).
3. **SSL Handling**: Ignore HTTPS errors to handle self-signed or misconfigured client certificates.
4. **Resource Blocking**: Abort request routes matching network resource types:
   - `image`
   - `media`
   - `font`
5. **Page Navigation Strategy**:
   - Call `goto(url)` with `domcontentloaded` wait strategy (Timeout default: 30 seconds).
   - Attempt to wait for `networkidle` state up to a short timeout (e.g., 5 seconds). Ignore timeout failures on noisy/chatty analytics sites.

### Step 4: HTML DOM Extraction & Regex Matching
1. Extract full page HTML content (`page.content()`).
2. Search all `<a>` tags and `href` attributes.
3. Match against the official **LinkedIn Regex Pattern**:
   ```regex
   https?://(www\.)?linkedin\.com/(company|school|showcase|in)/[^/\s]+
   ```
4. **Filter Out Social Share Links**:
   Ignore matches containing substring patterns like:
   - `linkedin.com/shareArticle`
   - `linkedin.com/sharing`

### Step 5: Secondary Page Fallback (About / Contact Pages)
If **no valid LinkedIn link** is found on the homepage:
1. Search DOM for `<a>` tags matching `href` containing `contact` or `about` (case-insensitive).
2. Resolve target URL:
   - If relative path (e.g., `/about-us`), join with root origin `https://domain.com/about-us`.
   - If absolute path, use as-is.
3. Navigate the browser page to the secondary URL.
4. Extract HTML content and re-execute the LinkedIn Regex parser.

### Step 6: Priority Ranking & Link Selection
If multiple valid LinkedIn links are found across a domain, select the **best match** according to business priority:

```
Priority 1: URL containing '/company/'   (e.g., linkedin.com/company/google)
Priority 2: URL containing '/showcase/'  (e.g., linkedin.com/showcase/google-cloud)
Priority 3: URL containing '/school/'    (e.g., linkedin.com/school/stanford-university)
Priority 4: URL containing '/in/'        (e.g., linkedin.com/in/john-doe)
Fallback:   First extracted URL in list
```

### Step 7: Caching & Export
1. Save result to SQLite cache database (`INSERT OR REPLACE INTO cache...`).
2. Record execution metrics (`Processed Time (s)`).
3. Append/update row in memory.
4. Allow binary output generation for CSV or XLSX formats.

---

## 5. Concurrency & Queue Architecture

To process large datasets safely and efficiently:
- **Worker Pool**: Maintain $N$ concurrent workers (default: 5, user-configurable up to 20).
- **Asynchronous Task Queue**: Feed items $(index, raw\_url)$ into a thread-safe / coroutine-safe FIFO queue.
- **Worker Throttle (Rate Limit)**: Implement a configurable delay (e.g. 1.0s) between sequential tasks handled by the same worker to prevent IP blocking.
- **Graceful Shutdown Signal**: Support a thread-safe boolean stop signal (`is_running`) to finish current in-flight workers while discarding remaining queue items.

---

## 6. Implementation Reference Code Snippets

### 6.1 Regular Expression & Rank Selection (Python Reference)

```python
import re
from bs4 import BeautifulSoup

LINKEDIN_URL_PATTERN = re.compile(
    r'https?://(www\.)?linkedin\.com/(company|school|showcase|in)/[^/\s]+', 
    re.IGNORECASE
)

def extract_linkedin_urls(html_content: str) -> list[str]:
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

def select_best_linkedin_url(urls: list[str]) -> str | None:
    if not urls:
        return None
    for priority_path in ['/company/', '/showcase/', '/school/', '/in/']:
        for url in urls:
            if priority_path in url.lower():
                return url
    return urls[0]
```

### 6.2 Equivalent Node.js / TypeScript Reference Logic

```typescript
const LINKEDIN_URL_PATTERN = /https?:\/\/(www\.)?linkedin\.com\/(company|school|showcase|in)\/[^\/\s]+/i;

function extractLinkedInUrls(html: string): string[] {
    const urlsFound: string[] = [];
    const hrefMatches = html.match(/href=["']([^"']+)["']/gi) || [];

    for (const hrefAttr of hrefMatches) {
        const href = hrefAttr.replace(/^href=["']|["']$/gi, '').trim();
        const match = href.match(LINKEDIN_URL_PATTERN);
        if (match) {
            const url = match[0];
            if (href.includes('linkedin.com/shareArticle') || href.includes('linkedin.com/sharing')) {
                continue;
            }
            if (!urlsFound.includes(url)) {
                urlsFound.push(url);
            }
        }
    }
    return urlsFound;
}

function selectBestLinkedInUrl(urls: string[]): string | null {
    if (!urls.length) return null;
    const priorities = ['/company/', '/showcase/', '/school/', '/in/'];
    for (const path of priorities) {
        const match = urls.find(url => url.toLowerCase().includes(path));
        if (match) return match;
    }
    return urls[0];
}
```

---

## 7. Recommended Tech Stacks for Rebuilding

| Stack Option | Recommended Headless Browser | HTML Parser | Database | Queue |
| :--- | :--- | :--- | :--- | :--- |
| **Node.js / TypeScript** | Playwright for Node / Puppeteer | Cheerio / jsdom | `better-sqlite3` | `p-queue` or native async channels |
| **Python** | Playwright for Python / Pyppeteer | BeautifulSoup4 / lxml | `sqlite3` | `asyncio.Queue` |
| **Go** | Rod / chromedp | `net/html` or `goquery` | `mattn/go-sqlite3` | Go channels & goroutines |
| **C# / .NET** | PuppeteerSharp / Playwright .NET | HtmlAgilityPack | `Microsoft.Data.Sqlite` | `Channel<T>` |

---

## 8. Summary Checklist for Implementation

- [ ] Implement robust column auto-detection (`website`, `url`, `domain`).
- [ ] Setup persistent SQLite caching for lookup resilience and speed.
- [ ] Configure headless browser engine to block fonts, images, and video resources.
- [ ] Implement primary homepage crawling with fallback to `/about` or `/contact` pages.
- [ ] Apply regex matching excluding social sharing URLs (`shareArticle`, `sharing`).
- [ ] Apply link selection hierarchy (`company` > `showcase` > `school` > `in`).
- [ ] Implement thread-safe/async worker pool with request throttling.
- [ ] Export enriched dataset preserving original input structure.
