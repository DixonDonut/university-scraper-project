# scraper/fetcher.py
# All scraping methods including Playwright for JS-rendered sites

import urllib.request
import ssl
import re
import json
import time
import random

# SSL context
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate',
    'Referer': 'https://www.google.com/',
    'Connection': 'keep-alive',
}

# ─────────────────────────────────────────
# METHOD 2 — urllib with browser headers
# ─────────────────────────────────────────
def fetch(url, retries=2, delay=0.5):
    """Fetch a URL with browser headers. Returns (content, final_url)."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=BROWSER_HEADERS)
            with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
                raw = r.read()
                if r.info().get('Content-Encoding') == 'gzip':
                    import gzip
                    raw = gzip.decompress(raw)
                return raw.decode('utf-8', errors='ignore'), r.geturl()
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                return None, str(e)
    return None, "Failed after retries"


def is_js_rendered(content):
    """
    Detect if a page is JavaScript-rendered and returned mostly empty.
    Returns True if the page needs Playwright to render properly.
    """
    if not content:
        return True

    # Very short content = JS shell with no real data
    if len(content) < 2000:
        return True

    content_lower = content.lower()

    # Strong signals the page is a JS shell
    js_shell_signals = [
        'you need to enable javascript',
        'please enable javascript',
        'javascript is required',
        'this site requires javascript',
        'loading...',
        'id="root"></div>',
        'id="app"></div>',
        'id="__next"></div>',
    ]
    for signal in js_shell_signals:
        if signal in content_lower:
            return True

    # Check ratio of actual text to total HTML
    # A JS shell has lots of script tags but little visible text
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(content, 'lxml')
    for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'header']):
        tag.decompose()
    visible_text = soup.get_text()
    visible_text = re.sub(r'\s+', ' ', visible_text).strip()

    # Less than 200 words of visible text = likely JS shell
    word_count = len(visible_text.split())
    if word_count < 200:
        return True

    return False


# ─────────────────────────────────────────
# METHOD 2b — Playwright (JS rendering)
# Automatically used when urllib returns empty/JS-shell page
# ─────────────────────────────────────────
def fetch_with_playwright(url, wait_seconds=3):
    """
    Fetch a URL using a real Chromium browser via Playwright.
    Handles JavaScript-rendered pages that urllib cannot read.
    Returns (content, final_url) same as fetch().
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  ⚠️  Playwright not installed. Run: pip install playwright && python3 -m playwright install chromium")
        return None, "Playwright not installed"

    print(f"  🌐 Playwright rendering: {url}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled',
                ]
            )

            context = browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                           'AppleWebKit/537.36 (KHTML, like Gecko) '
                           'Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1280, 'height': 800},
            )

            page = context.new_page()

            # Block images, fonts, media — speeds up loading
            page.route("**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,mp4,mp3}", 
                      lambda route: route.abort())

            # Navigate and wait for page to fully load
            response = page.goto(url, wait_until='networkidle', timeout=30000)
            final_url = page.url

            # Extra wait for JS to render content
            page.wait_for_timeout(wait_seconds * 1000)

            # Scroll to trigger lazy-loaded content
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1000)

            content = page.content()
            browser.close()

            print(f"  ✅ Playwright rendered ({len(content):,} chars)")
            return content, final_url

    except Exception as e:
        print(f"  ❌ Playwright failed: {e}")
        return None, str(e)


def smart_fetch(url, retries=2, delay=0.5):
    """
    Smart fetcher — tries urllib → cloudscraper → Playwright in order.
    Stops at the first method that returns substantial content.
    """
    # Method 2 — fast urllib
    content, final_url = fetch(url, retries=retries, delay=delay)
    if content and len(content) > 5000 and not is_js_rendered(content):
        return content, final_url

    # Method 2b — cloudscraper (handles Cloudflare challenges)
    cs_content, cs_url = fetch_cloudscraper(url)
    if cs_content and len(cs_content) > 5000:
        return cs_content, cs_url

    # Method 2d — Playwright stealth (true JS-rendered pages)
    if is_js_rendered(content):
        print(f"  ⚡ JS-rendered page detected — switching to Playwright")
        pw_content, pw_url = fetch_with_playwright(url)
        if pw_content and len(pw_content) > 1000:
            return pw_content, pw_url

    return content or cs_content or b"", final_url


