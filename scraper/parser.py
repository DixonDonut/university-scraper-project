# scraper/parser.py
# Universal parser — works for any university site.
# Uses name_quality.py for all filtering decisions.

import re
from bs4 import BeautifulSoup
from scraper.name_quality import (
    is_nav_noise, is_sentence_fragment, is_school_or_unit_name,
    is_valid_concentration_name, score_programme_name,
    DEGREE_QUALITY_SIGNALS,
)
from scraper.rules import (
    format_programme_name, format_unclear_degree,
    infer_degree_level_from_duration, normalise_degree_type,
    concentrations_chosen_at_application, concentrations_listed_separately,
    CONCENTRATION_INTRO_WORDS,
)

# ─────────────────────────────────────────────────────────
# URL PATTERNS
# ─────────────────────────────────────────────────────────

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

# Duration patterns — strict, with sanity checks
DURATION_PATTERNS = [
    r'(\d+)[- ]year degree',
    r'(\d+)[- ]year program(?:me)?',
    r'(\d)\s*years? of study',
    r'(\d)\s*years? to complete',
    r'(\d)\s*years? to graduate',
    r'(\d+)\s*credit hours? required',
    r'(\d+)\s*total credits?',
    r'(\d+)\s*semester credits?',
    r'(\d+)\s*ects credits?',
    r'(\d+)\s*units? required',
]


# ─────────────────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────────────────

STRIP_NAME_SUFFIXES = [
    ', course catalog', ', academic advising', ', course requirements',
    ' course catalog', ' academic advising', ' course requirements',
    ', requirements', ', curriculum',
    ', catalog listing', ' catalog listing',
    ', academic plan', ' academic plan',
]

def clean_text(text):
    text = re.sub(r'\s+', ' ', text).strip()
    return text.replace('\n', ' ').replace('\t', ' ')


_LOWERCASE_MID_WORDS = {
    'in', 'of', 'and', 'or', 'the', 'a', 'an',
    'at', 'by', 'for', 'from', 'on', 'to', 'with',
}


def smart_title(text):
    """Title case that preserves apostrophes, all-caps abbreviations, and
    lowercases prepositions/articles in non-initial positions."""
    def process_word(word, is_first):
        if not word:
            return word
        alpha = ''.join(c for c in word if c.isalpha())
        # Lowercase prepositions/articles mid-string
        if not is_first and alpha.lower() in _LOWERCASE_MID_WORDS and word.isalpha():
            return word.lower()
        # All-caps abbreviation (BFA, USA) — preserve entire token
        if alpha and alpha.isupper() and len(alpha) > 1:
            return word
        # Capitalize first alpha char, lowercase the rest; don't capitalize after '
        result = []
        capitalize_next = True
        for c in word:
            if capitalize_next and c.isalpha():
                result.append(c.upper())
                capitalize_next = False
            elif c == "'":
                result.append(c)
                capitalize_next = False
            elif not c.isalpha():
                result.append(c)
            else:
                result.append(c.lower())
        return ''.join(result)

    words = text.split(' ')
    return ' '.join(process_word(w, i == 0) for i, w in enumerate(words))


def strip_name_suffixes(name):
    """Remove trailing noise like ', Course Catalog', unclosed parens, and trailing dashes."""
    name_lower = name.lower()
    for suffix in STRIP_NAME_SUFFIXES:
        if name_lower.endswith(suffix):
            name = name[:len(name) - len(suffix)].strip().rstrip(',').strip()
            name_lower = name.lower()
            break
    # If name has "(" but no ")" → strip from "(" onwards
    if '(' in name and ')' not in name:
        name = name[:name.index('(')].strip()
    # Strip trailing spaces, hyphens, dashes
    name = name.rstrip(' \t-–—').strip()
    return name


def is_skip_url(href):
    if not href:
        return True
    href_lower = href.lower()
    return any(p in href_lower for p in SKIP_URL_PATTERNS)


def looks_like_degree_url(href):
    """Returns True if URL path suggests a programme page."""
    if not href:
        return False
    href_lower = href.lower()
    return any(p in href_lower for p in PROGRAMME_URL_PATTERNS)


def looks_like_degree_text(text):
    """Returns True if text contains a degree keyword."""
    text_lower = text.lower()
    return any(signal in text_lower for signal in DEGREE_QUALITY_SIGNALS)


