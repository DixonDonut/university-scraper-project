---
name: university-programme-scraper
description: >-
  Use this skill when the user gives a university website URL and asks to
  scrape, collect, extract, or list programmes, courses, degrees, diplomas,
  or undergraduate offerings. Triggers on: "scrape this university",
  "get all programmes", "collect courses from this site", "find all bachelor
  degrees", "find diplomas", "find associate degrees", "extract undergraduate
  programmes", or any variation of collecting programme data from a university.
version: 1.0
author: your-name
requires:
  - browser-tool
  - python-executor
  - file-writer
---

# University Programme Scraper

## What This Skill Does
Takes a university website URL and systematically collects all eligible
undergraduate programmes — including Bachelor's degrees, Associate degrees,
and Diplomas — that are open to international high school graduates.
Follows a 9-method scraping waterfall and strict include/exclude rules.
Delivers results as a formatted Excel file.

## What to Collect
Collect ALL of the following degree types if open to international HS grads:
- Bachelor's degrees (BSc, BA, BBA, BEng, B.Tech, LLB, etc.)
- Associate degrees (AA, AS, AAS, AAA)
- Diplomas and Advanced Diplomas
- D3 — Diploma III (Indonesia, 3 years)
- D4 — Diploma IV (Indonesia, 4 years)
- Foundation Degrees (UK — FdA, FdSc)
- Higher National Diploma / HND (UK)
- Junior College / Tandai (Japan — 2 years)
- 2-year College Diploma / 전문학사 (Korea)

---

## Pre-Skill Checklist
Before starting:
- [ ] University URL provided by user
- [ ] Browser tool available
- [ ] Python executor available
- [ ] Read PROJECT_RULES.md before scraping any programme
- [ ] If no URL given — ask: "Please paste the university website URL"

---

## Phase 1 — Understand the University

### Step 1 — Visit the Homepage
Open the university URL. Identify:
- Country of the university
- Language of instruction (English / local / both)
- Type — research university, college, community college, polytechnic
- Any obvious programme listing sections in navigation

### Step 2 — Load Country Rules
Before scraping anything, check PROJECT_RULES.md Section 7 for the
specific country's rules. Different countries have very different
degree structures and exclusions.

### Step 3 — Find Programme Listing Pages
Look for these navigation sections:

```
BACHELOR'S PROGRAMMES:
- Programmes / Programs
- Courses
- Academics
- Faculties / Schools / Colleges / Departments
- Undergraduate
- Study with Us
- Our Degrees

DIPLOMA AND ASSOCIATE PROGRAMMES:
- Diplomas
- Associate Degrees
- Vocational Programmes
- Polytechnic Programmes
- Foundation Programmes
- Short Courses (check — may contain diplomas)
- Professional Programmes
- D3 / D4 (Indonesia)
- College Programmes (Canada/Australia)
```

---

## Phase 2 — The 9-Method Scraping Waterfall

Try each method in order. Move to the next ONLY if the current one fails.

---

### Method 1 — web_fetch (Direct — Always Try First)

```python
web_fetch(url, html_extraction_method="markdown", text_content_token_limit=15000)
```

Works for: Static HTML, WordPress, standard university pages.
Failed if: Returns ROBOTS_DISALLOWED, CLIENT_ERROR, or returns only
navigation with no programme content.

---

### Method 2 — Python urllib with Browser Headers

```python
import urllib.request, ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def fetch(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0',
        'Accept': 'text/html,application/xhtml+xml,*/*;q=0.9',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.google.com/',
    })
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            return r.read().decode('utf-8', errors='ignore'), r.geturl()
    except Exception as e:
        return None, str(e)
```

Works for: Sites blocking Claude's tool but not browser-like requests.
Failed if: Still returns HTTP 403/503 with spoofed headers.

---

### Method 3 — Next.js /_next/data/ API Endpoint

```python
import re, json

# Step 1 — get buildId
c, _ = fetch(url)
build_id = re.search(r'"buildId"\s*:\s*"([^"]+)"', c).group(1)

# Step 2 — construct data URL
# Pattern: /_next/data/{buildId}/{locale}/{path}.json
data_url = f"https://site.com/_next/data/{build_id}/en/programmes.json"
c2, _ = fetch(data_url)
data = json.loads(c2)
```