# ─────────────────────────────────────────
# METHOD 3 — Next.js /_next/data/ API
# ─────────────────────────────────────────
def fetch_nextjs(base_url):
    """Try to fetch data from Next.js API endpoints."""
    content, _ = fetch(base_url)
    if not content:
        return None

    match = re.search(r'"buildId"\s*:\s*"([^"]+)"', content)
    if not match:
        return None

    build_id = match.group(1)
    print(f"  Found Next.js buildId: {build_id[:20]}...")

    patterns = [
        f"/_next/data/{build_id}/en/programmes.json",
        f"/_next/data/{build_id}/en/programs.json",
        f"/_next/data/{build_id}/en/courses.json",
        f"/_next/data/{build_id}/en/academics.json",
        f"/_next/data/{build_id}/en/undergraduate.json",
        f"/_next/data/{build_id}/en/study.json",
    ]

    domain = '/'.join(base_url.split('/')[:3])
    for pattern in patterns:
        data_url = domain + pattern
        data, _ = fetch(data_url)
        if data and data.strip().startswith('{'):
            try:
                return json.loads(data)
            except:
                continue

    return None


# ─────────────────────────────────────────
# METHOD 4 — DOM-Embedded JSON
# ─────────────────────────────────────────
def fetch_embedded_json(content):
    """Extract JSON data embedded in page HTML."""

    match = re.search(
        r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        content, re.DOTALL
    )
    if match:
        try:
            return json.loads(match.group(1))
        except:
            pass

    for pattern in [
        r'window\.__STATE__\s*=\s*({.*?});\s*</script>',
        r'window\.__DATA__\s*=\s*({.*?});\s*</script>',
        r'window\.__APP_STATE__\s*=\s*({.*?});\s*</script>',
        r'window\.initialData\s*=\s*({.*?});\s*</script>',
    ]:
        match = re.search(pattern, content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except:
                continue

    return None


# ─────────────────────────────────────────
# METHOD 5 — Sitemap.xml
# ─────────────────────────────────────────
def fetch_sitemap(base_url):
    """Find all programme URLs via sitemap."""
    domain = '/'.join(base_url.split('/')[:3])

    sitemaps = [
        '/sitemap.xml',
        '/sitemap_index.xml',
        '/wp-sitemap.xml',
        '/sitemap-1.xml',
        '/sitemap/sitemap.xml',
    ]

    programme_keywords = [
        'program', 'programme', 'course', 'degree', 'faculty',
        'major', 'diploma', 'associate', 'bachelor', 'study',
        'undergraduate', 'hnd', 'd3', 'd4', 'school', 'department'
    ]

    all_urls = []
    for path in sitemaps:
        content, _ = fetch(domain + path)
        if not content:
            continue

        if '<sitemapindex' in content:
            child_sitemaps = re.findall(r'<loc>(https?://[^<]+)</loc>', content)
            for child in child_sitemaps:
                child_content, _ = fetch(child)
                if child_content and '<urlset' in child_content:
                    urls = re.findall(r'<loc>(https?://[^<]+)</loc>', child_content)
                    all_urls.extend(urls)
        elif '<urlset' in content:
            urls = re.findall(r'<loc>(https?://[^<]+)</loc>', content)
            all_urls.extend(urls)

        if all_urls:
            break

    filtered = [
        u for u in all_urls
        if any(k in u.lower() for k in programme_keywords)
    ]

    print(f"  Sitemap: {len(all_urls)} total URLs, {len(filtered)} programme URLs")
    return filtered


# ─────────────────────────────────────────
# METHOD 6 — API Endpoint Discovery
# ─────────────────────────────────────────
def discover_api(base_url):
    """Try to find and use undocumented REST API endpoints."""
    domain = '/'.join(base_url.split('/')[:3])

    api_patterns = [
        '/api/programs', '/api/programmes', '/api/courses',
        '/api/faculties', '/api/degrees', '/api/diplomas',
        '/api/undergraduate', '/api/v1/programs', '/api/v2/courses',
        '/wp-json/wp/v2/pages?per_page=100',
        '/wp-json/wp/v2/posts?per_page=100&categories=programmes',
    ]

    for pattern in api_patterns:
        data, _ = fetch(domain + pattern)
        if data and len(data) > 100:
            stripped = data.strip()
            if stripped.startswith(('[', '{')):
                try:
                    return json.loads(data)
                except:
                    continue

    return None


def human_delay():
    """Random delay between 1-3 seconds like a real human."""
    time.sleep(random.uniform(1.0, 3.0))


USER_AGENTS = [
    # Chrome Mac
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    # Chrome Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    # Firefox Mac
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',
    # Safari Mac
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_1) AppleWebKit/605.1.15 Safari/604.1',
    # Chrome iPhone
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148',
]

