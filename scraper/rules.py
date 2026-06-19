# scraper/rules.py
# Degree rules, naming, NMC flags, include/exclude logic.
# Works universally for any university.

import re
from scraper.name_quality import (
    should_include_by_quality, is_valid_concentration_name,
    is_hard_excluded, is_nav_noise, is_school_or_unit_name,
    is_sentence_fragment, DEGREE_QUALITY_SIGNALS,
)

# ─────────────────────────────────────────────────────────
# DEGREE ABBREVIATION RULES
# ─────────────────────────────────────────────────────────

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

# These degrees never get abbreviated even when subject present
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

DEGREE_NORMALISATIONS = {
    'b.a.': 'bachelor of arts',      'b.a': 'bachelor of arts',
    'ba ':  'bachelor of arts',      'b.s.': 'bachelor of science',
    'b.s':  'bachelor of science',   'bs ': 'bachelor of science',
    'bsc ': 'bachelor of science',   'b.sc': 'bachelor of science',
    'bfa ': 'bachelor of fine arts', 'b.f.a': 'bachelor of fine arts',
    'bba ': 'bachelor of business administration',
    'b.b.a': 'bachelor of business administration',
    'bca ': 'bachelor of computer applications',
    'b.e.': 'bachelor of engineering', 'b.e ': 'bachelor of engineering',
    'beng ': 'bachelor of engineering', 'b.eng': 'bachelor of engineering',
    'be in': 'bachelor of engineering in',
    'llb': 'bachelor of laws',
    'b.tech': 'bachelor of technology', 'btech': 'bachelor of technology',
    'b.com': 'bachelor of commerce',   'bcom': 'bachelor of commerce',
    'b.ed': 'bachelor of education',   'bed ': 'bachelor of education',
    'b.arch': 'bachelor of architecture',
    'b.pharm': 'bachelor of pharmacy',
    'b.sc (hons)': 'bachelor of science',
    'b.a. (hons)': 'bachelor of arts',
    'a.a.': 'associate of arts',
    'a.s.': 'associate of science',
    'a.a.s': 'associate of applied science',
    'd3': 'diploma iii', 'd4': 'diploma iv',
}

# ─────────────────────────────────────────────────────────
# PROJECT-LEVEL EXCLUSIONS
# These apply to any university — per PROJECT_RULES.md
# ─────────────────────────────────────────────────────────

PROJECT_EXCLUSIONS = [
    # Postgraduate
    'm.sc', 'msc ', 'm.s.', ' ms ', 'm.e.', 'm.e ', 'm.tech', 'mtech',
    'm.pharm', 'mpharm', 'm.b.a', ' mba', 'm.phil', 'mphil',
    'master', 'masters', 'postgraduate', 'post-graduate', 'post graduate',
    'phd', 'ph.d', 'doctorate', 'doctoral', 'doctor of',
    'm.com', 'mcom', 'm.ed', ' med ', 'm.arch',
    # Professional degrees excluded per PROJECT_RULES.md
    'veterinary medicine', 'doctor of veterinary', 'd.v.m', 'dvm ',
    'doctor of medicine', 'doctor of dental',
    # Germany
    'staatsexamen', 'kirchliches',
    # Spain
    'odontolog', 'nivelaci',
    # Indonesia
    'kelas karyawan', 'pjj ', 'profesi ', 'ners ', 'apoteker',
    'kelas konversi', 'alih jenjang',
    # Other
    'dec-bac', 'rn-bsn', 'rnbsn', 'rn to bsn', 'rn-to-bsn',
    'baes', 'basus', 'hnc ',
    'post-graduate diploma', 'graduate certificate', 'conversion class',
    # Minors
    ' minor', 'minors',
    # WSU / general nav and unit noise
    'degree finder', 'back to degree',
    'humane society', 'externship program',
    'pre-veterinary', 'salmonid',
    'honors accelerated', 'veterinary microbiology',
    'veterinary clinical', 'alliance education',
    # UNR / general noise
    ' emphasis',
    'credential assembly',
    'projected openings',
    'according to the bls',
    'free members',
    'bi-md',
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
    'pathway', 'pathways',
    'stream', 'streams',
    'strand', 'strands',
    'focus area', 'focus areas',
]