Works for: React/Next.js sites — page source contains "buildId" and __NEXT_DATA__.
Failed if: 404 on data URL, or returns homepage HTML instead.

---

### Method 4 — DOM-Embedded JSON

```python
import re, json

# Look for __NEXT_DATA__
json_blob = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', c, re.DOTALL)
if json_blob:
    data = json.loads(json_blob.group(1))

# Or window.__STATE__
state = re.search(r'window\.__(?:STATE|DATA|APP_STATE)__\s*=\s*({.*?});', c, re.DOTALL)
if state:
    data = json.loads(state.group(1))
```

Works for: React, Vue, Angular SPAs that pre-render initial data in HTML.
Failed if: No JSON blobs in page source.

---

### Method 5 — Sitemap.xml

```python
for sitemap_url in [
    'https://site.com/sitemap.xml',
    'https://site.com/sitemap_index.xml',
    'https://site.com/wp-sitemap.xml',
    'https://site.com/sitemap-1.xml',
]:
    c, _ = fetch(sitemap_url)
    if c and '<urlset' in c:
        urls = re.findall(r'<loc>(https?://[^<]+)</loc>', c)
        # Filter for programme/diploma/degree URLs
        prog_urls = [u for u in urls if any(kw in u for kw in [
            'program', 'programme', 'faculty', 'major', 'degree',
            'diploma', 'associate', 'bachelor', 'course', 'study'
        ])]
        break
```

Works for: WordPress, Drupal, any standard CMS.
Failed if: Sitemap returns 404 or doesn't list individual programme pages.

---

### Method 6 — API Endpoint Discovery

```python
# Fetch homepage and search JS files for API patterns
c, _ = fetch('https://site.com/')
js_files = re.findall(r'src="(/[^"]*\.js[^"]*)"', c)

for js_file in js_files[:5]:
    js_content, _ = fetch('https://site.com' + js_file)
    if js_content:
        api_urls = re.findall(r'["\'](/api/[^"\']+)["\']', js_content)

# Try common API patterns
for api_pattern in [
    '/api/programs', '/api/programmes', '/api/courses',
    '/api/faculties', '/api/degrees', '/api/diplomas',
    '/wp-json/wp/v2/pages?per_page=100'
]:
    c, _ = fetch('https://site.com' + api_pattern)
    if c and len(c) > 100 and '{' in c:
        data = json.loads(c)
```

Works for: Modern university sites with React frontends and REST APIs.
Failed if: All API paths return 404 or HTML error pages.

---

### Method 7 — web_search + web_fetch of Indexed Pages

```python
# Use Google indexed pages
web_search("site:university.edu undergraduate programs bachelor diploma associate")
web_search("site:university.edu/programs OR site:university.edu/courses")
web_search("site:university.edu diploma programmes list")
web_search("site:university.edu associate degree list")

# Then fetch each result URL individually
for result_url in search_results:
    web_fetch(result_url)
```

Works for: Sites serving different content to Googlebot vs scrapers.
Failed if: Site returns 403 even to Google; no results indexed.

---

### Method 8 — PDF Download and Text Extraction

```python
# Find PDF links on the page
pdf_links = re.findall(r'href="([^"]*\.pdf[^"]*)"', c)

# Fetch PDF
web_fetch(pdf_url, web_fetch_pdf_extract_text=True)

# Or extract with pdftotext
import subprocess
result = subprocess.run(
    ['pdftotext', '/path/to/file.pdf', '-'],
    capture_output=True, text=True
)
text = result.stdout
```

Works for: Universities that publish programme lists / admission guides
as PDFs. Especially useful for diploma and associate degree catalogues
which are often only in PDF.
Look for: "Prospectus", "Programme Guide", "Course Catalogue",
"Student Handbook", "Admission Guide".

---

### Method 9 — Manual Compilation from Search Results (Last Resort)