def fetch_rotating_ua(url):
    ua = random.choice(USER_AGENTS)
    req = urllib.request.Request(url, headers={
        'User-Agent': ua,
        'Accept': 'text/html,application/xhtml+xml,*/*;q=0.9',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.google.com/',
    })
    with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
        return r.read().decode('utf-8', errors='ignore'), r.geturl()


# ─────────────────────────────────────────
# URL VERIFICATION
# ─────────────────────────────────────────
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth as stealth_sync

def fetch_stealth(url):
    """Playwright with stealth — bypasses Cloudflare JS challenges."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        stealth_sync(page)  # removes automation fingerprints
        page.goto(url, wait_until='networkidle')
        page.wait_for_timeout(3000)  # wait for Cloudflare check to pass
        content = page.content()
        browser.close()
        return content, url


def fetch_cloudscraper(url):
    """Bypass basic Cloudflare protection."""
    try:
        import cloudscraper
        scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'darwin'}
        )
        response = scraper.get(url, timeout=15)
        return response.text, response.url
    except Exception as e:
        return None, str(e)


def content_is_empty(content, min_chars=500):
    """Returns True if content is None, too short, or just a skeleton."""
    if not content:
        return True
    if len(content) < min_chars:
        return True
    return False


def _try_all_methods_on_url(url, verbose=False):
    """
    Try all fetch methods in order on a single URL.
    Returns (content, method_name) or (None, None) if all fail.
    """
    # Method 2 — urllib (works on non-Cloudflare)
    content, _ = fetch(url)
    if not content_is_empty(content):
        if verbose:
            print(f"  Method 2 (urllib) ✅")
        return content, "Method 2 (urllib)"

    human_delay()

    # Method 2b — cloudscraper (Cloudflare basic)
    content, _ = fetch_cloudscraper(url)
    if not content_is_empty(content):
        if verbose:
            print(f"  Method 2b (cloudscraper) ✅")
        return content, "Method 2b (cloudscraper)"

    human_delay()

    # Method 2c — rotating user agents
    content, _ = fetch_rotating_ua(url)
    if not content_is_empty(content):
        if verbose:
            print(f"  Method 2c (rotating UA) ✅")
        return content, "Method 2c (rotating UA)"

    human_delay()

    # Method 2d — Playwright stealth (Cloudflare JS)
    try:
        content, _ = fetch_stealth(url)
        if not content_is_empty(content):
            if verbose:
                print(f"  Method 2d (Playwright stealth) ✅")
            return content, "Method 2d (Playwright stealth)"
    except Exception as e:
        if verbose:
            print(f"  Method 2d (Playwright stealth) ❌ {e}")

    return None, None


def verify_url(url):
    """Check if URL returns real content."""
    if not url or not url.startswith('http'):
        return False, "Invalid URL"

    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=8, context=ctx) as r:
            final_url = r.geturl()
            status = r.status
            domain = '/'.join(url.split('/')[:3])
            if final_url.rstrip('/') == domain:
                return False, "Redirects to homepage"
            return status == 200, final_url
    except urllib.error.HTTPError as e:
        if e.code == 503:
            return None, f"503 — may work in browser"
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)
