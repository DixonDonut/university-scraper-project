# scraper/parser.py
# Handles: degree pages, subject-only pages, concentration detection,
# department page lists, deep crawling

import re
from bs4 import BeautifulSoup
from scraper.rules import (
    format_programme_name, format_unclear_degree,
    infer_degree_level_from_duration, normalise_degree_type,
    concentrations_chosen_at_application, concentrations_listed_separately,
    CONCENTRATION_INTRO_WORDS,
)

# ─────────────────────────────────────────────────────────
# SIGNALS
# ─────────────────────────────────────────────────────────

DEGREE_TEXT_SIGNALS = [
    'b.e', 'b.tech', 'btech', 'b.sc', 'bsc', 'b.a', 'bba',
    'b.com', 'b.pharm', 'b.arch', 'llb', 'b.ed', 'bachelor',
    'diploma in', 'diploma of', 'advanced diploma', 'hnd',
    'diploma iii', 'diploma iv', 'associate', 'foundation degree',
    'bfa', 'bca', 'beng',
]

PROGRAMME_URL_PATTERNS = [
    'programme', 'program', 'course', 'degree', 'bachelor',
    'diploma', 'associate', 'undergraduate', 'faculty', 'school',
    'department', 'major', 'study', 'academics', 'hnd', 'catalog',
]

SKIP_URL_PATTERNS = [
    'login', 'logout', 'search', 'news', 'event', 'contact',
    'about', 'alumni', 'portal', 'hostel', 'library', 'sport',
    'research', 'placement', 'scholarship', 'fee', 'sitemap',
    'privacy', 'cookie', 'terms', 'disclaimer', 'giving', 'donate',
    'facebook', 'twitter', 'linkedin', 'instagram', 'youtube',
    '#', 'javascript:', 'mailto:', 'tel:',
]

# Duration patterns for fallback detection
DURATION_PATTERNS = [
    r'(\d+)[- ]year',
    r'(\d+)\s*years',
    r'(\d+)\s*credit hours',
    r'(\d+)\s*credits',
    r'(\d+)\s*units',
    r'(\d+)\s*ects',
]


# ─────────────────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────────────────

def clean_text(text):
    text = re.sub(r'\s+', ' ', text).strip()
    return text.replace('\n', ' ').replace('\t', ' ')


def is_skip_url(href):
    if not href:
        return True
    href_lower = href.lower()
    return any(p in href_lower for p in SKIP_URL_PATTERNS)


def looks_like_degree(text, href=""):
    text_lower = text.lower()
    href_lower = href.lower() if href else ""
    for signal in DEGREE_TEXT_SIGNALS:
        if signal in text_lower:
            return True
    for signal in PROGRAMME_URL_PATTERNS:
        if signal in href_lower:
            return True
    return False


def extract_duration(text):
    """Extract duration string from page text."""
    for pattern in DURATION_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0)
    return None


def build_url(href, base_url):
    """Build absolute URL from href and base."""
    if not href:
        return ''
    if href.startswith('http'):
        return href
    if href.startswith('/'):
        parts = base_url.split('/')
        domain = '/'.join(parts[:3])
        return domain + href
    return base_url.rstrip('/') + '/' + href.lstrip('/')


# ─────────────────────────────────────────────────────────
# CONCENTRATION EXTRACTION
# ─────────────────────────────────────────────────────────

def extract_concentrations(soup, section_heading=None):
    """
    Extract concentrations/tracks/emphasis from a programme page.
    Returns list of concentration name strings.
    """
    concentrations = []
    text = soup.get_text().lower()

    # Find sections introduced by concentration keywords
    for heading in soup.find_all(['h2', 'h3', 'h4', 'h5', 'strong', 'b']):
        heading_text = heading.get_text().lower().strip()

        # Check if this heading introduces a concentration list
        if any(word in heading_text for word in CONCENTRATION_INTRO_WORDS):
            # Get the next list element
            next_el = heading.find_next_sibling()
            if not next_el:
                next_el = heading.parent.find_next_sibling()

            if next_el and next_el.name in ['ul', 'ol']:
                for item in next_el.find_all('li'):
                    name = clean_text(item.get_text())
                    if name and 5 < len(name) < 80:
                        # Filter out obviously non-programme items
                        if not any(skip in name.lower() for skip in [
                            'credit', 'prerequisite', 'require',
                            'contact', 'advisor', 'learn more'
                        ]):
                            concentrations.append(name)

            # Also check for inline comma-separated list
            elif next_el:
                next_text = next_el.get_text()
                if ',' in next_text and len(next_text) < 500:
                    items = [c.strip() for c in next_text.split(',')]
                    for item in items:
                        item = clean_text(item)
                        if item and 3 < len(item) < 60:
                            concentrations.append(item)

    # Also look for definition lists (dl/dt/dd pattern)
    for dl in soup.find_all('dl'):
        dl_text = dl.get_text().lower()
        if any(word in dl_text for word in CONCENTRATION_INTRO_WORDS):
            for dt in dl.find_all('dt'):
                name = clean_text(dt.get_text())
                if name and 3 < len(name) < 80:
                    concentrations.append(name)

    # Deduplicate
    seen = set()
    unique = []
    for c in concentrations:
        key = c.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique


