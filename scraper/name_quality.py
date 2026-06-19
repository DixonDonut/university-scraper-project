# scraper/name_quality.py
# Universal programme name quality scoring and filtering.
# Works for any university site — no site-specific strings.
# Detects nav noise, sentence fragments, school names, and real programmes
# using patterns and heuristics, not keyword lists.

import re

# ─────────────────────────────────────────────────────────
# PATTERN DEFINITIONS — all pattern-based, not site-specific
# ─────────────────────────────────────────────────────────

# Action words that appear in nav buttons and UI elements
# Never appear in real programme names
NAV_ACTION_WORDS = {
    'apply', 'login', 'register', 'sign', 'search', 'browse',
    'explore', 'discover', 'find', 'view', 'see', 'show', 'hide',
    'learn more', 'read more', 'click here', 'get started',
    'request', 'download', 'subscribe', 'follow', 'share', 'donate',
    'give', 'visit', 'tour', 'attend', 'join', 'enroll', 'enrol',
    'contact', 'ask', 'chat', 'call', 'email', 'submit',
    'next', 'previous', 'back', 'continue', 'proceed',
    'go to', 'jump to', 'skip to', 'return to',
}

# First/second person words — never in programme names
PERSONAL_PRONOUNS = {
    "i'm", "i'll", "i've", "i'd", 'we', 'our', 'us',
    'you', 'your', "you're", "you'll", "you've", "you'd",
    "let's", 'lets', "go cougs", "go bulldogs", "go trojans",
}

# Substring signals that indicate a sentence fragment, not a programme title
SENTENCE_FRAGMENT_SIGNALS = [
    'majoring in', 'majors in', 'major in',
    'majors like', 'major is', 'major at',
    'majors at', 'political scientists',
    'civil and environmental engineers',
]

# Verb patterns that indicate a sentence
SENTENCE_VERB_PATTERNS = [
    r'\byou will\b', r'\byou can\b', r'\byou are\b', r'\byou have\b',
    r'\bstudents will\b', r'\bstudents can\b', r'\bstudents are\b',
    r'\bthis (program|programme|major|course|degree)\b',
    r'\bthe (program|programme|course|degree)\b',
    r'\bdesigned to\b', r'\bprepares (you|students)\b',
    r'\bfocuses on\b', r'\bemphasizes\b', r'\bprovides (a|an|the)\b',
    r'\boffers (a|an|the)\b', r'\bincludes (a|an|the)\b',
    r'\bwith this major\b', r'\bfrom concept\b',
    r'\bin (either|both)\b', r'\bas well as\b',
    r'\bin addition to\b', r'\bbuilding on\b',
    r'\bcourses cover\b', r'\bcourses include\b',
    r'\bthe process of\b', r'\bthe study of\b',
]

# Structural patterns of school/department names
# "X of Y" or "X for Y" where X is an institutional unit
INSTITUTIONAL_PREFIXES = [
    'college of', 'school of', 'faculty of', 'department of',
    'division of', 'institute of', 'center for', 'centre for',
    'office of', 'bureau of', 'section of', 'unit of',
    'program in',  # rare but appears
]

# UI connector strings — often appear in scraped page text
UI_CONNECTORS = [
    '|', '›', '»', '«', '‹', '→', '←', '↓', '↑',
    '...', '–', '—', '>>>', '<<<',
]

# Degree keywords — if any of these appear, it's likely a real programme
DEGREE_QUALITY_SIGNALS = [
    'bachelor of', 'bachelor in', "bachelor's",
    'associate of', 'associate degree', 'associate in',
    'diploma in', 'diploma of', 'advanced diploma',
    'hnd in', 'hnd ', 'foundation degree',
    'b.sc', 'bsc ', 'b.a.', 'ba in', 'bba ', 'bfa ',
    'b.com', 'b.pharm', 'b.arch', 'llb', 'beng',
    'diploma iii', 'diploma iv',
    'aa in', 'as in', 'aas ',
]

# Things that are definitely not programmes regardless of context
HARD_EXCLUDES = [
    'master', 'masters', 'msc', 'm.sc', 'mba', 'm.b.a',
    'phd', 'ph.d', 'doctorate', 'doctoral', 'doctor of',
    'postgraduate', 'post-graduate', 'post graduate',
    'graduate certificate', 'graduate diploma',
    'staatsexamen', 'kirchliches examen',
    'dec-bac',
]