1. `web_search` for "UniversityName all bachelor programmes 2025 2026"
2. `web_search` for "UniversityName diploma programmes list"
3. `web_search` for "UniversityName associate degree programmes"
4. `web_search` for "site:university.edu bachelor OR diploma OR associate"
5. Check university Wikipedia page for college/department structure
6. Check third-party aggregators (Study.eu, Mastersportal, uni-assist)
7. Cross-reference multiple sources to build the complete list

Note: Always verify URLs in a browser before including in the Excel file.

---

## Phase 3 — Apply Include and Exclude Rules

For every programme found, check against PROJECT_RULES.md Sections 1 and 2.

### Quick Include Checklist
- [ ] Is it a Bachelor, Associate, Diploma, D3, D4, HND, FdA, FdSc, or Junior College degree?
- [ ] Is it open to international high school graduates?
- [ ] Is it full-time?
- [ ] Is it on-campus?
- [ ] Is it minimum 8 months?

### Quick Exclude Checklist
- [ ] Is it a Masters, PhD, or Postgrad? → EXCLUDE
- [ ] Is it part-time only? → EXCLUDE
- [ ] Is it online/distance only? → EXCLUDE
- [ ] Does it require a prior degree? → EXCLUDE
- [ ] Is it restricted to citizens only? → EXCLUDE
- [ ] Is it a post-bachelor diploma? → EXCLUDE
- [ ] Is it a diploma top-up requiring prior D3? → EXCLUDE
- [ ] Is it under 8 months? → EXCLUDE
- [ ] Is it HNC (UK)? → EXCLUDE
- [ ] Is it German Diplom or Staatsexamen? → EXCLUDE
- [ ] Is it DEC-BAC (Canada)? → EXCLUDE
- [ ] Is it Indonesian Employee Class, PJJ, or Profession Study? → EXCLUDE

---

## Phase 4 — Format Programme Names

Apply PROJECT_RULES.md Section 3 naming rules to every programme.

### Quick Naming Reference

| Degree Found | How to Write It |
|---|---|
| BSc Computer Science | `BSc in Computer Science` |
| Bachelor of Business | `Bachelor of Business` |
| Diploma in Tourism | `Diploma in Tourism` |
| Advanced Diploma Marketing | `Advanced Diploma in Marketing` |
| D3 Akuntansi (Indonesia) | `Diploma III in Accounting` |
| D4 Teknologi Informasi | `Diploma IV in Information Technology` |
| AA Liberal Arts | `AA in Liberal Arts` |
| Associate of Science | `AS in [Subject]` |
| FdA Early Childhood | `FdA in Early Childhood Studies` |
| HND Business | `HND in Business` |
| 전문학사 경영 (Korea) | `Associate Degree in Business Administration` |
| 短期大学士 (Japan) | `Associate Degree in [Subject]` |

### Degree Level Column Values
- `Bachelor` — for all bachelor's degrees
- `Associate` — for AA, AS, AAS, AAA, 2-year college, junior college
- `Diploma` — for Diploma, Advanced Diploma, D3, D4, HND, FdA, FdSc

---

## Phase 5 — Assign NMC Flags

For every programme, check PROJECT_RULES.md Section 5.

### Fast NMC: Yes Triggers
- Korean-medium instruction → Yes
- Japanese-medium instruction → Yes
- Russian-medium instruction → Yes
- Chinese-medium instruction → Yes
- D3 or D4 (Indonesia) → Yes
- Associate Degree at community college → Yes
- HND or Foundation Degree (UK) → Yes
- College Diploma (Canada) → Yes
- Architecture 5-year → Yes
- Diploma pathway that may lead to Bachelor's only → Yes
- Any programme you are uncertain about → Yes

### Fast NMC: No
- English-medium at a university that clearly welcomes international HS grads

---

## Phase 6 — Verify URLs

For every programme URL found, verify it works:

```python
def check_url(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=8, context=ctx) as r:
            return r.status, r.geturl()
    except Exception as e:
        return None, str(e)

code, final_url = check_url(url)
# 200 = good
# 503 from scraper but loads in browser = include, flag NMC: Yes
# Redirects to homepage = page doesn't exist, use parent URL
# 404 = broken — find correct URL before including
```

---

## Phase 7 — Build the Excel File

