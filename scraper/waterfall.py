# scraper/waterfall.py
# Fully autonomous 9-method waterfall scraper.
# Tries every method automatically. Never stops to ask.
# Based on SCRAPING_METHODS.md priority order.

import re
import json
import time
import subprocess
import os
import urllib.request
import ssl

from scraper.fetcher import fetch, fetch_nextjs, fetch_embedded_json, fetch_sitemap, discover_api
from scraper.parser import parse_programmes, parse_json_programmes, is_same_domain, is_genuine_programme_page

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# ─────────────────────────────────────────────────────────
# DOMAIN METHOD CACHE
# After any successful fetch, record which method worked.
# Future requests to the same domain skip straight to it.
# ─────────────────────────────────────────────────────────

DOMAIN_METHOD_CACHE = {}  # domain -> fetch_fn


def _domain_of(url):
    """Extract scheme + netloc from a URL."""
    parts = url.split('/')
    return '/'.join(parts[:3]) if len(parts) >= 3 else url


def record_successful_method(url, fetch_fn):
    """Store which fetch function worked for this domain."""
    DOMAIN_METHOD_CACHE[_domain_of(url)] = fetch_fn


def get_cached_method(url):
    """Return the cached fetch function for this domain, or None."""
    return DOMAIN_METHOD_CACHE.get(_domain_of(url))

# ─────────────────────────────────────────────────────────
# FAILURE DETECTION
# How to know a method failed and we should try the next one
# ─────────────────────────────────────────────────────────

def content_is_empty(content, min_chars=500):
    """Returns True if content is too short to contain programme data."""
    if not content:
        return True
    if len(content) < min_chars:
        return True
    return False


def content_has_programmes(content):
    """
    Returns True if the content likely contains programme data.
    Used to confirm a method succeeded before moving on.
    """
    if not content:
        return False

    text = content.lower()

    strong_signals = [
        'bachelor of', 'bachelor in', "bachelor's",
        'b.sc', 'b.a.', 'bba ', 'bfa ', 'b.tech', 'b.e.',
        'associate of', 'associate degree',
        'diploma in', 'diploma of', 'hnd ',
        'undergraduate program', 'undergraduate programme',
        'degree program', 'degree programme',
        'major in', 'majors',
    ]

    count = sum(1 for s in strong_signals if s in text)
    return count >= 2


def parse_result_has_data(programmes):
    """Returns True if a parsed result list has actual programme data."""
    return programmes and len(programmes) >= 1


# ─────────────────────────────────────────────────────────
# METHOD 7 — Google/DuckDuckGo Search
# For bot-blocked sites where search engines have indexed pages
# ─────────────────────────────────────────────────────────

def search_for_programme_pages(homepage_url, university_name=""):
    """
    Use DuckDuckGo (no API key needed) to find programme listing
    pages for a university that blocks direct scraping.
    Returns list of URLs to try.
    """
    domain = homepage_url.split('/')[2]
    uni_name = university_name or domain

    queries = [
        f"site:{domain} undergraduate programs bachelor",
        f"site:{domain} undergraduate programmes bachelor",
        f"site:{domain} degrees majors list",
        f"site:{domain} bachelor diploma associate",
        f'"{uni_name}" undergraduate programs list bachelor degrees',
    ]

    found_urls = []

    for query in queries[:3]:
        try:
            # DuckDuckGo lite — no JS, no API key
            encoded = urllib.request.quote(query)
            search_url = f"https://lite.duckduckgo.com/lite/?q={encoded}"
            req = urllib.request.Request(search_url, headers={
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'text/html',
            })
            with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
                html = r.read().decode('utf-8', errors='ignore')

            # Extract URLs from search results
            urls = re.findall(r'href="(https?://[^"]+)"', html)
            for url in urls:
                # Only keep URLs from the target domain
                if domain in url and url not in found_urls:
                    # Filter out nav/utility pages
                    skip = ['login', 'news', 'event', 'alumni', 'donate',
                           'library', 'sport', 'research', 'contact', 'about']
                    if not any(s in url.lower() for s in skip):
                        found_urls.append(url)

            time.sleep(0.5)  # polite delay between searches

        except Exception as e:
            print(f"  Search error: {e}")
            continue

    return found_urls[:10]


# ─────────────────────────────────────────────────────────
# METHOD 8 — PDF Detection and Extraction
# ─────────────────────────────────────────────────────────

