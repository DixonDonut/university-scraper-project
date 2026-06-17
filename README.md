# University Programme Scraper

Collects Bachelor's degrees, Associate degrees, and Diploma 
programmes from university websites that are open to 
international high school graduates.

Outputs a formatted Excel file per university with correct 
colours, degree levels, and NMC flags.

---

## What It Collects

- Bachelor's degrees (BSc, BA, BBA, BEng, B.Tech, LLB, etc.)
- Associate degrees (AA, AS, AAS)
- Diplomas (Diploma, Advanced Diploma, HND, D3, D4)

Only programmes open to international high school graduates.
Full-time, on-campus, minimum 8 months duration.

---

## Setup

### 1. Install Python dependencies
pip install -r requirements.txt

### 2. Install Claude Code (for difficult sites)
curl -fsSL https://claude.ai/install.sh | sh

---

## Usage

### Single university
python3 -m scraper.main https://university.edu \
  --name "University Name" \
  --country UK \
  -v

### Batch from file
python3 -m scraper.main --file universities.txt -v

### Using Claude Code (for bot-protected sites)
claude
> Scrape all universities in universities.txt

---

## universities.txt Format

One university per line using pipe-separated format:

URL | University Name | Country

Example:
https://www.manchester.ac.uk/study/undergraduate/courses/ | University of Manchester | UK
https://www.bits-pilani.ac.in/academics/ | BITS Pilani | India

Important — always use direct programme listing pages,
not the university homepage.

---

## Output

Results saved to results/ folder.
One Excel file per university: universityname-programmes.xlsx

Each file contains:
- Course Name
- Degree Level (Bachelor / Associate / Diploma)
- Programme Page URL
- Duration
- Tuition Fee
- Medium of Instruction
- Needs Manual Check (Yes / No)

Row colours:
- Yellow  = NMC: Yes — needs manual verification
- Orange  = Diploma or Associate degree
- Green   = English-medium at non-English university
- Blue    = Standard Bachelor degree

---

## Scraping Methods

Tries 6 automated methods in order:
1. urllib with browser headers
2. Next.js API endpoints
3. DOM-embedded JSON
4. Sitemap.xml
5. API endpoint discovery
6. Falls back to Claude Code for difficult sites

---

## Project Rules

All include/exclude logic is in:
.claude/skills/university-programme-scraper/PROJECT_RULES.md

Covers 14 countries with specific rules for:
Korea, Japan, Indonesia, Spain, Germany, Canada,
Australia, UK, USA, Russia, China, Finland,
Kuwait/UAE, Caribbean

---

## Project Structure

university-scraper-project/
├── .claude/skills/          ← skill files for Claude Code
├── scraper/
│   ├── main.py              ← run this
│   ├── fetcher.py           ← 6 scraping methods
│   ├── parser.py            ← extracts programme data
│   ├── rules.py             ← include/exclude logic
│   └── excel_writer.py      ← builds Excel output
├── universities.txt         ← list of URLs to scrape
├── results/                 ← Excel files saved here
└── requirements.txt