# Programme quality indicators — proper nouns, subject areas
SUBJECT_AREA_WORDS = {
    'accounting', 'agriculture', 'anthropology', 'architecture', 'art',
    'astronomy', 'biochemistry', 'biology', 'business', 'chemistry',
    'cinema', 'civil', 'commerce', 'communication', 'computer',
    'criminology', 'dance', 'data', 'design', 'drama', 'ecology',
    'economics', 'education', 'electrical', 'engineering', 'english',
    'environment', 'finance', 'food', 'forensic', 'geography',
    'geology', 'health', 'history', 'hospitality', 'information',
    'international', 'journalism', 'kinesiology', 'landscape', 'law',
    'linguistics', 'literature', 'management', 'marketing', 'mathematics',
    'mechanical', 'media', 'medicine', 'music', 'nursing', 'nutrition',
    'philosophy', 'photography', 'physics', 'political', 'psychology',
    'public', 'science', 'social', 'sociology', 'software', 'statistics',
    'technology', 'theatre', 'tourism', 'urban', 'veterinary', 'zoology',
}


# ─────────────────────────────────────────────────────────
# DETECTION FUNCTIONS
# ─────────────────────────────────────────────────────────

def is_nav_noise(name):
    """
    Universal nav noise detection.
    Returns True if name looks like a nav link, button, or UI element.
    """
    if not name:
        return True

    name_stripped = name.strip()
    name_lower = name_stripped.lower()

    # Too short to be a programme
    if len(name_stripped) < 5:
        return True

    # Too long to be a simple nav item but check for UI connectors
    for connector in UI_CONNECTORS:
        if connector in name_stripped:
            return True

    # All caps — usually an acronym nav item or heading
    if name_stripped.isupper() and len(name_stripped) < 10:
        return True

    # Action word only (single nav button)
    words = name_lower.split()
    if len(words) <= 3:
        # Short text — check if it's a pure action word
        for action in NAV_ACTION_WORDS:
            if name_lower == action or name_lower.startswith(action + ' '):
                return True

    # Personal pronouns — "Let's Go", "Your Future"
    for pronoun in PERSONAL_PRONOUNS:
        if name_lower.startswith(pronoun) or f' {pronoun} ' in name_lower:
            return True

    # Starts with a number (page numbers, years, IDs)
    if re.match(r'^\d', name_stripped):
        return True

    # Looks like a URL path that wasn't cleaned
    if '/' in name_stripped and not any(d in name_lower for d in DEGREE_QUALITY_SIGNALS):
        return True

    # Campus/location only — single proper noun that's clearly a place
    # (Detected by being a single word with no degree/subject signal)
    if len(words) == 1 and name_stripped[0].isupper():
        if name_lower not in SUBJECT_AREA_WORDS:
            return True

    return False


def is_sentence_fragment(name):
    """
    Universal sentence fragment detection.
    Returns True if name looks like description text, not a programme title.
    """
    if not name:
        return False

    name_lower = name.lower()

    # Check fragment signals
    for signal in SENTENCE_FRAGMENT_SIGNALS:
        if signal in name_lower:
            return True

    # Check verb patterns
    for pattern in SENTENCE_VERB_PATTERNS:
        if re.search(pattern, name_lower):
            return True

    # Multiple sentences (more than one period with text after)
    if re.search(r'\. [A-Z]', name):
        return True

    # Ends with a period (sentence ending)
    if name.strip().endswith('.') and len(name) > 30:
        return True

    # Contains a lowercase verb after a comma
    if re.search(r', (and|or|but|which|that|where|when|how) ', name_lower):
        # Only a fragment if it's long
        if len(name) > 60:
            return True

    return False


def is_school_or_unit_name(name):
    """
    Universal detection of institutional unit names.
    Returns True if name is a school/department/college name, not a programme.
    """
    name_lower = name.lower().strip()

    # "X of Y" pattern with institutional prefix
    for prefix in INSTITUTIONAL_PREFIXES:
        if name_lower.startswith(prefix):
            return True

    # "Paul X. Allen School for Y" type patterns — named schools
    if re.search(r'\b(dr|prof|sir|dame|lord)\.?\s+[A-Z]', name):
        return True

    # Possessive school names "Smith's College of..."
    if re.search(r"[A-Z][a-z]+'s\s+(college|school|institute|center)", name):
        return True

    return False


