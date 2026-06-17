# scraper/rules.py
# Complete rules — naming, concentrations, degree detection, include/exclude

import re

# ─────────────────────────────────────────────────────────
# DEGREE ABBREVIATION RULES
# ─────────────────────────────────────────────────────────

# These get abbreviated ONLY when a subject/major is present
# Standalone → always write full form
ABBREVIATIONS = {
    'bachelor of arts':                    'BA',
    'bachelor of science':                 'BSc',
    'bachelor of fine arts':               'BFA',
    'bachelor of business administration': 'BBA',
    'bachelor of computer applications':   'BCA',
    'bachelor of engineering':             'BEng',
    'bachelor of applied science':         'BASc',
    'bachelor of social work':             'BSW',
    'bachelor of nursing':                 'BN',
    'bachelor of music':                   'BMus',
    'associate of arts':                   'AA',
    'associate of science':                'AS',
    'associate of applied science':        'AAS',
    'associate of applied arts':           'AAA',
}

# These NEVER get abbreviated — always full form even with a subject
NO_ABBREVIATION = [
    'bachelor of laws',
    'bachelor of technology',
    'bachelor of commerce',
    'bachelor of education',
    'bachelor of architecture',
    'bachelor of pharmacy',
    'bachelor of medicine',
    'bachelor of dental surgery',
    'bachelor of veterinary science',
    'bachelor of public health',
    'bachelor of social science',
    'bachelor of design',
    'bachelor of urban planning',
    'bachelor of information technology',
    'bachelor of environmental science',
    'bachelor of international studies',
]

# Raw degree strings from university pages → normalise to full form
DEGREE_NORMALISATIONS = {
    'b.a.': 'bachelor of arts',
    'b.a':  'bachelor of arts',
    'ba ':  'bachelor of arts',
    'b.s.': 'bachelor of science',
    'b.s':  'bachelor of science',
    'bs ':  'bachelor of science',
    'bsc ': 'bachelor of science',
    'b.sc': 'bachelor of science',
    'bfa ': 'bachelor of fine arts',
    'b.f.a': 'bachelor of fine arts',
    'bba ': 'bachelor of business administration',
    'b.b.a': 'bachelor of business administration',
    'bca ': 'bachelor of computer applications',
    'b.e.': 'bachelor of engineering',
    'b.e ': 'bachelor of engineering',
    'beng ': 'bachelor of engineering',
    'b.eng': 'bachelor of engineering',
    'be in': 'bachelor of engineering in',
    'llb':  'bachelor of laws',
    'b.tech': 'bachelor of technology',
    'btech': 'bachelor of technology',
    'b.com': 'bachelor of commerce',
    'bcom': 'bachelor of commerce',
    'b.ed': 'bachelor of education',
    'bed ': 'bachelor of education',
    'b.arch': 'bachelor of architecture',
    'b.pharm': 'bachelor of pharmacy',
    'b.sc (hons)': 'bachelor of science',
    'b.a. (hons)': 'bachelor of arts',
    'a.a.': 'associate of arts',
    'a.s.': 'associate of science',
    'a.a.s': 'associate of applied science',
    'd3': 'diploma iii',
    'd4': 'diploma iv',
}

# ─────────────────────────────────────────────────────────
# INCLUDE / EXCLUDE KEYWORDS
# ─────────────────────────────────────────────────────────

EXCLUDE_KEYWORDS = [
    # Postgraduate
    'm.sc', 'msc ', 'm.s.', ' ms ', 'm.e.', 'm.e ', 'm.tech', 'mtech',
    'm.pharm', 'mpharm', 'm.b.a', ' mba ', 'm.phil', 'mphil',
    'master', 'masters', 'postgraduate', 'post-graduate', 'post graduate',
    'phd', 'ph.d', 'doctorate', 'doctoral', 'doctor of',
    'm.com', 'mcom', 'm.ed', ' med ', 'm.arch',
    # Section headings
    'higher degree', 'integrated first degree', 'doctoral programme',
    'online admission', 'practice school',
    # German
    'staatsexamen', 'kirchliches',
    # Spanish
    'odontolog', 'nivelaci',
    # Indonesian
    'kelas karyawan', 'pjj', 'profesi', 'ners', 'apoteker',
    'kelas konversi', 'alih jenjang',
    # Other
    'dec-bac', 'rn-bsn', 'rnbsn',
    'baes', 'basus', 'hnc ',
    'post-graduate diploma', 'graduate certificate', 'conversion class',
    # Minors and certificates — not standalone programmes
    ' minor', 'minors', 'certificate only', 'non-degree',
]

