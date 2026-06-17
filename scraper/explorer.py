# scraper/explorer.py
# Automatically finds programme listing pages from any university homepage.
# No universities.txt needed — just paste the homepage URL.

import re
import time
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────────────────
# SCORING — how likely is this link/URL to be a programme page?
# Higher score = more likely = visit this first
# ─────────────────────────────────────────────────────────

# URL keywords — found in the href
URL_HIGH_SCORE = [
    'undergraduate', 'programmes', 'programs', 'courses',
    'bachelor', 'diploma', 'associate', 'degrees',
    'study-with-us', 'study', 'academics', 'faculties',
    'schools', 'departments', 'majors', 'course-listing',
    'programme-listing', 'our-courses', 'what-we-offer',
    'd3', 'd4', 'hnd', 's1',
]

URL_MED_SCORE = [
    'faculty', 'school', 'college', 'department',
    'admissions', 'apply', 'explore', 'discover',
    'education', 'learning', 'academic',
]

# Text keywords — found in the link text or nearby heading
TEXT_HIGH_SCORE = [
    'undergraduate programmes', 'undergraduate programs',
    'bachelor', 'courses', 'programmes', 'programs',
    'what can i study', 'what to study', 'our courses',
    'degrees', 'study options', 'study with us',
    'faculties and schools', 'schools and faculties',
    'academic programmes', 'academic programs',
    'diploma', 'associate degree', 'find a course',
    'browse courses', 'explore programmes',
]

TEXT_MED_SCORE = [
    'study', 'academics', 'faculties', 'schools',
    'departments', 'apply', 'admission',
]

# If any of these appear in the URL, skip it entirely
SKIP_URL_CONTAINS = [
    'login', 'logout', 'sign-in', 'register',
    'news', 'event', 'blog', 'media', 'gallery',
    'alumni', 'donate', 'shop', 'store',
    'library', 'sport', 'hostel', 'accommodation',
    'research', 'staff', 'jobs', 'career', 'vacancy',
    'contact', 'about', 'history', 'governance',
    'sustainability', 'privacy', 'cookie', 'terms',
    'facebook', 'twitter', 'instagram', 'linkedin',
    'youtube', 'tiktok', 'mailto:', 'tel:', 'javascript:',
    '.pdf', '.doc', '.jpg', '.png', '#',
]

# Country-specific known programme page URL patterns
# Used as direct hints when homepage exploration is not enough
COUNTRY_HINTS = {
    'UK': [
        '/study/undergraduate/courses',
        '/study/undergraduate/courses/course-listing',
        '/undergraduate/courses',
        '/courses/undergraduate',
        '/study/courses',
    ],
    'USA': [
        '/academics/programs',
        '/academics/majors',
        '/admissions/undergraduate-admissions/academic-programs.html',
        '/programs',
        '/undergraduate/programs',
    ],
    'CANADA': [
        '/programs',
        '/future-students/programs',
        '/undergraduate/programs',
        '/academics/programs',
    ],
    'AUSTRALIA': [
        '/courses/undergraduate',
        '/study/undergraduate',
        '/courses',
        '/study/courses',
    ],
    'INDIA': [
        '/academics/integrated-first-degree',
        '/academics/programs',
        '/programmes',
        '/departments',
        '/academics',
    ],
    'KOREA': [
        '/en/academics/undergraduate',
        '/academics/undergraduate',
        '/en/programs',
    ],
    'JAPAN': [
        '/en/academics/undergraduate',
        '/en/programs',
        '/academics',
    ],
    'INDONESIA': [
        '/program',
        '/programs',
        '/akademik/program-studi',
        '/fakultas',
    ],
}


def score_link(href, text):
    """
    Score a link by how likely it leads to a programme listing page.
    Returns integer score. Higher = more likely.
    """
    if not href:
        return 0

    href_lower = href.lower()
    text_lower = text.lower().strip()

    # Skip if any skip pattern found
    for skip in SKIP_URL_CONTAINS:
        if skip in href_lower:
            return 0

    score = 0

    # URL scoring
    for keyword in URL_HIGH_SCORE:
        if keyword in href_lower:
            score += 10

    for keyword in URL_MED_SCORE:
        if keyword in href_lower:
            score += 5

    # Text scoring
    for keyword in TEXT_HIGH_SCORE:
        if keyword in text_lower:
            score += 15

    for keyword in TEXT_MED_SCORE:
        if keyword in text_lower:
            score += 5

    # Bonus: text and URL both match — very likely a programme page
    if score >= 10 and score >= 15:
        score += 10

    # Penalty: very short text is probably a nav button not a section
    if len(text_lower) < 4:
        score -= 5

    return score


def extract_links(html, base_url):
    """
    Extract all links from a page with their scores.
    Returns sorted list of (score, url, text) tuples.
    """
    soup = BeautifulSoup(html, 'lxml')
    domain = '{uri.scheme}://{uri.netloc}'.format(uri=urlparse(base_url))

    seen = set()
    scored_links = []

    for tag in soup.find_all('a', href=True):
        href = tag.get('href', '').strip()
        text = tag.get_text(separator=' ', strip=True)
        text = re.sub(r'\s+', ' ', text)

        if not href or not text:
            continue

        # Build absolute URL
        if href.startswith('http'):
            full_url = href
        elif href.startswith('/'):
            full_url = domain + href
        else:
            full_url = urljoin(base_url, href)

        # Only follow links on same domain
        if domain.replace('www.', '') not in full_url.replace('www.', ''):
            continue

        # Deduplicate
        url_key = full_url.rstrip('/')
        if url_key in seen:
            continue
        seen.add(url_key)

        s = score_link(full_url, text)
        if s > 0:
            scored_links.append((s, full_url, text))

    # Sort by score descending
    scored_links.sort(key=lambda x: x[0], reverse=True)
    return scored_links


