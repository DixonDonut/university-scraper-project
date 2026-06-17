# scraper/fetcher.py
# All 9 scraping methods from SCRAPING_METHODS.md

import urllib.request
import ssl
import re
import json
import time

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
                # Handle gzip
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


# ─────────────────────────────────────────
# METHOD 3 — Next.js /_next/data/ API
# ─────────────────────────────────────────
def fetch_nextjs(base_url):
    """Try to fetch data from Next.js API endpoints."""
    content, _ = fetch(base_url)
    if not content:
        return None

    # Find buildId
    match = re.search(r'"buildId"\s*:\s*"([^"]+)"', content)
    if not match:
        return None

    build_id = match.group(1)
    print(f"  Found Next.js buildId: {build_id[:20]}...")

    # Common programme data URL patterns
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

    # Try __NEXT_DATA__
    match = re.search(
        r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        content, re.DOTALL
    )
    if match:
        try:
            return json.loads(match.group(1))
        except:
            pass

    # Try window.__STATE__ / window.__DATA__ / window.__APP_STATE__
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
            # Index sitemap — find child sitemaps
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

    # Filter for programme-related URLs
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


# ─────────────────────────────────────────
# URL VERIFICATION
# ─────────────────────────────────────────
def verify_url(url):
    """
    Check if URL returns real content.
    Returns (is_valid, final_url_or_error)
    """
    if not url or not url.startswith('http'):
        return False, "Invalid URL"

    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=8, context=ctx) as r:
            final_url = r.geturl()
            status = r.status

            # Check for silent redirect to homepage
            domain = '/'.join(url.split('/')[:3])
            if final_url.rstrip('/') == domain:
                return False, "Redirects to homepage"

            return status == 200, final_url
    except urllib.error.HTTPError as e:
        # 503 from scraper ≠ broken — flag as NMC but include
        if e.code == 503:
            return None, f"503 — may work in browser"
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)