INCLUDE_DEGREE_TYPES = [
    'bachelor of', 'bachelor in', "bachelor's degree",
    'b.e.', 'b.e ', 'b.tech', 'btech ',
    'b.sc', 'bsc ', 'b.a.', 'ba in', 'bba ', 'bca ', 'bfa ',
    'b.com', 'b.pharm', 'bpharm', 'b.arch', 'llb', 'b.ed ', 'beng',
    'associate of', 'associate degree', 'associate in',
    'aa in', 'as in', 'aas ', 'aaa ',
    'foundation degree', 'fda ', 'fdsc ',
    'diploma in', 'diploma of', 'advanced diploma',
    'higher national diploma', 'hnd in', 'hnd ',
    'diploma iii', 'diploma iv',
]

NAV_NOISE = [
    'home', 'about', 'contact', 'login', 'search', 'menu',
    'overview', 'apply now', 'news', 'events', 'research',
    'library', 'sports', 'hostel', 'fees', 'scholarships',
    'placements', 'alumni', 'portal', 'notice', 'announcement',
    'dubai', 'hyderabad', 'goa', 'pilani',
    'higher degree', 'practice school', 'online admissions',
    'doctoral programmes', 'departments', 'campus', 'giving', 'donate',
]

NMC_TRIGGERS = {
    'Korean medium':           ['korean', '한국어'],
    'Japanese medium':         ['japanese', '日本語', 'nihongo'],
    'Russian medium':          ['russian', 'русский'],
    'Chinese medium':          ['chinese', '中文', 'mandarin'],
    'Architecture 5yr':        ['architecture', 'b.arch'],
    'Medicine':                ['medicine', 'medical', 'mbbs'],
    'D3 Indonesia':            ['diploma iii', 'd3 '],
    'D4 Indonesia':            ['diploma iv', 'd4 '],
    'Associate/Community Col': ['associate degree', 'aa in', 'as in'],
    'HND/Foundation':          ['hnd', 'foundation degree', 'fda ', 'fdsc'],
    'College Diploma Canada':  ['college diploma', 'advanced diploma'],
    'Unclear degree type':     ['unclear degree', "bachelor's degree in"],
}

# ─────────────────────────────────────────────────────────
# CONCENTRATION DETECTION
# ─────────────────────────────────────────────────────────

APPLICATION_TIME_PHRASES = [
    'choose your concentration',
    'select your concentration',
    'concentration at the time of application',
    'concentration upon application',
    'declare your concentration',
    'declare concentration at admission',
    'concentration chosen at application',
    'apply directly to',
    'admitted directly into',
    'students apply to the',
    'admission is to the',
    'admitted to the program',
    'choose a track when applying',
    'select a track at application',
    'emphasis chosen at admission',
    'specialization at the time of application',
    'applied to as a separate major',
    'separate admission',
]

CONCENTRATION_INTRO_WORDS = [
    'concentration', 'concentrations',
    'track', 'tracks',
    'emphasis', 'emphases',
    'specialization', 'specializations',
    'specialisation', 'specialisations',
    'option', 'options',
    'pathway', 'pathways',
    'stream', 'streams',
    'strand', 'strands',
    'focus area', 'focus areas',
]


def concentrations_chosen_at_application(page_text):
    """Returns True if concentrations are declared at application time."""
    text_lower = page_text.lower()
    return any(phrase in text_lower for phrase in APPLICATION_TIME_PHRASES)


def concentrations_listed_separately(page_text):
    """Returns True if page lists concentrations as separate items."""
    text_lower = page_text.lower()
    return any(word in text_lower for word in CONCENTRATION_INTRO_WORDS)


# ─────────────────────────────────────────────────────────
# DEGREE NAME FORMATTING
# ─────────────────────────────────────────────────────────

def normalise_degree_type(raw):
    """Convert raw degree string to standard full form."""
    raw_lower = raw.lower().strip()
    for abbrev, full in DEGREE_NORMALISATIONS.items():
        if raw_lower.startswith(abbrev) or raw_lower == abbrev.strip():
            return full
    return raw_lower