NMC_TRIGGERS = {
    'Korean medium':           ['korean', '한국어'],
    'Japanese medium':         ['japanese', '日本語', 'nihongo'],
    'Russian medium':          ['russian', 'русский'],
    'Chinese medium':          ['chinese', '中文', 'mandarin'],
    'Architecture 5yr':        ['bachelor of architecture', 'b.arch'],
    'Medicine':                ['medicine', 'medical', 'mbbs'],
    'D3 Indonesia':            ['diploma iii', 'd3 '],
    'D4 Indonesia':            ['diploma iv', 'd4 '],
    'Associate/Community Col': ['associate of', 'aa in', 'as in', 'aas '],
    'HND/Foundation':          ['hnd', 'foundation degree', 'fda ', 'fdsc'],
    'College Diploma Canada':  ['college diploma', 'advanced diploma'],
}


def concentrations_chosen_at_application(page_text):
    text_lower = page_text.lower()
    return any(phrase in text_lower for phrase in APPLICATION_TIME_PHRASES)


def concentrations_listed_separately(page_text):
    text_lower = page_text.lower()
    return any(word in text_lower for word in CONCENTRATION_INTRO_WORDS)


# ─────────────────────────────────────────────────────────
# DEGREE NAME FORMATTING
# ─────────────────────────────────────────────────────────

def normalise_degree_type(raw):
    raw_lower = raw.lower().strip()
    for abbrev, full in DEGREE_NORMALISATIONS.items():
        if raw_lower.startswith(abbrev) or raw_lower == abbrev.strip():
            return full
    return raw_lower


def format_programme_name(degree_type, subject=None, concentration=None):
    """
    Format per naming rules:
    - No subject  → full form:   Bachelor of Arts
    - With subject → abbreviate: BA in Fine Arts
    - With conc   → add dash:   BA in Fine Arts - Graphic Design
    - Never-abbrev → full form: Bachelor of Laws in X
    """
    degree_lower = degree_type.lower().strip()

    if not subject:
        return degree_type.title()

    for no_abbrev in NO_ABBREVIATION:
        if no_abbrev in degree_lower:
            name = f"{degree_type.title()} in {subject.title()}"
            if concentration:
                name += f" - {concentration.title()}"
            return name

    abbrev = None
    for full_form, short in ABBREVIATIONS.items():
        if full_form in degree_lower:
            abbrev = short
            break

    name = f"{abbrev} in {subject.title()}" if abbrev else f"{degree_type.title()} in {subject.title()}"

    if concentration:
        name += f" - {concentration.title()}"

    name = name.replace(' In ', ' in ')
    return name


def infer_degree_level_from_duration(duration_text):
    """
    Infer Bachelor/Associate/Diploma from duration with sanity checks.
    """
    if not duration_text:
        return 'Bachelor'

    text = duration_text.lower()
    numbers = re.findall(r'\d+', text)
    if not numbers:
        return 'Bachelor'

    num = int(numbers[0])

    if 'year' in text:
        if num < 1 or num > 8:   return 'Bachelor'  # sanity check
        if num >= 3:              return 'Bachelor'
        elif num == 2:            return 'Associate'
        else:                     return 'Diploma'

    if 'credit' in text or 'unit' in text or 'ects' in text:
        if num < 20 or num > 240: return 'Bachelor'  # sanity check
        if num >= 90:             return 'Bachelor'
        elif num >= 50:           return 'Associate'
        else:                     return 'Diploma'

    return 'Bachelor'


