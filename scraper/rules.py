# scraper/rules.py
# Fixed version — properly excludes Masters/PhD, filters nav noise

EXCLUDE_KEYWORDS = [
    # Postgraduate — catch these FIRST before include check
    'm.sc', 'msc ', 'm.e.', 'm.e ', 'm.tech', 'mtech',
    'm.pharm', 'mpharm', 'm.b.a', 'mba', 'm.phil', 'mphil',
    'master', 'masters', 'postgraduate', 'post-graduate', 'post graduate',
    'phd', 'ph.d', 'doctorate', 'doctoral', 'doctor of',
    'm.com', 'mcom', 'm.fa', 'med ', 'm.ed',
    # Section headings that are not real programmes
    'higher degree', 'integrated first degree', 'doctoral programme',
    'online admission', 'practice school',
    # Nav and menu items
    'hyderabad', 'dubai', 'pilani', 'goa campus',
    'faculty page', 'about us', 'contact us',
    # German
    'staatsexamen', 'kirchliches',
    # Spanish
    'medicina', 'odontolog', 'farmacia', 'veterinaria', 'nivelaci',
    # Indonesian
    'kelas karyawan', 'pjj', 'profesi', 'ners', 'apoteker',
    'kelas konversi', 'alih jenjang',
    # Other
    'dec-bac', 'rn-bsn', 'rnbsn', 'top-up programme',
    'baes', 'basus', 'hnc ', 'post-graduate diploma',
    'graduate certificate', 'conversion class',
]

INCLUDE_DEGREE_TYPES = [
    # Bachelor — longer strings first to avoid partial matches
    'bachelor of', 'bachelor in', "bachelor's",
    'b.e.', 'b.e ', 'b.tech', 'btech ',
    'b.sc', 'bsc ', 'b.a.', 'ba ', 'bba ', 'bca ', 'bfa ',
    'b.com', 'b.pharm', 'bpharm', 'b.arch', 'llb',
    'b.ed ', 'bed ',
    # Associate
    'associate of', 'associate degree', 'associate in',
    'aa in', 'as in', 'aas ', '전문학사', '短期大学',
    'tandai', 'foundation degree', 'fda ', 'fdsc ',
    # Diploma
    'diploma in', 'diploma of', 'advanced diploma',
    'higher national diploma', 'hnd in', 'hnd ',
    'diploma iii', 'diploma iv',
]

# Nav links, menu items, campus names — never real programmes
NAV_NOISE = [
    'admissions', 'academics', 'home', 'about', 'contact',
    'login', 'search', 'menu', 'overview', 'apply now',
    'news', 'events', 'research', 'library', 'sports',
    'hostel', 'fees', 'scholarships', 'placements', 'alumni',
    'portal', 'notice', 'announcement', 'tender',
    'dubai', 'hyderabad', 'goa', 'pilani',
    'integrated first degree', 'higher degree',
    'practice school', 'online admissions', 'doctoral programmes',
    'faculty', 'departments', 'campus', 'university',
]

NMC_TRIGGERS = {
    'Korean medium':           ['korean', '한국어'],
    'Japanese medium':         ['japanese', '日本語', 'nihongo'],
    'Russian medium':          ['russian', 'русский'],
    'Chinese medium':          ['chinese', '中文', 'mandarin'],
    'Architecture 5yr':        ['architecture', 'b.arch', 'arquitectura'],
    'Medicine':                ['medicine', 'medical', 'mbbs'],
    'D3 Indonesia':            ['diploma iii', 'd3 '],
    'D4 Indonesia':            ['diploma iv', 'd4 '],
    'Associate/Community Col': ['associate degree', 'aa in', 'as in'],
    'HND/Foundation':          ['hnd', 'foundation degree', 'fda ', 'fdsc'],
    'College Diploma Canada':  ['college diploma', 'advanced diploma'],
}


def is_nav_noise(name):
    """Returns True if the name looks like a nav link not a programme."""
    name_lower = name.lower().strip()

    # Too short
    if len(name_lower) < 8:
        return True

    # URL fragment
    if name_lower.startswith('http') or name_lower.count('/') > 1:
        return True

    # Exact match or starts with nav noise word
    for noise in NAV_NOISE:
        if name_lower == noise:
            return True

    return False


def should_include(programme_name):
    """
    Returns (True/False/None, reason)
    True  = include
    False = exclude
    None  = unknown degree type — flag for manual check
    """
    name_lower = programme_name.lower().strip()

    # Step 1 — filter nav noise first
    if is_nav_noise(programme_name):
        return False, f"Nav noise — skipped"

    # Step 2 — exclusions BEFORE inclusions
    # This catches M.Sc, M.E, PhD etc even if they have
    # degree-like words nearby
    for keyword in EXCLUDE_KEYWORDS:
        if keyword in name_lower:
            return False, f"Excluded: '{keyword}'"

    # Step 3 — inclusions
    for keyword in INCLUDE_DEGREE_TYPES:
        if keyword in name_lower:
            return True, "Included"

    # Step 4 — unknown
    return None, "Unknown degree type — manual check needed"


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
        'foundation degree', 'higher national diploma'
    ]
    associate_keywords = [
        'associate', 'aa in', 'as in', 'aas ',
        '전문학사', 'tandai', '短期大学', 'junior college'
    ]

    for k in diploma_keywords:
        if k in name_lower:
            return 'Diploma'

    for k in associate_keywords:
        if k in name_lower:
            return 'Associate'

    return 'Bachelor'