def format_programme_name(degree_type, subject=None, concentration=None):
    """
    Format a programme name following the naming rules:

    Standalone (no subject):
      Bachelor of Arts

    With subject:
      BA in Fine Arts           ← abbreviate if allowed
      Bachelor of Laws in X     ← never abbreviate

    With subject + concentration:
      BA in Fine Arts - Graphic Design
    """
    degree_lower = degree_type.lower().strip()

    # ── Standalone
    if not subject:
        return degree_type.title()

    # ── Never-abbreviate degrees
    for no_abbrev in NO_ABBREVIATION:
        if no_abbrev in degree_lower:
            name = f"{degree_type.title()} in {subject.title()}"
            if concentration:
                name += f" - {concentration.title()}"
            return name

    # ── Find abbreviation
    abbrev = None
    for full_form, short in ABBREVIATIONS.items():
        if full_form in degree_lower:
            abbrev = short
            break

    if abbrev:
        name = f"{abbrev} in {subject.title()}"
    else:
        name = f"{degree_type.title()} in {subject.title()}"

    if concentration:
        name += f" - {concentration.title()}"

    return name


def infer_degree_level_from_duration(duration_text):
    """
    Infer Bachelor/Associate/Diploma from duration text.
    Fallback when degree type is unclear.
    """
    if not duration_text:
        return 'Bachelor'

    text = duration_text.lower()
    numbers = re.findall(r'\d+', text)
    if not numbers:
        return 'Bachelor'

    num = int(numbers[0])

    if 'year' in text:
        if num >= 3:   return 'Bachelor'
        elif num == 2: return 'Associate'
        else:          return 'Diploma'

    if 'credit' in text or 'unit' in text or 'ects' in text:
        if num >= 90:  return 'Bachelor'
        elif num >= 50: return 'Associate'
        else:          return 'Diploma'

    return 'Bachelor'


def format_unclear_degree(subject, level):
    """
    Format when degree type is not explicitly stated.
    Uses inferred level written in full.
    """
    subject_title = subject.title() if subject else 'General Studies'
    if level == 'Bachelor':
        return f"Bachelor's Degree in {subject_title}"
    elif level == 'Associate':
        return f"Associate Degree in {subject_title}"
    elif level == 'Diploma':
        return f"Diploma in {subject_title}"
    return f"Bachelor's Degree in {subject_title}"


# ─────────────────────────────────────────────────────────
# INCLUDE / EXCLUDE LOGIC
# ─────────────────────────────────────────────────────────

def is_nav_noise(name):
    name_lower = name.lower().strip()
    if len(name_lower) < 5:
        return True
    if name_lower.startswith('http') or name_lower.count('/') > 1:
        return True
    for noise in NAV_NOISE:
        if name_lower == noise:
            return True
    return False


def should_include(programme_name):
    """
    Returns (True/False/None, reason)
    True  = include
    False = exclude
    None  = subject name only — needs degree type lookup
    """
    name_lower = programme_name.lower().strip()

    if is_nav_noise(programme_name):
        return False, "Nav noise"

    for keyword in EXCLUDE_KEYWORDS:
        if keyword in name_lower:
            return False, f"Excluded: '{keyword}'"

    for keyword in INCLUDE_DEGREE_TYPES:
        if keyword in name_lower:
            return True, "Included"

    return None, "Subject name only — needs degree type lookup"


def get_nmc_flag(programme_name, medium="English"):
    name_lower = programme_name.lower()
    medium_lower = medium.lower()
    for reason, triggers in NMC_TRIGGERS.items():
        for trigger in triggers:
            if trigger in name_lower or trigger in medium_lower:
                return "Yes", reason
    return "No", ""


def get_degree_level(programme_name):
    name_lower = programme_name.lower()

    diploma_keywords = [
        'diploma in', 'diploma of', 'advanced diploma', 'hnd',
        'diploma iii', 'diploma iv', 'fda ', 'fdsc',
        'foundation degree', 'higher national diploma',
    ]
    associate_keywords = [
        'associate', 'aa in', 'as in', 'aas ',
        'associate degree', '전문학사', 'tandai', '短期大学',
    ]

    for k in diploma_keywords:
        if k in name_lower:
            return 'Diploma'
    for k in associate_keywords:
        if k in name_lower:
            return 'Associate'

    return 'Bachelor'