def name_passes_quality(name, min_score=0):
    """
    Returns True if a name passes the universal quality check.
    min_score: minimum score to accept (-100 to +100)
    """
    if is_nav_noise(name):
        return False
    if is_sentence_fragment(name):
        return False
    if is_school_or_unit_name(name):
        return False
    score = score_programme_name(name)
    return score >= min_score


PROGRAMME_PAGE_SIGNALS = [
    'credit hour', 'credit unit', 'ects credit',
    'course catalog', 'course of study', 'course requirement',
    'graduation requirement', 'degree requirement', 'learning outcome',
    'years to complete', 'curriculum', 'academic plan',
    'programme of study', 'program of study',
    'bachelor of science', 'bachelor of arts', 'bachelor of',
    "bachelor's degree in", 'undergraduate degree in',
    'major requirements', 'program at a glance', 'programme overview',
]

def is_genuine_programme_page(content):
    """
    Returns True only if content looks like an actual undergraduate
    programme page rather than a blog post, news article, or nav page.
    Requires at least 3 programme-level signals.
    """
    if not content or len(content) < 1000:
        return False
    text = content.lower()
    count = sum(1 for s in PROGRAMME_PAGE_SIGNALS if s in text)
    return count >= 3


def extract_duration(text):
    """Extract duration with strict patterns and sanity checks."""
    for pattern in DURATION_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            num = int(match.group(1))
            if 'year' in pattern and (num < 1 or num > 8):
                continue
            if 'credit' in pattern or 'unit' in pattern or 'ects' in pattern:
                if num < 20 or num > 240:
                    continue
            return match.group(0)
    return None


def build_url(href, base_url):
    if not href:
        return ''
    if href.startswith('http'):
        return href
    if href.startswith('/'):
        domain = '/'.join(base_url.split('/')[:3])
        return domain + href
    return base_url.rstrip('/') + '/' + href.lstrip('/')


def is_same_domain(url, base_url):
    """Returns True if url shares the same root domain as base_url."""
    if not url or not url.startswith('http'):
        return True
    try:
        def root(u):
            parts = u.split('/')[2].split('.')
            return '.'.join(parts[-2:]) if len(parts) >= 2 else parts[0]
        return root(url) == root(base_url)
    except (IndexError, AttributeError):
        return True


# ─────────────────────────────────────────────────────────
# CONCENTRATION EXTRACTION — Universal strict version
# ─────────────────────────────────────────────────────────

def extract_concentrations(soup):
    """
    Extract concentrations from a programme page.
    Universal: validates all names with is_valid_concentration_name().
    Rejects sentence fragments, long descriptions, and UI text.
    """
    concentrations = []

    # Find headings that introduce concentration lists
    for heading in soup.find_all(['h2', 'h3', 'h4', 'h5', 'strong', 'b']):
        heading_text = heading.get_text().lower().strip()

        if not any(word in heading_text for word in CONCENTRATION_INTRO_WORDS):
            continue

        # Get the next list element
        next_el = heading.find_next_sibling()
        if not next_el:
            next_el = heading.parent.find_next_sibling() if heading.parent else None

        if next_el and next_el.name in ['ul', 'ol']:
            for item in next_el.find_all('li', recursive=False):
                name = clean_text(item.get_text())
                if is_valid_concentration_name(name):
                    concentrations.append(name)

    # Definition lists
    for dl in soup.find_all('dl'):
        dl_text = dl.get_text().lower()
        if not any(word in dl_text for word in CONCENTRATION_INTRO_WORDS):
            continue
        for dt in dl.find_all('dt'):
            name = clean_text(dt.get_text())
            if is_valid_concentration_name(name):
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
# CATALOG WIDGET DEGREE TYPE EXTRACTION
# Works for any university using Acalog catalog (common in USA)
# ─────────────────────────────────────────────────────────

_ACALOG_ABBREV_MAP = {
    'b.a.':               'bachelor of arts',
    'b.s.':               'bachelor of science',
    'b.f.a.':             'bachelor of fine arts',
    'b.m.':               'bachelor of music',
    'b.s. in bus. ad.':   'bachelor of science',
    'b.a. in bus. ad.':   'bachelor of arts',
    'b.a./b.a. in ed.':   'bachelor of arts',
    'b.s./b.s. in ed.':   'bachelor of science',
    'b.a. in ed.':        'bachelor of arts',
    'b.s. in ed.':        'bachelor of science',
    'b.s.n.':             'bachelor of nursing',
    'b.s.w.':             'bachelor of social work',
    'b.arch.':            'bachelor of architecture',
    'b.mus.':             'bachelor of music',
}
_ACALOG_EXCLUDE = {
    'minor', 'certificate', 'master', 'm.s.', 'm.a.', 'm.f.a', 'mba',
    'ph.d', 'phd', 'accelerated', 'graduate', 'online',
}