# ─────────────────────────────────────────────────────────
# DEGREE TYPE DETECTION FROM PAGE
# ─────────────────────────────────────────────────────────

def detect_degree_type_from_page(soup, page_text):
    """
    Try to find the degree type from a page that only lists
    the subject name (e.g. 'Economics Department' page).

    Returns (degree_type_string, subject_string) or (None, None)
    """
    text_lower = page_text.lower()

    # Pattern: "Bachelor of Arts in Economics" anywhere in page
    patterns = [
        r'(bachelor of (?:arts|science|fine arts|business administration|'
        r'engineering|applied science|nursing|music|social work|laws|'
        r'technology|commerce|education|architecture|pharmacy|design))'
        r'(?:\s+in\s+([\w\s]+?))?(?:\.|,|\n|$)',

        r'(associate of (?:arts|science|applied science|applied arts))'
        r'(?:\s+in\s+([\w\s]+?))?(?:\.|,|\n|$)',

        r'(diploma(?:\s+in|\s+of)?\s+([\w\s]+?))?(?:\.|,|\n|$)',

        r'(b\.?a\.?|b\.?s\.?c?\.?|b\.?f\.?a\.?|b\.?b\.?a\.?|'
        r'b\.?eng\.?|llb)\s+(?:in\s+)?([\w\s]+?)(?:\.|,|\n|$)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            groups = match.groups()
            if groups[0]:
                degree_type = normalise_degree_type(groups[0].strip())
                subject = groups[1].strip() if len(groups) > 1 and groups[1] else None
                return degree_type, subject

    return None, None


def detect_duration_from_page(page_text):
    """Extract duration from page text."""
    return extract_duration(page_text)


# ─────────────────────────────────────────────────────────
# MAIN PARSERS
# ─────────────────────────────────────────────────────────

def parse_programmes(html, base_url=""):
    """
    Parse programmes from a page.
    Handles:
    - Pages with explicit degree names
    - Pages with only subject names
    - Pages with concentrations
    - Department listing pages
    """
    soup = BeautifulSoup(html, 'lxml')
    page_text = soup.get_text()
    programmes = []

    # Remove noise
    for tag in soup.find_all(['nav', 'footer', 'script', 'style', 'noscript']):
        tag.decompose()

    # ── Strategy 1: Links with explicit degree keywords
    for link in soup.find_all('a', href=True):
        text = clean_text(link.get_text())
        href = link['href']

        if not text or len(text) < 5 or len(text) > 150:
            continue
        if is_skip_url(href):
            continue

        if looks_like_degree(text, href):
            full_url = build_url(href, base_url)
            programmes.append({
                'name': text,
                'url': full_url,
                'level': 'Bachelor',
                'raw': True,
                'needs_lookup': False,
            })

    # ── Strategy 2: Tables with programme data
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if len(rows) < 2:
            continue
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if not cells:
                continue
            text = clean_text(cells[0].get_text())
            link = row.find('a')
            href = link['href'] if link else ''
            if text and len(text) > 5 and looks_like_degree(text, href):
                full_url = build_url(href, base_url)
                programmes.append({
                    'name': text,
                    'url': full_url,
                    'level': 'Bachelor',
                    'raw': True,
                    'needs_lookup': False,
                })

    # ── Strategy 3: Headings followed by lists
    for heading in soup.find_all(['h2', 'h3', 'h4']):
        heading_text = heading.get_text().lower()
        if not any(s in heading_text for s in [
            'programme', 'program', 'course', 'degree', 'bachelor',
            'diploma', 'associate', 'undergraduate', 'major', 'study'
        ]):
            continue

        next_el = heading.find_next_sibling()
        if next_el and next_el.name in ['ul', 'ol']:
            for item in next_el.find_all('li'):
                text = clean_text(item.get_text())
                link = item.find('a')
                href = link['href'] if link else ''
                if text and len(text) > 5:
                    full_url = build_url(href, base_url)
                    programmes.append({
                        'name': text,
                        'url': full_url,
                        'level': 'Bachelor',
                        'raw': True,
                        'needs_lookup': not looks_like_degree(text, href),
                    })

    # ── Strategy 4: Subject-only links (department/faculty listing pages)
    # These are links that look like subject names, not degree names
    # Flag them for degree type lookup
    subject_links = []
    for link in soup.find_all('a', href=True):
        text = clean_text(link.get_text())
        href = link['href']

        if not text or len(text) < 4 or len(text) > 80:
            continue
        if is_skip_url(href):
            continue
        if looks_like_degree(text, href):
            continue  # already caught in Strategy 1

        # Check if it links to a department/programme-type page
        href_lower = href.lower()
        if any(p in href_lower for p in [
            'department', 'dept', 'faculty', 'school', 'college',
            'program', 'programme', 'major', 'degree', 'study',
            'academics', 'undergraduate',
        ]):
            full_url = build_url(href, base_url)
            subject_links.append({
                'name': text,
                'url': full_url,
                'level': 'Bachelor',
                'raw': True,
                'needs_lookup': True,  # must visit page to find degree type
            })

    programmes.extend(subject_links)

    # ── Deduplicate by name
    seen = set()
    unique = []
    for p in programmes:
        key = p['name'].lower().strip()
        if key not in seen and len(key) > 4:
            seen.add(key)
            unique.append(p)

    return unique


def parse_programme_detail(html, base_url, subject_name=None):
    """
    Parse a single programme's detail page.
    Used when we visit a department/subject page to find:
    - The actual degree type
    - Whether concentrations exist
    - Duration for fallback

    Returns list of programme dicts (may be multiple if concentrations found).
    """
    soup = BeautifulSoup(html, 'lxml')
    page_text = soup.get_text()

    programmes = []

    # ── Find degree type
    degree_type, subject_from_page = detect_degree_type_from_page(soup, page_text)
    subject = subject_from_page or subject_name or ''

    # ── Find duration for fallback
    duration = detect_duration_from_page(page_text)

    # ── Determine degree level
    if degree_type:
        from scraper.rules import get_degree_level, format_programme_name
        level = get_degree_level(degree_type + ' in ' + subject if subject else degree_type)
    else:
        # Unclear degree type — use duration fallback
        level = infer_degree_level_from_duration(duration)

    # ── Check for concentrations
    should_expand = (
        concentrations_chosen_at_application(page_text) or
        concentrations_listed_separately(page_text)
    )

    if should_expand:
        concentrations = extract_concentrations(soup)
    else:
        concentrations = []

    # ── Build programme rows
    if concentrations:
        for conc in concentrations:
            if degree_type and subject:
                name = format_programme_name(degree_type, subject, conc)
            elif degree_type:
                name = format_programme_name(degree_type, conc, None)
            else:
                name = format_unclear_degree(f"{subject} - {conc}" if subject else conc, level)
            programmes.append({
                'name': name,
                'url': base_url,
                'level': level,
                'duration': duration or '',
                'fee': '',
                'medium': 'English',
                'raw': False,
                'needs_lookup': False,
            })
    else:
        # Single programme row
        if degree_type and subject:
            name = format_programme_name(degree_type, subject)
        elif degree_type:
            name = format_programme_name(degree_type)
        else:
            name = format_unclear_degree(subject, level)

        programmes.append({
            'name': name,
            'url': base_url,
            'level': level,
            'duration': duration or '',
            'fee': '',
            'medium': 'English',
            'raw': False,
            'needs_lookup': False,
        })

    return programmes


def parse_json_programmes(data, base_url=""):
    """Extract programmes from a JSON API response."""
    programmes = []

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ['programmes', 'programs', 'courses', 'data',
                    'results', 'items', 'faculties', 'degrees']:
            if key in data:
                items = data[key]
                break
        else:
            items = []
    else:
        return []

    for item in items:
        if not isinstance(item, dict):
            continue
        name = (item.get('name') or item.get('title') or
                item.get('programme_name') or item.get('course_name') or
                item.get('degree_name') or '')
        url = (item.get('url') or item.get('link') or
               item.get('programme_url') or item.get('slug') or '')

        if name and len(name) > 5:
            if url and not url.startswith('http'):
                url = base_url.rstrip('/') + '/' + url.lstrip('/')
            programmes.append({
                'name': clean_text(name),
                'url': url,
                'level': 'Bachelor',
                'raw': True,
                'needs_lookup': False,
            })

    return programmes
