# scraper/main.py
# Master script — ties all modules together
# Usage:
#   python3 -m scraper.main https://university.edu --name "University Name" --country UK
#   python3 -m scraper.main --file universities.txt --country UK

import sys
import os
import argparse
import time
import json

# Add parent directory to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper.fetcher import (
    fetch, fetch_nextjs, fetch_embedded_json,
    fetch_sitemap, discover_api, verify_url
)
from scraper.parser import parse_programmes, parse_json_programmes
from scraper.rules import should_include, get_nmc_flag, get_degree_level
from scraper.excel_writer import write_excel


def scrape_university(url, name=None, country="Unknown", verbose=False):
    """
    Scrape a single university URL.
    Returns list of eligible programmes or None if scraping failed.
    """
    domain = url.split('/')[2].replace('www.', '')
    university_name = name or domain

    print(f"\n{'='*60}")
    print(f"🏫 {university_name}")
    print(f"🔗 {url}")
    print(f"🌍 Country: {country}")
    print(f"{'='*60}")

    content     = None
    method_used = None
    all_programmes = []

    # ── Method 2 — urllib with browser headers
    print("  → Method 2: urllib with browser headers...")
    content, final_url = fetch(url)
    if content and len(content) > 1000:
        method_used = 2
        print(f"  ✅ Method 2 succeeded ({len(content):,} chars)")
    else:
        print(f"  ❌ Method 2 failed")
        content = None

    # ── Method 3 — Next.js API
    if not content:
        print("  → Method 3: Next.js API...")
        data = fetch_nextjs(url)
        if data:
            method_used = 3
            all_programmes = parse_json_programmes(data, url)
            print(f"  ✅ Method 3 succeeded — {len(all_programmes)} raw entries")

    # ── Method 4 — DOM-embedded JSON
    if not content and not all_programmes:
        print("  → Method 4: DOM-embedded JSON...")
        raw, _ = fetch(url)
        if raw:
            data = fetch_embedded_json(raw)
            if data:
                method_used = 4
                all_programmes = parse_json_programmes(data, url)
                print(f"  ✅ Method 4 succeeded — {len(all_programmes)} raw entries")

    # ── Method 5 — Sitemap
    if not content and not all_programmes:
        print("  → Method 5: Sitemap...")
        prog_urls = fetch_sitemap(url)
        if prog_urls:
            method_used = 5
            print(f"  ✅ Method 5: visiting {len(prog_urls[:30])} programme pages...")
            for prog_url in prog_urls[:30]:
                page_content, _ = fetch(prog_url)
                if page_content:
                    content = (content or '') + page_content
                time.sleep(0.3)

    # ── Method 6 — API discovery
    if not content and not all_programmes:
        print("  → Method 6: API endpoint discovery...")
        data = discover_api(url)
        if data:
            method_used = 6
            all_programmes = parse_json_programmes(data, url)
            print(f"  ✅ Method 6 succeeded — {len(all_programmes)} raw entries")

    # ── If we have HTML content, parse it
    if content and not all_programmes:
        print(f"  Parsing HTML content...")
        all_programmes = parse_programmes(content, url)
        print(f"  Found {len(all_programmes)} raw entries from HTML")

    if not all_programmes:
        print(f"\n  ❌ All methods failed for {university_name}")
        print(f"  💡 Try these direct URLs instead:")
        domain_base = '/'.join(url.split('/')[:3])
        suggestions = get_direct_url_suggestions(domain_base, country)
        for s in suggestions:
            print(f"     {s}")
        return None

    # ── Apply include/exclude rules
    included  = []
    excluded  = []
    unknown   = []

    for prog in all_programmes:
        name_val = prog['name']
        result, reason = should_include(name_val)

        if result is True:
            level       = get_degree_level(name_val)
            nmc, nmc_r  = get_nmc_flag(name_val)

            included.append({
                'name':     name_val,
                'level':    level,
                'url':      prog.get('url', ''),
                'duration': prog.get('duration', ''),
                'fee':      prog.get('fee', ''),
                'medium':   prog.get('medium', 'English'),
                'nmc':      nmc,
                'nmc_reason': nmc_r,
            })

        elif result is False:
            excluded.append({'name': name_val, 'reason': reason})

        else:
            # Unknown — flag as NMC: Yes and include
            level = get_degree_level(name_val)
            unknown.append({
                'name':     name_val,
                'level':    level,
                'url':      prog.get('url', ''),
                'duration': '',
                'fee':      '',
                'medium':   'English',
                'nmc':      'Yes',
                'nmc_reason': 'Unknown degree type — manual check needed',
            })

    all_final = included + unknown

    # ── Print results
    bachelors  = [p for p in all_final if p['level'] == 'Bachelor']
    associates = [p for p in all_final if p['level'] == 'Associate']
    diplomas   = [p for p in all_final if p['level'] == 'Diploma']
    nmc_yes    = [p for p in all_final if p['nmc'] == 'Yes']

    print(f"\n  📊 Results:")
    print(f"     ✅ Included:    {len(included)}")
    print(f"     ❓ Unknown:     {len(unknown)}")
    print(f"     ❌ Excluded:    {len(excluded)}")
    print(f"     Bachelor's:    {len(bachelors)}")
    print(f"     Associate:     {len(associates)}")
    print(f"     Diploma:       {len(diplomas)}")
    print(f"     NMC Yes:       {len(nmc_yes)}")
    print(f"     Method used:   {method_used}")

    if verbose and excluded[:5]:
        print(f"\n  Sample excluded:")
        for e in excluded[:5]:
            print(f"     ❌ {e['name'][:60]} — {e['reason']}")

    return all_final


