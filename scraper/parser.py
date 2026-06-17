# scraper/parser.py
# Fixed version — better degree detection, filters nav noise

from bs4 import BeautifulSoup
import re

# Keywords that signal a programme listing section
SECTION_SIGNALS = [
    'programme', 'program', 'course', 'degree', 'bachelor',
    'diploma', 'associate', 'undergraduate', 'faculty', 'school',
    'department', 'major', 'study', 'hnd', 'd3', 'd4',
]

# URL patterns that signal a programme page
PROGRAMME_URL_PATTERNS = [
    'programme', 'program', 'course', 'degree', 'bachelor',
    'diploma', 'associate', 'undergraduate', 'faculty', 'school',
    'department', 'major', 'study', 'academics', 'hnd',
]

# URL patterns that signal nav/utility pages — skip these
SKIP_URL_PATTERNS = [
    'login', 'logout', 'search', 'news', 'event', 'contact',
    'about', 'alumni', 'portal', 'hostel', 'library', 'sport',
    'research', 'placement', 'scholarship', 'fee', 'admission',
    'campus', 'gallery', 'media', 'blog', 'career', 'job',
    'tender', 'notice', 'circular', 'announcement', 'download',
    'sitemap', 'privacy', 'cookie', 'terms', 'disclaimer',
    'facebook', 'twitter', 'linkedin', 'instagram', 'youtube',
    '#', 'javascript:', 'mailto:', 'tel:',
]

# Degree signals in text — used to detect programme names
DEGREE_TEXT_SIGNALS = [
    'b.e', 'b.tech', 'btech', 'b.sc', 'bsc', 'b.a', 'bba',
    'b.com', 'b.pharm', 'b.arch', 'llb', 'b.ed', 'bachelor',
    'diploma in', 'diploma of', 'advanced diploma', 'hnd',
    'diploma iii', 'diploma iv', 'associate', 'foundation degree',
]


def clean_text(text):
    """Clean up extracted text."""
    text = re.sub(r'\s+', ' ', text).strip()
    text = text.replace('\n', ' ').replace('\t', ' ')
    return text


def is_skip_url(href):
    """Returns True if this URL should be skipped."""
    if not href:
        return True
    href_lower = href.lower()
    for pattern in SKIP_URL_PATTERNS:
        if pattern in href_lower:
            return True
    return False


def looks_like_programme(text, href=""):
    """Returns True if text or URL looks like a programme."""
    text_lower = text.lower()
    href_lower = href.lower() if href else ""

    # Check text for degree signals
    for signal in DEGREE_TEXT_SIGNALS:
        if signal in text_lower:
            return True

    # Check URL for programme signals
    for signal in PROGRAMME_URL_PATTERNS:
        if signal in href_lower:
            return True

    return False


def parse_programmes(html, base_url=""):
    """
    Extract programme names and URLs from raw HTML.
    Returns list of dicts with name, url, level.
    """
    soup = BeautifulSoup(html, 'lxml')
    programmes = []

    # Remove noise tags
    for tag in soup.find_all(['nav', 'footer', 'header',
                               'script', 'style', 'noscript']):
        tag.decompose()

    # ── Strategy 1: Find links with degree keywords in text
    for link in soup.find_all('a', href=True):
        text = clean_text(link.get_text())
        href = link['href']

        if not text or len(text) < 5 or len(text) > 120:
            continue

        if is_skip_url(href):
            continue

        if looks_like_programme(text, href):
            # Build full URL
            if href.startswith('http'):
                full_url = href
            elif href.startswith('/'):
                # Extract domain from base_url
                parts = base_url.split('/')
                domain = '/'.join(parts[:3])
                full_url = domain + href
            else:
                full_url = base_url.rstrip('/') + '/' + href

            programmes.append({
                'name': text,
                'url': full_url,
                'level': 'Bachelor',  # will be refined in rules
                'raw': True
            })

    # ── Strategy 2: Find tables that look like programme lists
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if len(rows) < 3:
            continue

        for row in rows:
            cells = row.find_all(['td', 'th'])
            if not cells:
                continue

            text = clean_text(cells[0].get_text())
            link = row.find('a')
            href = link['href'] if link else ''

            if text and len(text) > 5 and looks_like_programme(text, href):
                full_url = href if href.startswith('http') else base_url + href
                programmes.append({
                    'name': text,
                    'url': full_url,
                    'level': 'Bachelor',
                    'raw': True
                })

    # ── Strategy 3: Find headings and their following lists
    for heading in soup.find_all(['h2', 'h3', 'h4']):
        heading_text = heading.get_text().lower()

        # Only look at sections that sound like programme lists
        if not any(s in heading_text for s in SECTION_SIGNALS):
            continue

        # Get the next sibling list
        next_el = heading.find_next_sibling()
        if next_el and next_el.name in ['ul', 'ol']:
            for item in next_el.find_all('li'):
                text = clean_text(item.get_text())
                link = item.find('a')
                href = link['href'] if link else ''

                if text and len(text) > 5:
                    full_url = href if href.startswith('http') else base_url + href
                    programmes.append({
                        'name': text,
                        'url': full_url,
                        'level': 'Bachelor',
                        'raw': True
                    })

    # ── Deduplicate by name
    seen = set()
    unique = []
    for p in programmes:
        name_key = p['name'].lower().strip()
        if name_key not in seen and len(name_key) > 5:
            seen.add(name_key)
            unique.append(p)

    return unique


def parse_json_programmes(data, base_url=""):
    """
    Extract programmes from a JSON API response.
    Handles both list and dict responses.
    """
    programmes = []

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        # Try common keys
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

        # Try common name fields
        name = (item.get('name') or item.get('title') or
                item.get('programme_name') or item.get('course_name') or
                item.get('degree_name') or '')

        # Try common URL fields
        url = (item.get('url') or item.get('link') or
               item.get('programme_url') or item.get('slug') or '')

        if name and len(name) > 5:
            if url and not url.startswith('http'):
                url = base_url.rstrip('/') + '/' + url.lstrip('/')

            programmes.append({
                'name': clean_text(name),
                'url': url,
                'level': 'Bachelor',
                'raw': True
            })

    return programmes