def is_hard_excluded(name):
    """
    Returns True if name contains a hard-exclude keyword
    regardless of any other signals.
    """
    name_lower = name.lower()
    return any(kw in name_lower for kw in HARD_EXCLUDES)


def is_real_programme(name):
    """
    Returns True if name contains strong signals that it is a real programme.
    """
    name_lower = name.lower()

    # Contains a degree keyword
    for signal in DEGREE_QUALITY_SIGNALS:
        if signal in name_lower:
            return True

    return False


def score_programme_name(name):
    """
    Score a programme name from -100 (definitely noise) to +100 (definitely real).
    
    Used to rank ambiguous entries where we cannot be certain.
    
    Score guide:
    +50 to +100 = include
     -10 to +49 = unknown — needs page visit to confirm
    -100 to -11 = exclude
    """
    if not name:
        return -100

    score = 0
    name_lower = name.lower().strip()
    name_len = len(name.strip())

    # Hard excludes → immediate -100
    if is_hard_excluded(name):
        return -100

    # Clear nav noise → -80
    if is_nav_noise(name):
        return -80

    # School/unit name → -60
    if is_school_or_unit_name(name):
        return -60

    # Sentence fragment → -50
    if is_sentence_fragment(name):
        return -50

    # Real degree signal → +60
    if is_real_programme(name):
        score += 60

    # Subject area words → +20 each (up to +40)
    subject_hits = sum(1 for w in SUBJECT_AREA_WORDS if w in name_lower)
    score += min(subject_hits * 20, 40)

    # Good length for a programme name (15-80 chars)
    if 15 <= name_len <= 80:
        score += 10
    elif name_len < 6 or name_len > 150:
        score -= 30

    # Title case (proper programme formatting)
    words = name.split()
    if len(words) >= 2:
        capitalised = sum(1 for w in words if w[0].isupper())
        if capitalised / len(words) >= 0.5:
            score += 10

    # Action words → -20
    for action in NAV_ACTION_WORDS:
        if action in name_lower:
            score -= 20
            break

    return max(-100, min(100, score))


def should_include_by_quality(name):
    """
    Master quality check.
    Returns ('include'|'exclude'|'unknown', reason)
    """
    if is_hard_excluded(name):
        return 'exclude', 'Hard excluded keyword'

    if is_nav_noise(name):
        return 'exclude', 'Nav noise'

    if is_school_or_unit_name(name):
        return 'exclude', 'School/unit name, not a programme'

    if is_sentence_fragment(name):
        return 'exclude', 'Sentence fragment from description text'

    if is_real_programme(name):
        return 'include', 'Contains degree keyword'

    score = score_programme_name(name)

    if score >= 30:
        return 'include', f'Quality score: {score}'
    elif score >= 0:
        return 'unknown', f'Quality score: {score} — needs lookup'
    else:
        return 'exclude', f'Quality score: {score}'


def is_valid_concentration_name(name):
    """
    Universal concentration name validation.
    Returns True only if the name could realistically be a concentration.
    """
    if not name:
        return False

    name_stripped = name.strip()

    # Length check — concentrations are subject area names, not sentences
    if len(name_stripped) < 3 or len(name_stripped) > 60:
        return False

    # Sentence fragment
    if is_sentence_fragment(name_stripped):
        return False

    # Nav noise
    if is_nav_noise(name_stripped):
        return False

    # Contains sentence-like patterns
    name_lower = name_stripped.lower()

    sentence_starters = [
        'with this', 'you will', 'you can', 'from concept',
        'the process', 'courses cover', 'in addition',
        'as well as', 'and selling', 'planning and',
        'this major', 'this program', 'this track',
    ]
    if any(s in name_lower for s in sentence_starters):
        return False

    # Ends with a period (sentence ending)
    if name_stripped.endswith('.'):
        return False

    # Contains word counts suggesting a full sentence
    words = name_stripped.split()
    if len(words) > 8:
        return False

    return True