def find_and_extract_pdfs(homepage_url):
    """
    Find PDF links on the homepage and nearby pages,
    then extract text from them looking for programme lists.
    Returns (content_text, pdf_url) or (None, None)
    """
    print("  → Method 8: PDF detection...")

    # Fetch homepage to find PDF links
    content, _ = fetch(homepage_url)
    if not content:
        return None, None

    # Find PDF URLs
    pdf_patterns = [
        r'href="([^"]*\.pdf[^"]*)"',
        r"href='([^']*\.pdf[^']*)'",
        r'"(https?://[^"]*\.pdf[^"]*)"',
    ]

    pdf_urls = []
    for pattern in pdf_patterns:
        urls = re.findall(pattern, content, re.IGNORECASE)
        for url in urls:
            if not url.startswith('http'):
                domain = '/'.join(homepage_url.split('/')[:3])
                url = domain + url if url.startswith('/') else domain + '/' + url

            # Prioritise likely programme-related PDFs
            url_lower = url.lower()
            priority_keywords = [
                'programme', 'program', 'course', 'degree', 'undergraduate',
                'prospectus', 'handbook', 'catalog', 'catalogue', 'guide',
                'bachelor', 'diploma', 'associate', 'academic',
            ]
            if any(k in url_lower for k in priority_keywords):
                pdf_urls.insert(0, url)  # high priority
            else:
                pdf_urls.append(url)

    if not pdf_urls:
        print("  ❌ Method 8: No PDFs found")
        return None, None

    print(f"  Found {len(pdf_urls)} PDFs, trying top 3...")

    # Try to extract text from each PDF
    for pdf_url in pdf_urls[:3]:
        try:
            # Download the PDF
            req = urllib.request.Request(pdf_url, headers={
                'User-Agent': 'Mozilla/5.0',
                'Referer': homepage_url,
            })
            with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
                pdf_bytes = r.read()

            # Save temporarily
            tmp_path = '/tmp/university_scraper_temp.pdf'
            with open(tmp_path, 'wb') as f:
                f.write(pdf_bytes)

            # Extract text using pdftotext (if available) or pdfminer
            text = None

            # Try pdftotext first (fastest)
            result = subprocess.run(
                ['pdftotext', tmp_path, '-'],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0 and result.stdout:
                text = result.stdout

            # Fallback to pdfminer
            if not text:
                try:
                    from pdfminer.high_level import extract_text as pdf_extract
                    text = pdf_extract(tmp_path)
                except Exception:
                    pass

            # Clean up
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

            if text and content_has_programmes(text):
                print(f"  ✅ Method 8: Found programme data in PDF: {pdf_url}")
                return text, pdf_url

        except Exception as e:
            print(f"  PDF error ({pdf_url[:50]}): {e}")
            continue

    print("  ❌ Method 8: No useful programme data in PDFs")
    return None, None


# ─────────────────────────────────────────────────────────
# URL CANDIDATE GENERATION
# When the main URL fails, automatically generate alternatives
# ─────────────────────────────────────────────────────────

COUNTRY_URL_PATTERNS = {
    'UK': [
        '/study/undergraduate/courses/course-listing',
        '/study/undergraduate/courses',
        '/undergraduate/courses',
        '/courses/undergraduate',
        '/study/courses',
        '/programmes',
    ],
    'USA': [
        '/academics/programs',
        '/academics/majors',
        '/admissions/undergraduate-admissions/academic-programs.html',
        '/programs',
        '/undergraduate/programs',
        '/academics/undergraduate',
        '/admission/academics/majors',
    ],
    'CANADA': [
        '/programs',
        '/future-students/programs',
        '/undergraduate/programs',
        '/academics/programs',
        '/programs/undergraduate',
    ],
    'AUSTRALIA': [
        '/courses/undergraduate',
        '/study/undergraduate',
        '/courses',
        '/study/courses',
        '/programs',
    ],
    'INDIA': [
        '/academics/integrated-first-degree',
        '/academics/programs',
        '/programmes',
        '/departments',
        '/academics',
        '/courses',
    ],
    'KOREA': [
        '/en/academics/undergraduate',
        '/academics/undergraduate',
        '/en/programs',
        '/admission/programs',
    ],
    'JAPAN': [
        '/en/academics/undergraduate',
        '/en/programs',
        '/academics',
        '/en/admissions',
    ],
    'INDONESIA': [
        '/program',
        '/programs',
        '/akademik/program-studi',
        '/fakultas',
        '/prodi',
    ],
}

GENERIC_URL_PATTERNS = [
    '/study/undergraduate',
    '/programmes/undergraduate',
    '/academics/programs',
    '/undergraduate/programs',
    '/courses/undergraduate',
    '/degrees',
    '/faculties',
    '/departments',
    '/schools',
    '/academics',
    '/study',
]


def generate_url_candidates(homepage_url, country='Unknown'):
    """
    Generate list of URLs to try automatically when homepage fails.
    Country-specific patterns first, then generic ones.
    """
    domain = '/'.join(homepage_url.split('/')[:3])
    candidates = []

    # Country-specific patterns
    country_upper = country.upper()
    if country_upper in COUNTRY_URL_PATTERNS:
        for pattern in COUNTRY_URL_PATTERNS[country_upper]:
            candidates.append(domain + pattern)

    # Generic patterns
    for pattern in GENERIC_URL_PATTERNS:
        url = domain + pattern
        if url not in candidates:
            candidates.append(url)

    return candidates


# ─────────────────────────────────────────────────────────
# THE FULL AUTONOMOUS WATERFALL
# ─────────────────────────────────────────────────────────

def run_waterfall(homepage_url, country='Unknown', university_name='',
                  verbose=False):
    """
    Run the full 9-method waterfall autonomously.
    Never stops to ask. Tries every method until something works.

    Returns (programmes_list, method_used, source_url)
    or (None, 'all_failed', None) if everything fails.
    """

    print(f"\n  🌊 Starting autonomous waterfall...")
    domain = '/'.join(homepage_url.split('/')[:3])

    # ── Stage 1: Try the homepage URL with all methods
    programmes, method, url = _try_all_methods_on_url(
        homepage_url, verbose=verbose
    )
    if programmes:
        return programmes, method, url

    # ── Stage 2: Try country-specific and generic URL candidates
    print(f"\n  🔄 Homepage failed — trying alternative URLs automatically...")
    candidates = generate_url_candidates(homepage_url, country)

    for candidate_url in candidates:
        if verbose:
            print(f"  → Trying: {candidate_url}")

        programmes, method, url = _try_all_methods_on_url(
            candidate_url, verbose=verbose
        )
        if programmes:
            print(f"  ✅ Found data at: {candidate_url}")
            return programmes, method, url

        time.sleep(0.3)

    # ── Stage 3: Google/DuckDuckGo search for programme pages
    print(f"\n  🔍 Trying web search for programme pages (Method 7)...")
    search_urls = search_for_programme_pages(homepage_url, university_name)

    if search_urls:
        print(f"  Found {len(search_urls)} URLs from search")
        for search_url in search_urls:
            if verbose:
                print(f"  → Trying search result: {search_url}")

            programmes, method, url = _try_all_methods_on_url(
                search_url, verbose=verbose
            )
            if programmes:
                print(f"  ✅ Found data via search: {search_url}")
                return programmes, f"Search + {method}", url

            time.sleep(0.3)

    # ── Stage 4: PDF extraction (Method 8)
    pdf_text, pdf_url = find_and_extract_pdfs(homepage_url)
    if pdf_text:
        programmes = parse_programmes(pdf_text, pdf_url or homepage_url)
        if parse_result_has_data(programmes):
            print(f"  ✅ Found data in PDF: {pdf_url}")
            return programmes, "PDF extraction", pdf_url

    # ── Stage 5: Try subdomains commonly used by universities
    print(f"\n  🔄 Trying common subdomains...")
    subdomains = ['admission', 'admissions', 'www', 'study',
                  'undergraduate', 'academics', 'catalog']

    base_domain = domain.split('://')[-1]
    # Remove existing subdomain
    parts = base_domain.split('.')
    if len(parts) > 2:
        root_domain = '.'.join(parts[-2:])
    else:
        root_domain = base_domain

    for sub in subdomains:
        sub_url = f"https://{sub}.{root_domain}"
        if sub_url == homepage_url or sub_url == domain:
            continue

        if verbose:
            print(f"  → Trying subdomain: {sub_url}")

        content, _ = fetch(sub_url)
        if content and len(content) > 2000:
            programmes = parse_programmes(content, sub_url)
            if parse_result_has_data(programmes):
                print(f"  ✅ Found data at subdomain: {sub_url}")
                return programmes, "Subdomain discovery", sub_url

        time.sleep(0.3)

    # ── All methods exhausted
    print(f"\n  ❌ All 9 methods exhausted for {university_name or domain}")
    print(f"  This site may require manual handling.")
    return None, "all_failed", None


def _fetch_with_cache(url, verbose=False):
    """
    Fetch a URL using the cached method for its domain if available,
    otherwise try all methods in order and cache the winner.
    Returns (content, final_url, fetch_fn_name).
    """
    cached_fn = get_cached_method(url)
    if cached_fn is not None:
        content, final_url = cached_fn(url)
        if not content_is_empty(content):
            return content, final_url, cached_fn.__name__
        # Cached method failed this time — fall through to full waterfall

    # Try fetch methods in order
    from scraper.fetcher import fetch_cloudscraper, fetch_rotating_ua
    for fn, label in [
        (fetch,              'fetch'),
        (fetch_cloudscraper, 'fetch_cloudscraper'),
        (fetch_rotating_ua,  'fetch_rotating_ua'),
    ]:
        try:
            content, final_url = fn(url)
            if not content_is_empty(content):
                record_successful_method(url, fn)
                return content, final_url, label
        except Exception:
            continue

    return None, url, None


def _try_all_methods_on_url(url, verbose=False):
    """
    Try all fetch methods on a single URL.
    Returns (programmes, method_name, url) or (None, None, None).
    """

    # ── Method 2: urllib with browser headers (cache-aware)
    content, final_url, fetch_label = _fetch_with_cache(url, verbose=verbose)
    if not content_is_empty(content):
        if verbose:
            print(f"  Method 2 ✅ ({len(content):,} chars)")

        # Try Method 3 (Next.js) on this content
        programmes = _try_nextjs(url, content)
        if programmes:
            return programmes, "Method 3 (Next.js API)", url

        # Try Method 4 (DOM JSON) on this content
        programmes = _try_dom_json(content, url)
        if programmes:
            return programmes, "Method 4 (DOM JSON)", url

        # Parse the HTML directly
        if content_has_programmes(content):
            programmes = parse_programmes(content, url)
            if parse_result_has_data(programmes):
                return programmes, "Method 2 (urllib)", url

    # ── Method 5: Sitemap
    if verbose:
        print(f"  Trying Method 5 (sitemap)...")
    sitemap_urls = [u for u in fetch_sitemap(url) if is_same_domain(u, url)]
    if sitemap_urls:
        all_programmes = []
        for smap_url in sitemap_urls[:30]:
            page_content, _, _ = _fetch_with_cache(smap_url, verbose=False)
            if page_content and is_genuine_programme_page(page_content):
                found = parse_programmes(page_content, smap_url)
                all_programmes.extend(found)
            time.sleep(0.2)
        if parse_result_has_data(all_programmes):
            return all_programmes, "Method 5 (Sitemap)", url

    # ── Method 6: API discovery
    if verbose:
        print(f"  Trying Method 6 (API)...")
    api_data = discover_api(url)
    if api_data:
        programmes = parse_json_programmes(api_data, url)
        if parse_result_has_data(programmes):
            return programmes, "Method 6 (API)", url

    # ── Playwright (JS rendering) — for JS-heavy pages
    try:
        from scraper.fetcher import fetch_with_playwright, is_js_rendered
        if is_js_rendered(content):
            if verbose:
                print(f"  Trying Playwright (JS rendering)...")
            pw_content, pw_url = fetch_with_playwright(url)
            if pw_content and content_has_programmes(pw_content):
                programmes = parse_programmes(pw_content, pw_url)
                if parse_result_has_data(programmes):
                    return programmes, "Playwright (JS)", url

                # Try Next.js on Playwright content too
                programmes = _try_nextjs(url, pw_content)
                if programmes:
                    return programmes, "Playwright + Next.js", url

    except Exception as e:
        if verbose:
            print(f"  Playwright error: {e}")

    return None, None, None


def _try_nextjs(base_url, content):
    """Try Next.js API endpoint extraction."""
    if not content:
        return None
    match = re.search(r'"buildId"\s*:\s*"([^"]+)"', content)
    if not match:
        return None

    build_id = match.group(1)
    domain = '/'.join(base_url.split('/')[:3])

    patterns = [
        f"/_next/data/{build_id}/en/programmes.json",
        f"/_next/data/{build_id}/en/programs.json",
        f"/_next/data/{build_id}/en/courses.json",
        f"/_next/data/{build_id}/en/academics.json",
        f"/_next/data/{build_id}/en/undergraduate.json",
        f"/_next/data/{build_id}/en/degrees.json",
        f"/_next/data/{build_id}/en/study.json",
    ]

    for pattern in patterns:
        data_url = domain + pattern
        data, _ = fetch(data_url)
        if data and data.strip().startswith('{'):
            try:
                parsed = json.loads(data)
                programmes = parse_json_programmes(parsed, base_url)
                if programmes:
                    return programmes
            except:
                continue

    return None


def _try_dom_json(content, base_url):
    """Try DOM-embedded JSON extraction."""
    from scraper.fetcher import fetch_embedded_json
    data = fetch_embedded_json(content)
    if data:
        programmes = parse_json_programmes(data, base_url)
        if programmes:
            return programmes
    return None