def get_direct_url_suggestions(domain, country):
    """Return suggested direct programme page URLs for a university."""
    suggestions = []
    country_upper = country.upper()

    common = [
        f"{domain}/study/undergraduate/courses",
        f"{domain}/programmes/undergraduate",
        f"{domain}/academics/programs",
        f"{domain}/departments",
        f"{domain}/faculties",
    ]

    country_specific = {
        'UK':     [
            f"{domain}/study/undergraduate/courses/course-listing",
            f"{domain}/courses/undergraduate",
        ],
        'USA':    [
            f"{domain}/admissions/undergraduate-admissions/academic-programs.html",
            f"{domain}/academics/majors",
        ],
        'CANADA': [
            f"{domain}/programs#mode=by-faculty",
            f"{domain}/future-students/programs",
        ],
        'INDIA':  [
            f"{domain}/academics/programs",
            f"{domain}/departments",
        ],
        'AUSTRALIA': [
            f"{domain}/courses/undergraduate",
            f"{domain}/study/undergraduate",
        ],
    }

    suggestions.extend(common)
    if country_upper in country_specific:
        suggestions.extend(country_specific[country_upper])

    return suggestions[:6]


def main():
    parser = argparse.ArgumentParser(
        description='University Programme Scraper'
    )
    parser.add_argument('url', nargs='?',
                        help='University URL to scrape')
    parser.add_argument('--name', default=None,
                        help='University name (for Excel filename)')
    parser.add_argument('--country', default='Unknown',
                        help='Country (e.g. UK, USA, India, Canada, Australia)')
    parser.add_argument('--file', default=None,
                        help='Text file with one URL per line')
    parser.add_argument('--output', default='results',
                        help='Output directory (default: results)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Show sample excluded programmes')
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    # ── Batch mode — read from file
    if args.file:
        print(f"\n📋 Reading URLs from {args.file}")
        with open(args.file, 'r') as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith('#')]

        print(f"   Found {len(lines)} universities")
        results_summary = []

        for line in lines:
            # Support "URL | Name | Country" format in the file
            parts = [p.strip() for p in line.split('|')]
            url     = parts[0]
            name    = parts[1] if len(parts) > 1 else None
            country = parts[2] if len(parts) > 2 else args.country

            programmes = scrape_university(
                url, name=name, country=country, verbose=args.verbose
            )

            if programmes:
                uni_name = name or url.split('/')[2].replace('www.', '')
                filepath = write_excel(programmes, uni_name, args.output)
                results_summary.append({
                    'university': uni_name,
                    'status': '✅',
                    'file': os.path.basename(filepath),
                    'count': len(programmes),
                })
            else:
                uni_name = name or url.split('/')[2].replace('www.', '')
                results_summary.append({
                    'university': uni_name,
                    'status': '❌',
                    'file': 'Failed',
                    'count': 0,
                })

            time.sleep(1)  # polite delay between universities

        # ── Print final summary
        print(f"\n{'='*60}")
        print(f"📊 FINAL SUMMARY")
        print(f"{'='*60}")
        succeeded = [r for r in results_summary if r['status'] == '✅']
        failed    = [r for r in results_summary if r['status'] == '❌']
        print(f"✅ Succeeded: {len(succeeded)}/{len(results_summary)}")
        print(f"❌ Failed:    {len(failed)}/{len(results_summary)}")
        print()
        for r in results_summary:
            count_str = f"{r['count']} programmes" if r['count'] else "—"
            print(f"  {r['status']} {r['university']:<35} {r['file']:<40} {count_str}")

    # ── Single URL mode
    elif args.url:
        programmes = scrape_university(
            args.url,
            name=args.name,
            country=args.country,
            verbose=args.verbose
        )
        if programmes:
            uni_name = args.name or args.url.split('/')[2].replace('www.', '')
            write_excel(programmes, uni_name, args.output)
        else:
            print("\n❌ No programmes found. Try a more specific URL.")
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