def detect_country(html, homepage_url):
    """
    Try to detect the country from the homepage content and URL.
    Returns country string like 'UK', 'USA', 'India' etc.
    """
    url_lower = homepage_url.lower()
    html_lower = html.lower() if html else ''

    # TLD detection
    tld_map = {
        '.ac.uk': 'UK', '.edu': 'USA', '.ac.in': 'India',
        '.ca': 'CANADA', '.edu.au': 'AUSTRALIA', '.ac.au': 'AUSTRALIA',
        '.ac.kr': 'KOREA', '.ac.jp': 'JAPAN', '.ac.id': 'INDONESIA',
        '.edu.sg': 'SINGAPORE', '.ac.nz': 'NEW ZEALAND',
        '.de': 'GERMANY', '.fr': 'FRANCE', '.es': 'SPAIN',
        '.ru': 'RUSSIA', '.cn': 'CHINA',
    }

    for tld, country in tld_map.items():
        if tld in url_lower:
            return country

    # Content hints
    content_hints = {
        'INDIA': ['indian', 'india', 'ugc', 'aicte', 'naac', 'iit', 'nit'],
        'UK': ['ucas', 'a-levels', 'a levels', 'united kingdom'],
        'USA': ['common app', 'sat score', 'act score', 'gpa'],
        'CANADA': ['ontario', 'british columbia', 'quebec', 'cégep'],
        'AUSTRALIA': ['cricos', 'atar', 'tafe', 'australia'],
    }

    for country, hints in content_hints.items():
        if any(h in html_lower for h in hints):
            return country

    return 'Unknown'


def find_programme_pages(homepage_url, fetch_fn, max_candidates=8, verbose=False):
    """
    Main entry point. Given a homepage URL, finds the best programme
    listing pages to scrape.

    Returns list of (url, page_content) tuples ready for parsing.
    """
    print(f"\n  🔍 Exploring: {homepage_url}")

    # Step 1 — fetch homepage
    homepage_content, final_url = fetch_fn(homepage_url)

    if not homepage_content:
        print(f"  ❌ Could not fetch homepage")
        return []

    print(f"  ✅ Homepage fetched ({len(homepage_content):,} chars)")

    # Step 2 — detect country
    country = detect_country(homepage_content, homepage_url)
    print(f"  🌍 Detected country: {country}")

    # Step 3 — extract and score all links
    scored_links = extract_links(homepage_content, homepage_url)
    print(f"  🔗 Found {len(scored_links)} candidate links")

    if verbose:
        print(f"\n  Top 10 candidates:")
        for score, url, text in scored_links[:10]:
            print(f"    [{score:3d}] {text[:40]:<40} → {url}")

    # Step 4 — add country-specific hints
    domain = '{uri.scheme}://{uri.netloc}'.format(uri=urlparse(homepage_url))
    hints = COUNTRY_HINTS.get(country, [])
    hint_urls = [(50, domain + h, f'Country hint: {h}') for h in hints]

    # Combine scored links + hints, deduplicate
    all_candidates = scored_links + hint_urls
    seen = set()
    unique_candidates = []
    for score, url, text in all_candidates:
        key = url.rstrip('/')
        if key not in seen:
            seen.add(key)
            unique_candidates.append((score, url, text))

    unique_candidates.sort(key=lambda x: x[0], reverse=True)

    # Step 5 — visit top candidates and check if they have programme data
    print(f"\n  📄 Visiting top {max_candidates} candidates...")
    programme_pages = []
    visited = 0

    for score, url, text in unique_candidates[:max_candidates * 2]:
        if visited >= max_candidates:
            break

        if verbose:
            print(f"  → [{score:3d}] {url}")

        page_content, _ = fetch_fn(url)
        time.sleep(0.4)  # polite delay

        if not page_content or len(page_content) < 500:
            if verbose:
                print(f"       Empty page — skipped")
            continue

        # Check if this page actually has programme-like content
        content_score = score_page_content(page_content)

        if content_score > 0:
            print(f"  ✅ Programme page found [{content_score}]: {url}")
            programme_pages.append((url, page_content))
            visited += 1
        else:
            if verbose:
                print(f"       No programme content — skipped")

    if not programme_pages:
        print(f"  ⚠️  No programme pages found from homepage exploration")
        print(f"  💡 Try passing a more specific URL directly")

    return programme_pages, country


def score_page_content(html):
    """
    Score a page by how much programme data it contains.
    Returns 0 if page has no programme content.
    """
    soup = BeautifulSoup(html, 'lxml')

    # Remove nav/footer noise
    for tag in soup.find_all(['nav', 'footer', 'script', 'style']):
        tag.decompose()

    text = soup.get_text().lower()
    score = 0

    # Strong signals — this page has actual programme listings
    strong_signals = [
        'bachelor of', 'bachelor in', 'b.sc', 'b.a ', 'b.tech',
        'bba ', 'beng', 'b.e.', 'llb', 'diploma in', 'associate of',
        'hnd ', 'foundation degree', 'undergraduate programme',
        'undergraduate program', 'degree programme', 'degree program',
    ]

    for signal in strong_signals:
        count = text.count(signal)
        if count > 0:
            score += count * 10

    # Moderate signals — may contain programmes
    moderate_signals = [
        'study', 'course', 'programme', 'program', 'degree',
        'faculty', 'school', 'department', 'major',
    ]

    for signal in moderate_signals:
        count = text.count(signal)
        if count > 2:  # more than 2 mentions = likely relevant
            score += min(count, 10) * 2

    return score