def fetch_catalog_degree_type(raw_html):
    """
    Extract degree type from Acalog catalog widget data attributes embedded
    in any university page. Returns (degree_type_str, subject_str) or (None, None).
    Works for any US university that uses the Acalog catalog system.
    """
    if not raw_html:
        return None, None

    matches = re.findall(r'data-acalog-program-name="([^"]+)"', raw_html)
    if not matches:
        return None, None

    for match in matches:
        match_lower = match.lower()
        if any(ex in match_lower for ex in _ACALOG_EXCLUDE):
            continue

        # "Subject Name, B.X." or "Subject Name, B.X. in Bus. Ad."
        abbrev_match = re.search(
            r',\s*(B\.[A-Z.]+(?:\s+in\s+Bus\.\s+Ad\.)?)\s*$', match, re.I
        )
        if abbrev_match:
            abbrev_raw = abbrev_match.group(1).lower().strip()
            degree_type = _ACALOG_ABBREV_MAP.get(abbrev_raw)
            if degree_type:
                subject = match[:match.rfind(',')].strip()
                subject = re.sub(r'\s*\([^)]+\)\s*$', '', subject).strip()
                return degree_type, subject

    return None, None


# ─────────────────────────────────────────────────────────
# DEGREE TYPE DETECTION
# ─────────────────────────────────────────────────────────

def detect_degree_type_from_page(soup, page_text):
    """
    Detect the degree type from a page that only lists a subject name.
    Returns (degree_type, subject) or (None, None).
    """
    text_lower = page_text.lower()

    degree_patterns = [
        # Full degree names
        r'(bachelor of (?:arts|science|fine arts|business administration|'
        r'engineering|applied science|nursing|music|social work|laws|'
        r'technology|commerce|education|architecture|pharmacy|design|'
        r'public health|social science|information technology|'
        r'environmental science|international studies|urban planning))'
        r'(?:\s+in\s+([\w\s,&\']+?))?(?:\.|,|\n|\(|with|and a|$)',

        r'(associate of (?:arts|science|applied science|applied arts))'
        r'(?:\s+in\s+([\w\s]+?))?(?:\.|,|\n|$)',

        r'(diploma(?:\s+(?:in|of))\s+([\w\s]+?))?(?:\.|,|\n|$)',

        # Abbreviated forms
        r'(b\.?[asf]\.?c?\.?|b\.?eng\.?|b\.?b\.?a\.?|llb|bca)\s+'
        r'(?:in\s+)?([\w\s,&\']+?)(?:\.|,|\n|\(|$)',
    ]

    for pattern in degree_patterns:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            groups = match.groups()
            if groups and groups[0]:
                degree_type = normalise_degree_type(groups[0].strip())
                subject = None
                if len(groups) > 1 and groups[1]:
                    subject = groups[1].strip()
                    if len(subject) < 3 or len(subject) > 80:
                        subject = None
                return degree_type, subject

    return None, None


# ─────────────────────────────────────────────────────────
# MAIN PARSERS
# ─────────────────────────────────────────────────────────