Create an Excel file named `[UniversityName]-programmes.xlsx`

### Column Structure

| Column | Content |
|---|---|
| A | Course Name (formatted per naming rules) |
| B | Degree Level (Bachelor / Associate / Diploma) |
| C | Programme Page URL (=HYPERLINK formula) |
| D | Duration |
| E | Tuition Fee |
| F | Medium of Instruction |
| G | Needs Manual Check (Yes / No) |

Add country-specific columns as needed:
- CRICOS Code (Australia)
- Intakes / Start Dates
- School / Faculty / College

### Row Colours

```python
from openpyxl.styles import PatternFill, Font

# Bachelor rows — standard
bachelor_fill_1 = PatternFill("solid", fgColor="D6E4F0")   # blue
bachelor_fill_2 = PatternFill("solid", fgColor="FFFFFF")    # white alternating

# Diploma and Associate rows
diploma_fill = PatternFill("solid", fgColor="FCE4D6")       # orange

# NMC: Yes rows (any degree type)
nmc_fill = PatternFill("solid", fgColor="FFF2CC")           # yellow

# English-medium at non-English universities
english_track_fill_1 = PatternFill("solid", fgColor="E2EFDA")   # green
english_track_fill_2 = PatternFill("solid", fgColor="EBF5E1")   # light green alt

# Header
header_fill = PatternFill("solid", fgColor="1F3864")        # dark navy
```

### Font Colours

```python
# Standard rows
standard_font = Font(color="000000")

# NMC: Yes
nmc_font = Font(color="7F6000")

# English-medium tracks at non-English universities
english_track_font = Font(color="375623")

# Diploma and Associate rows
diploma_font = Font(color="833C00")

# URL column
url_font = Font(color="0563C1", underline="single")

# Header
header_font = Font(color="FFFFFF", bold=True)
```

### Other Formatting

```python
# Freeze header row
ws.freeze_panes = "A2"

# Auto-filter
ws.auto_filter.ref = ws.dimensions

# Row height
for row in ws.iter_rows():
    ws.row_dimensions[row[0].row].height = 18

# URL column formula
ws['C2'] = '=HYPERLINK("https://university.edu/programme","https://university.edu/programme")'
```

---

## Phase 8 — Deliver Results

After building the Excel file:

1. Save as `[UniversityName]-programmes.xlsx`
2. Report a summary:

---

## 📊 Scrape Complete — [UNIVERSITY NAME]

**Total programmes found:** [NUMBER]
**Breakdown:**
- Bachelor's degrees: [NUMBER]
- Associate degrees: [NUMBER]
- Diplomas: [NUMBER]

**NMC: Yes:** [NUMBER]
**NMC: No:** [NUMBER]

**Scraping method used:** [Method 1-9]
**Pages visited:** [NUMBER]
**Notes:** [Any issues, exclusions, or flags]

---

3. Ask the user:
"Would you like me to:
1. Scrape the next university
2. Add more columns to this file
3. Review any specific programme inclusion/exclusion decisions"

---

## Common Anti-Scraping Fixes

| Pattern | Symptom | Fix |
|---|---|---|
| Cloudflare | Empty HTML, 503, challenge page | Method 2 with different UA |
| JS-only rendering | Nav skeleton, no programme data | Methods 3-6 |
| Session/cookie required | 302 redirect to login | Check for cookie-free APIs |
| Rate limiting | First fetch OK, then 429 | Add time.sleep(0.3-0.5) |
| IP blocking | All methods fail | Method 7 — Google indexed pages |
| robots.txt disallow | ROBOTS_DISALLOWED in web_fetch | Switch to Method 2 |
| Diploma data in PDF only | No diploma list on web pages | Method 8 — PDF extraction |

---

## Post-Skill Checklist
- [ ] All three degree types checked — Bachelor, Associate, Diploma
- [ ] Include/exclude rules applied to every programme
- [ ] All names formatted per naming rules
- [ ] Degree Level column filled for every row
- [ ] NMC flags assigned
- [ ] All URLs verified
- [ ] Excel formatted with correct colours and fonts
- [ ] Summary delivered to user
- [ ] Follow-up question asked
