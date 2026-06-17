# scraper/main.py
# Full pipeline with deep crawling, subject-name lookup, concentration expansion

import sys
import os
import argparse
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper.fetcher import smart_fetch, fetch, fetch_nextjs, fetch_embedded_json, fetch_sitemap, discover_api
from scraper.explorer import find_programme_pages
from scraper.parser import parse_programmes, parse_programme_detail, parse_json_programmes
from scraper.rules import (
    should_include, get_nmc_flag, get_degree_level,
    format_programme_name, format_unclear_degree,
    infer_degree_level_from_duration,
)
from scraper.excel_writer import write_excel


def resolve_programme(prog, fetch_fn, verbose=False):
    """
    Resolve a raw programme entry to final programme dict(s).

    If the entry is just a subject name (needs_lookup=True):
      1. Visit the programme page
      2. Find the degree type
      3. Check for concentrations
      4. Return expanded list of programmes

    If the degree type is already known:
      Return immediately with formatting applied.
    """
    name = prog['name']
    url  = prog.get('url', '')

    # ── Already a fully formed degree name
    result, reason = should_include(name)

    if result is True:
        level      = get_degree_level(name)
        nmc, nmc_r = get_nmc_flag(name)
        return [{
            'name':       name,
            'level':      level,
            'url':        url,
            'duration':   prog.get('duration', ''),
            'fee':        prog.get('fee', ''),
            'medium':     prog.get('medium', 'English'),
            'nmc':        nmc,
            'nmc_reason': nmc_r,
        }]

    if result is False:
        return []  # excluded

    # ── Unknown / subject-name only — visit the page
    if not url:
        # No URL — use subject name as fallback
        level = infer_degree_level_from_duration(None)
        formatted = format_unclear_degree(name, level)
        nmc, nmc_r = get_nmc_flag(formatted)
        nmc = 'Yes'  # unclear degree type always NMC
        return [{
            'name': formatted, 'level': level, 'url': '',
            'duration': '', 'fee': '', 'medium': 'English',
            'nmc': nmc, 'nmc_reason': 'Unclear degree type',
        }]

    if verbose:
        print(f"     🔍 Looking up: {name} → {url}")

    page_content, _ = fetch_fn(url)
    time.sleep(0.3)

    if not page_content:
        if verbose:
            print(f"     ⚠️  Could not fetch: {url}")
        # Fallback — list with unclear name
        level = infer_degree_level_from_duration(None)
        formatted = format_unclear_degree(name, level)
        nmc, _ = get_nmc_flag(formatted)
        return [{
            'name': formatted, 'level': level, 'url': url,
            'duration': '', 'fee': '', 'medium': 'English',
            'nmc': 'Yes', 'nmc_reason': 'Could not fetch page',
        }]

    # Parse the detail page
    detail_programmes = parse_programme_detail(page_content, url, subject_name=name)

    if not detail_programmes:
        level = infer_degree_level_from_duration(None)
        formatted = format_unclear_degree(name, level)
        nmc, _ = get_nmc_flag(formatted)
        return [{
            'name': formatted, 'level': level, 'url': url,
            'duration': '', 'fee': '', 'medium': 'English',
            'nmc': 'Yes', 'nmc_reason': 'Degree type not found on page',
        }]

    # Apply NMC flags to detail results
    resolved = []
    for dp in detail_programmes:
        nmc, nmc_r = get_nmc_flag(dp['name'])
        dp['nmc']        = nmc
        dp['nmc_reason'] = nmc_r
        resolved.append(dp)

    return resolved


