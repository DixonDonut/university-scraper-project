# scraper/main.py
# Paste any university homepage — scraper finds everything automatically.
#
# Usage:
#   python3 -m scraper.main https://www.manchester.ac.uk
#   python3 -m scraper.main https://www.bits-pilani.ac.in --country India -v

import sys
import os
import argparse
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper.fetcher import fetch, fetch_nextjs, fetch_embedded_json, fetch_sitemap, discover_api
from scraper.explorer import find_programme_pages
from scraper.parser import parse_programmes, parse_json_programmes
from scraper.rules import should_include, get_nmc_flag, get_degree_level
from scraper.excel_writer import write_excel


def scrape_university(homepage_url, name=None, country=None, verbose=False, output_dir='results'):
    """
    Full pipeline from homepage URL to Excel file.
    No universities.txt required.
    """
    domain = homepage_url.split('/')[2].replace('www.', '')
    university_name = name or domain

    print(f"\n{'='*60}")
    print(f"🏫  {university_name}")
    print(f"🔗  {homepage_url}")
    print(f"{'='*60}")

    all_raw_programmes = []
    method_used = None
    detected_country = country

    # ── Phase 1: Try fast API methods first
    print("\n  ⚡ Checking for Next.js API...")
    data = fetch_nextjs(homepage_url)
    if data:
        method_used = 'Next.js API'
        all_raw_programmes = parse_json_programmes(data, homepage_url)
        print(f"  ✅ Next.js API found {len(all_raw_programmes)} raw entries")

    if not all_raw_programmes:
        print("  ⚡ Checking for REST API...")
        data = discover_api(homepage_url)
        if data:
            method_used = 'REST API'
            all_raw_programmes = parse_json_programmes(data, homepage_url)
            print(f"  ✅ REST API found {len(all_raw_programmes)} raw entries")

    # ── Phase 2: Smart homepage exploration
    if not all_raw_programmes:
        print("\n  🔍 Starting homepage exploration...")
        programme_pages, detected_country_found = find_programme_pages(
            homepage_url,
            fetch_fn=fetch,
            max_candidates=8,
            verbose=verbose
        )

        if not detected_country:
            detected_country = detected_country_found or 'Unknown'

        if programme_pages:
            method_used = 'Homepage exploration'
            print(f"\n  📄 Parsing {len(programme_pages)} programme pages...")
            for page_url, page_content in programme_pages:
                found = parse_programmes(page_content, page_url)
                all_raw_programmes.extend(found)
                if verbose:
                    print(f"     {page_url} → {len(found)} raw entries")

    # ── Phase 3: Sitemap fallback
    if not all_raw_programmes:
        print("\n  🗺️  Trying sitemap...")
        prog_urls = fetch_sitemap(homepage_url)
        if prog_urls:
            method_used = 'Sitemap'
            print(f"  ✅ Sitemap found {len(prog_urls)} programme URLs")
            for prog_url in prog_urls[:40]:
                page_content, _ = fetch(prog_url)
                if page_content:
                    found = parse_programmes(page_content, prog_url)
                    all_raw_programmes.extend(found)
                time.sleep(0.3)

    # ── Nothing found
    if not all_raw_programmes:
        print(f"\n  ❌ Could not find programme data automatically.")
        print(f"  💡 This site may be JavaScript-rendered.")
        print(f"  💡 Try using Claude Code instead:\n")
        print(f"     claude")
        print(f'     > Scrape {homepage_url} for all undergraduate programmes')
        print(f'     > Apply PROJECT_RULES.md include/exclude rules')
        print(f'     > Save to results/{domain}-programmes.xlsx')
        return None

    # Deduplicate
    seen = set()
    unique_raw = []
    for p in all_raw_programmes:
        key = p['name'].lower().strip()
        if key not in seen:
            seen.add(key)
            unique_raw.append(p)

    print(f"\n  📦 {len(unique_raw)} unique raw entries before rules")

    # ── Phase 4: Apply include/exclude rules
    included = []
    excluded = []
    unknown  = []

    for prog in unique_raw:
        prog_name = prog['name']
        result, reason = should_include(prog_name)

        if result is True:
            level      = get_degree_level(prog_name)
            nmc, nmc_r = get_nmc_flag(prog_name)
            included.append({
                'name':       prog_name,
                'level':      level,
                'url':        prog.get('url', ''),
                'duration':   prog.get('duration', ''),
                'fee':        prog.get('fee', ''),
                'medium':     prog.get('medium', 'English'),
                'nmc':        nmc,
                'nmc_reason': nmc_r,
            })
        elif result is False:
            excluded.append({'name': prog_name, 'reason': reason})
        else:
            level = get_degree_level(prog_name)
            unknown.append({
                'name':       prog_name,
                'level':      level,
                'url':        prog.get('url', ''),
                'duration':   '',
                'fee':        '',
                'medium':     'English',
                'nmc':        'Yes',
                'nmc_reason': 'Unknown degree type — manual check needed',
            })

    all_final = included + unknown

    # ── Phase 5: Print summary and save Excel
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
    print(f"     Country:       {detected_country}")
    print(f"     Method:        {method_used}")

    if verbose and excluded:
        print(f"\n  Sample excluded (first 8):")
        for e in excluded[:8]:
            print(f"     ❌ {e['name'][:55]:<55} — {e['reason']}")

    if not all_final:
        print(f"\n  ⚠️  No eligible programmes found after applying rules.")
        return None

    filepath = write_excel(all_final, university_name, output_dir)
    print(f"\n  🎉 Done: {filepath}")
    return all_final


def main():
    parser = argparse.ArgumentParser(
        description='University Programme Scraper — paste any homepage URL'
    )
    parser.add_argument(
        'url',
        help='University homepage URL — e.g. https://www.manchester.ac.uk'
    )
    parser.add_argument(
        '--name', default=None,
        help='University name (optional — auto-detected from domain)'
    )
    parser.add_argument(
        '--country', default=None,
        help='Country hint — UK, USA, India, Canada, Australia (optional — auto-detected)'
    )
    parser.add_argument(
        '--output', default='results',
        help='Output folder (default: results)'
    )
    parser.add_argument(
        '-v', '--verbose', action='store_true',
        help='Show detailed output'
    )
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    scrape_university(
        homepage_url=args.url,
        name=args.name,
        country=args.country,
        verbose=args.verbose,
        output_dir=args.output,
    )


if __name__ == "__main__":
    main()