def parse_programmes(html, base_url=""):
    """
    Universal programme parser.
    Works for any university site.
    Uses quality scoring to filter noise.
    """
    soup = BeautifulSoup(html, 'lxml')
    programmes = []

    for tag in soup.find_all(['nav', 'footer', 'script', 'style', 'noscript']):
        tag.decompose()

    # ── Strategy 1: Links with degree signals
    for link in soup.find_all('a', href=True):
        text = clean_text(link.get_text())
        href = link['href']

        if not text or len(text) < 5 or len(text) > 150:
            continue
        if is_skip_url(href):
            continue

        # Must pass quality check
        if not name_passes_quality(text, min_score=-10):
            continue

        if looks_like_degree_text(text) or looks_like_degree_url(href):
            full_url = build_url(href, base_url)
            if not is_same_domain(full_url, base_url):
                continue
            programmes.append({
                'name': text, 'url': full_url,
                'level': 'Bachelor', 'raw': True, 'needs_lookup': False,
            })

    # ── Strategy 2: Tables
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

            if (text and len(text) > 5 and name_passes_quality(text, min_score=-10)
                    and (looks_like_degree_text(text) or looks_like_degree_url(href))):
                full_url = build_url(href, base_url)
                if not is_same_domain(full_url, base_url):
                    continue
                programmes.append({
                    'name': text, 'url': full_url,
                    'level': 'Bachelor', 'raw': True, 'needs_lookup': False,
                })

    # ── Strategy 3: Headings + lists
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

                if text and len(text) > 5 and name_passes_quality(text, min_score=0):
                    full_url = build_url(href, base_url)
                    if not is_same_domain(full_url, base_url):
                        continue
                    is_degree = looks_like_degree_text(text)
                    programmes.append({
                        'name': text, 'url': full_url,
                        'level': 'Bachelor', 'raw': True,
                        'needs_lookup': not is_degree,
                    })

    # ── Strategy 4: Subject-only links
    for link in soup.find_all('a', href=True):
        text = clean_text(link.get_text())
        href = link['href']

        if not text or len(text) < 4 or len(text) > 80:
            continue
        if is_skip_url(href):
            continue
        if looks_like_degree_text(text):
            continue  # already caught
        if not name_passes_quality(text, min_score=0):
            continue

        if looks_like_degree_url(href):
            full_url = build_url(href, base_url)
            if not is_same_domain(full_url, base_url):
                continue
            programmes.append({
                'name': text, 'url': full_url,
                'level': 'Bachelor', 'raw': True, 'needs_lookup': True,
            })

    # ── Deduplicate and normalise case
    seen = set()
    unique = []
    for p in programmes:
        name = strip_name_suffixes(p['name'])
        key = name.lower().strip()
        if key not in seen and len(key) > 4:
            seen.add(key)
            p['name'] = smart_title(name)
            unique.append(p)

    return unique


def parse_programme_detail(html, base_url, subject_name=None):
    """
    Parse a single programme detail page.
    Universal: finds degree type, concentrations, duration.
    Falls back to Acalog catalog widget data attributes when page text
    doesn't explicitly state the degree type.
    """
    soup = BeautifulSoup(html, 'lxml')
    page_text = soup.get_text()

    degree_type, subject_from_page = detect_degree_type_from_page(soup, page_text)

    # Fallback: extract from embedded Acalog catalog widget (common in US universities)
    if not degree_type:
        degree_type, catalog_subject = fetch_catalog_degree_type(html)
        if degree_type and catalog_subject and not subject_name:
            subject_from_page = catalog_subject

    subject = subject_from_page or subject_name or ''
    duration = extract_duration(page_text)

    if degree_type:
        from scraper.rules import get_degree_level
        level = get_degree_level(
            degree_type + ' in ' + subject if subject else degree_type
        )
    else:
        level = infer_degree_level_from_duration(duration)

    # Concentration check — only expand when clearly stated
    should_expand = concentrations_chosen_at_application(page_text)
    concentrations = []

    if not should_expand and concentrations_listed_separately(page_text):
        concentrations = extract_concentrations(soup)
        # Only expand if all extracted names pass quality check
        if concentrations and all(is_valid_concentration_name(c) for c in concentrations):
            should_expand = True
        else:
            concentrations = []

    if should_expand and not concentrations:
        concentrations = extract_concentrations(soup)

    programmes = []

    if concentrations:
        for conc in concentrations:
            if degree_type and subject:
                name = format_programme_name(degree_type, subject, conc)
            elif degree_type:
                name = format_programme_name(degree_type, conc, None)
            else:
                name = format_unclear_degree(
                    f"{subject} - {conc}" if subject else conc, level
                )
            programmes.append({
                'name': name, 'url': base_url, 'level': level,
                'duration': duration or '', 'fee': '', 'medium': 'English',
                'raw': False, 'needs_lookup': False,
            })
    else:
        if degree_type and subject:
            name = format_programme_name(degree_type, subject)
        elif degree_type:
            name = format_programme_name(degree_type)
        else:
            name = format_unclear_degree(subject, level)

        programmes.append({
            'name': name, 'url': base_url, 'level': level,
            'duration': duration or '', 'fee': '', 'medium': 'English',
            'raw': False, 'needs_lookup': False,
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
            if key in data and isinstance(data[key], list):
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
            name_clean = smart_title(strip_name_suffixes(clean_text(name)))
            # Quality check on API responses too
            if not name_passes_quality(name_clean, min_score=-10):
                continue
            if url and not url.startswith('http'):
                url = base_url.rstrip('/') + '/' + url.lstrip('/')
            programmes.append({
                'name': name_clean, 'url': url,
                'level': 'Bachelor', 'raw': True, 'needs_lookup': False,
            })

    return programmes