def scrape_university(homepage_url, name=None, country=None,
                      verbose=False, output_dir='results'):
    """
    Full pipeline from homepage URL to Excel file.
    Handles static, JS-rendered, subject-only, and deep department pages.
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

    # ── Phase 1: Fast API methods
    print("\n  ⚡ Checking for Next.js API...")
    data = fetch_nextjs(homepage_url)
    if data:
        method_used = 'Next.js API'
        all_raw_programmes = parse_json_programmes(data, homepage_url)
        print(f"  ✅ Next.js API: {len(all_raw_programmes)} raw entries")

    if not all_raw_programmes:
        print("  ⚡ Checking for REST API...")
        data = discover_api(homepage_url)
        if data:
            method_used = 'REST API'
            all_raw_programmes = parse_json_programmes(data, homepage_url)
            print(f"  ✅ REST API: {len(all_raw_programmes)} raw entries")

    # ── Phase 2: Homepage exploration + deep crawl
    if not all_raw_programmes:
        print("\n  🔍 Homepage exploration...")
        programme_pages, detected_country_found = find_programme_pages(
            homepage_url,
            fetch_fn=smart_fetch,
            max_candidates=10,
            verbose=verbose,
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
            print(f"  ✅ Sitemap: {len(prog_urls)} URLs")
            for prog_url in prog_urls[:50]:
                page_content, _ = smart_fetch(prog_url)
                if page_content:
                    found = parse_programmes(page_content, prog_url)
                    all_raw_programmes.extend(found)
                time.sleep(0.3)

    # ── Nothing found
    if not all_raw_programmes:
        print(f"\n  ❌ No programme data found automatically.")
        print(f"  💡 Try Claude Code:")
        print(f"\n     claude")
        print(f'     > Scrape {homepage_url} — apply PROJECT_RULES.md')
        print(f'     > Save to results/{domain}-programmes.xlsx')
        return None

    # Deduplicate raw
    seen = set()
    unique_raw = []
    for p in all_raw_programmes:
        key = p['name'].lower().strip()
        if key not in seen:
            seen.add(key)
            unique_raw.append(p)

    print(f"\n  📦 {len(unique_raw)} unique raw entries")

    # ── Phase 4: Resolve each entry
    # This handles subject-name lookup, concentration expansion,
    # degree type detection, duration fallback
    print(f"  🔄 Resolving degree types and concentrations...")

    needs_lookup = [p for p in unique_raw if p.get('needs_lookup')]
    already_known = [p for p in unique_raw if not p.get('needs_lookup')]

    if needs_lookup and verbose:
        print(f"     {len(needs_lookup)} entries need degree type lookup")

    all_final = []
    excluded = []

    # Process known entries
    for prog in already_known:
        resolved = resolve_programme(prog, smart_fetch, verbose)
        for r in resolved:
            result, reason = should_include(r['name'])
            if result is False:
                excluded.append({'name': r['name'], 'reason': reason})
            else:
                all_final.append(r)

    # Process entries needing lookup
    for prog in needs_lookup:
        resolved = resolve_programme(prog, smart_fetch, verbose)
        for r in resolved:
            result, reason = should_include(r['name'])
            if result is False:
                excluded.append({'name': r['name'], 'reason': reason})
            else:
                all_final.append(r)

    # Final dedup by name
    seen_final = set()
    deduped_final = []
    for p in all_final:
        key = p['name'].lower().strip()
        if key not in seen_final:
            seen_final.add(key)
            deduped_final.append(p)
    all_final = deduped_final

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
    print(f"     Country:             {detected_country}")
    print(f"     Method:              {method_used}")

    if verbose and excluded:
        print(f"\n  Sample excluded (first 8):")
        for e in excluded[:8]:
            print(f"     ❌ {e['name'][:55]:<55} — {e['reason']}")

    if not all_final:
        print(f"\n  ⚠️  No eligible programmes after rules applied.")
        return None

    filepath = write_excel(all_final, university_name, output_dir)
    print(f"\n  🎉 Done: {filepath}")
    return all_final


def main():
    parser = argparse.ArgumentParser(
        description='University Programme Scraper'
    )
    parser.add_argument('url', help='University homepage URL')
    parser.add_argument('--name', default=None)
    parser.add_argument('--country', default=None)
    parser.add_argument('--output', default='results')
    parser.add_argument('-v', '--verbose', action='store_true')
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