def normalise_programme_name(name):
    """
    Convert raw scraped names to standard formatted names.
    'Bachelor of Science in Accounting'  → 'BSc in Accounting'
    'Accounting (B.S.)'                  → 'BSc in Accounting'
    'BA in Anthropology'                 → 'BA in Anthropology'  (unchanged)
    """
    name_stripped = name.strip()

    # Pattern: "Subject (B.X.)" — e.g. "Accounting (B.S.)"
    abbrev_suffix = re.match(
        r'^(.+?)\s*\((B\.S\.|B\.A\.|B\.F\.A\.|B\.B\.A\.|B\.Arch\.?|'
        r'B\.S\.N\.|B\.S\.W\.|B\.Mus\.?|B\.E\.|BFA|BBA|BArch|BSN|BSW|BMus|BS|BA)\s*'
        r'(?:in\s+.+?)?\)$',
        name_stripped, re.I
    )
    if abbrev_suffix:
        subject = abbrev_suffix.group(1).strip()
        raw_abbrev = abbrev_suffix.group(2).lower().replace('.', '').replace(' ', '')
        abbrev_map = {
            'bs': 'BSc', 'ba': 'BA', 'bfa': 'BFA', 'bba': 'BBA',
            'barch': 'BArch', 'bsn': 'BSN', 'bsw': 'BSW', 'bmus': 'BMus',
            'be': 'BEng',
        }
        short = abbrev_map.get(raw_abbrev, raw_abbrev.upper())
        return f"{short} in {subject.title()}"

    # Pattern: "Bachelor of X in Subject" or "Bachelor of X Subject" (no 'in')
    full_match = re.match(
        r'(bachelor of (?:arts|science|fine arts|business administration|'
        r'applied science|music|nursing|social work|laws|technology|'
        r'commerce|education|architecture|pharmacy|engineering|design|'
        r'public health|social science|information technology|'
        r'environmental science|international studies|urban planning))'
        r'(?:\s+in\s+(.+)|\s+(.+))?$',
        name_stripped, re.I
    )
    if full_match:
        degree_type = full_match.group(1)
        subject = (full_match.group(2) or full_match.group(3) or '').strip() or None
        if subject:
            subject = subject.strip()
        return format_programme_name(degree_type, subject)

    # Pattern: "Bachelor's Degree in X" — fix apostrophe if mangled by .title()
    bachelors_match = re.match(
        r"bachelor'?s?\s+degree\s+in\s+(.+)$", name_stripped, re.I
    )
    if bachelors_match:
        subject = bachelors_match.group(1).strip().title()
        return f"Bachelor's Degree in {subject}"

    return name_stripped


def format_unclear_degree(subject, level):
    """Format when degree type is not explicitly stated."""
    subject_title = subject.title() if subject else 'General Studies'
    if level == 'Bachelor':   return f"Bachelor's Degree in {subject_title}"
    elif level == 'Associate': return f"Associate Degree in {subject_title}"
    elif level == 'Diploma':   return f"Diploma in {subject_title}"
    return f"Bachelor's Degree in {subject_title}"


# ─────────────────────────────────────────────────────────
# MAIN INCLUDE / EXCLUDE LOGIC
# ─────────────────────────────────────────────────────────

def should_include(programme_name):
    """
    Returns (True/False/None, reason)
    True  = include
    False = exclude
    None  = subject name only — needs degree type lookup

    Uses three layers:
    1. Universal quality checks (name_quality.py)
    2. Project-level exclusions (PROJECT_RULES.md)
    3. Degree type keyword matching
    """
    name_lower = programme_name.lower().strip()

    # Layer 1 — Universal quality checks
    quality, reason = should_include_by_quality(programme_name)
    if quality == 'exclude':
        return False, reason

    # Layer 2 — Project-level exclusions (Masters, PhD, etc.)
    for keyword in PROJECT_EXCLUSIONS:
        if keyword in name_lower:
            return False, f"Project exclusion: '{keyword}'"

    # Layer 3 — Degree type keywords
    if quality == 'include':
        return True, 'Degree keyword detected'

    for keyword in INCLUDE_DEGREE_TYPES:
        if keyword in name_lower:
            return True, 'Included'

    # Unknown — subject name only
    return None, 'Subject name only — needs degree type lookup'


def get_nmc_flag(programme_name, medium="English", country="Unknown"):
    """
    Determine NMC flag universally.
    Logic:
    - Specific language requirements → Yes
    - Architecture 5yr → Yes
    - Medicine → Yes
    - Associate/community college → Yes (verify eligibility)
    - Unclear degree level (Bachelor's Degree in X format, English) → No
    - Everything else English-medium → No
    """
    name_lower = programme_name.lower()
    medium_lower = medium.lower()

    # Specific NMC triggers
    for trigger_reason, triggers in NMC_TRIGGERS.items():
        for trigger in triggers:
            if trigger in name_lower or trigger in medium_lower:
                return "Yes", trigger_reason

    # Unclear degree type but English medium — still NMC: No
    # because we know it IS a bachelor's/associate/diploma,
    # just not the exact abbreviation
    if "bachelor's degree in" in name_lower and medium_lower == 'english':
        return "No", ""

    if "associate degree in" in name_lower:
        return "Yes", "Associate degree — verify eligibility"

    if "diploma in" in name_lower and medium_lower != 'english':
        return "Yes", "Non-English diploma"

    # Non-English medium → always NMC: Yes
    if medium_lower not in ('english', 'en', ''):
        return "Yes", f"Non-English medium: {medium}"

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
        if k in name_lower: return 'Diploma'
    for k in associate_keywords:
        if k in name_lower: return 'Associate'
    return 'Bachelor'
