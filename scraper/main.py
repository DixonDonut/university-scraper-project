# scraper/main.py
# Fully autonomous — paste homepage URL, everything else runs automatically.
# Tries all 9 methods. Never stops to ask.

import sys
import os
import argparse
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper.waterfall import run_waterfall
from scraper.explorer import detect_country
from scraper.fetcher import fetch
from scraper.rules import (
    should_include, get_nmc_flag, get_degree_level,
    infer_degree_level_from_duration,
    format_unclear_degree, normalise_programme_name,
)
from scraper.excel_writer import write_excel


def resolve_programme(prog, verbose=False):
    """Resolve a raw programme entry to final formatted dict(s)."""
    from scraper.parser import parse_programme_detail, is_genuine_programme_page
    from scraper.fetcher import smart_fetch

    name = prog['name']
    url  = prog.get('url', '')
    result, reason = should_include(name)

    if result is True:
        name = normalise_programme_name(name)

        # If still "Bachelor's Degree in X", try catalog widget on the page
        if name.lower().startswith("bachelor's degree in") and url:
            page_content, _ = smart_fetch(url)
            if page_content:
                detail = parse_programme_detail(page_content, url, subject_name=name.split(' in ', 1)[-1])
                if detail and not detail[0]['name'].lower().startswith("bachelor's degree"):
                    for dp in detail:
                        dp['nmc'], dp['nmc_reason'] = get_nmc_flag(dp['name'])
                    return detail

        level      = get_degree_level(name)
        nmc, nmc_r = get_nmc_flag(name)
        return [{
            'name': name, 'level': level, 'url': url,
            'duration': prog.get('duration', ''),
            'fee': prog.get('fee', ''),
            'medium': prog.get('medium', 'English'),
            'nmc': nmc, 'nmc_reason': nmc_r,
        }]

    if result is False:
        return []

    # Unknown — visit the page automatically, no asking
    if url:
        if verbose:
            print(f"     🔍 Looking up: {name}")
        page_content, _ = smart_fetch(url)
        time.sleep(0.3)

        if page_content:
            if not is_genuine_programme_page(page_content):
                return []  # page is a blog post / nav page / 404 — not a real programme

            detail = parse_programme_detail(page_content, url, subject_name=name)
            if detail:
                resolved = []
                for dp in detail:
                    nmc, nmc_r = get_nmc_flag(dp['name'])
                    dp['nmc'] = nmc
                    dp['nmc_reason'] = nmc_r
                    resolved.append(dp)
                return resolved

    # Final fallback — duration-based name
    level = infer_degree_level_from_duration(prog.get('duration', ''))
    formatted = format_unclear_degree(name, level)
    nmc, _ = get_nmc_flag(formatted)
    return [{
        'name': formatted, 'level': level, 'url': url,
        'duration': '', 'fee': '', 'medium': 'English',
        'nmc': 'Yes', 'nmc_reason': 'Unclear degree type',
    }]


def scrape_university(homepage_url, name=None, country=None,
                      verbose=False, output_dir='results'):
    """
    Full autonomous pipeline.
    Paste homepage → runs all methods → saves Excel.
    Never asks permission or stops for input.
    """
    domain = homepage_url.split('/')[2].replace('www.', '')
    university_name = name or domain

    print(f"\n{'='*60}")
    print(f"🏫  {university_name}")
    print(f"🔗  {homepage_url}")
    print(f"{'='*60}")

    # Auto-detect country if not provided
    if not country:
        homepage_content, _ = fetch(homepage_url)
        if homepage_content:
            country = detect_country(homepage_content, homepage_url)
        country = country or 'Unknown'

    print(f"  🌍 Country: {country}")

    # ── Run the full autonomous waterfall
    all_raw, method_used, source_url = run_waterfall(
        homepage_url,
        country=country,
        university_name=university_name,
        verbose=verbose,
    )

    if not all_raw:
        print(f"\n  ❌ Could not scrape {university_name}")
        print(f"  All 9 methods failed. Site may need manual handling.")
        return None

    # Deduplicate
    seen = set()
    unique_raw = []
    for p in all_raw:
        key = p['name'].lower().strip()
        if key not in seen:
            seen.add(key)
            unique_raw.append(p)

    print(f"\n  📦 {len(unique_raw)} unique raw entries")
    print(f"  🔄 Resolving degree types and concentrations...")

    # ── Resolve every entry
    all_final = []
    excluded  = []

    for prog in unique_raw:
        resolved = resolve_programme(prog, verbose)
        for r in resolved:
            result, reason = should_include(r['name'])
            if result is False:
                excluded.append({'name': r['name'], 'reason': reason})
            else:
                all_final.append(r)

    # Final dedup
    seen_f = set()
    deduped = []
    for p in all_final:
        key = p['name'].lower().strip()
        if key not in seen_f:
            seen_f.add(key)
            deduped.append(p)
    all_final = deduped

    # ── Summary
    bachelors  = [p for p in all_final if p['level'] == 'Bachelor']
    associates = [p for p in all_final if p['level'] == 'Associate']
    diplomas   = [p for p in all_final if p['level'] == 'Diploma']
    nmc_yes    = [p for p in all_final if p['nmc'] == 'Yes']

    print(f"\n  📊 Results:")
    print(f"     ✅ Final programmes: {len(all_final)}")
    print(f"     ❌ Excluded:         {len(excluded)}")
    print(f"     Bachelor's:          {len(bachelors)}")
    print(f"     Associate:           {len(associates)}")
    print(f"     Diploma:             {len(diplomas)}")
    print(f"     NMC Yes:             {len(nmc_yes)}")
    print(f"     Method used:         {method_used}")
    print(f"     Source URL:          {source_url}")

    if verbose and excluded:
        print(f"\n  Sample excluded:")
        for e in excluded[:8]:
            print(f"     ❌ {e['name'][:55]:<55} — {e['reason']}")

    if not all_final:
        print(f"\n  ⚠️  No eligible programmes after rules applied.")
        return None

    filepath = write_excel(all_final, university_name, output_dir)
    print(f"\n  🎉 Done → {filepath}")
    return all_final


def main():
    parser = argparse.ArgumentParser(
        description='University Programme Scraper — fully autonomous'
    )
    parser.add_argument('url', help='University homepage URL')
    parser.add_argument('--name', default=None, help='University name (optional)')
    parser.add_argument('--country', default=None,
                        help='Country — auto-detected if not given')
    parser.add_argument('--output', default='results', help='Output folder')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Show detailed output')
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
