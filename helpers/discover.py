#!/usr/bin/env python3
"""
Competitor discovery via Meta Ad Library + Apify.

Three operating modes:

1. **keyword mode** (legacy) - keyword-search the Ad Library directly:
       discover.py --keywords "AI agency" "AI bootcamp" --label ai-coaching
   Best for ecom/dropship/info-product niches with thousands of advertisers.
   Returns lots of noise for small-TAM B2B niches.

2. **seed mode** (v2, RECOMMENDED for small-TAM B2B niches) - curated seed list
   plus brand-name keyword search with domain/page-name validation:
       discover.py --seed weight-loss-demo --country US
   Loads config/known-competitors.json for the chosen segment, page-direct scrapes
   the known seeds, then expands by searching for the configured brand names and
   filtering out deny-listed domains/pages (e.g. big SaaS false positives).

3. **page-direct mode** - bulk page-direct scrape of specific Page IDs:
       discover.py --pages 102201386497398 --label noom
   Use when you know exactly which competitor Pages you want to deconstruct.
   Works in ANY country (no actor keyword-search bug).
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

APIFY_ACTOR = "curious_coder/facebook-ads-library-scraper"
APIFY_API_BASE = "https://api.apify.com/v2"

DEFAULT_OUTPUT_ROOT = Path.home() / "competitor-research"


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def get_apify_token():
    token = os.environ.get("APIFY_TOKEN")
    if token:
        return token.strip()
    token_file = Path.home() / ".config" / "apify" / "token"
    if token_file.exists():
        return token_file.read_text().strip()
    sys.exit(
        "ERROR: Apify token not found.\n"
        "Sign up at https://console.apify.com/sign-up, copy your API token from\n"
        "https://console.apify.com/account/integrations, then:\n"
        "  mkdir -p ~/.config/apify && echo 'YOUR_TOKEN' > ~/.config/apify/token"
    )


def build_keyword_url(keyword, country="US"):
    params = {
        "active_status": "active",
        "ad_type": "all",
        "country": country,
        "q": keyword,
        "search_type": "keyword_unordered",
        "media_type": "all",
    }
    return f"https://www.facebook.com/ads/library/?{urllib.parse.urlencode(params)}"


def build_page_url(page_id):
    """Page-direct: pull all active ads from a specific FB Page. Works in any country."""
    params = {
        "active_status": "active",
        "ad_type": "all",
        "country": "ALL",
        "is_targeted_country": "false",
        "media_type": "all",
        "search_type": "page",
        "view_all_page_id": page_id,
    }
    return f"https://www.facebook.com/ads/library/?{urllib.parse.urlencode(params)}"


def expand_countries(country_arg):
    if not country_arg or country_arg.upper() == "ALL":
        return ["ALL"]
    return [c.strip().upper() for c in country_arg.split(",") if c.strip()]


def http_json(url, method="GET", body=None, timeout=300):
    req = urllib.request.Request(url, method=method)
    if body is not None:
        req.data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def run_apify(token, urls, count_per_url=200, label=""):
    if not urls:
        return []
    actor_path = APIFY_ACTOR.replace("/", "~")
    payload = {"urls": [{"url": u} for u in urls], "scrapeAdDetails": True, "count": count_per_url}
    log(f"Apify {label}: {len(urls)} URLs...")
    start = http_json(f"{APIFY_API_BASE}/acts/{actor_path}/runs?token={token}", "POST", payload)["data"]
    run_id, ds_id = start["id"], start["defaultDatasetId"]
    log(f"  Run: {run_id}")
    started = time.time()
    while True:
        status = http_json(f"{APIFY_API_BASE}/actor-runs/{run_id}?token={token}")["data"]["status"]
        log(f"  [{int(time.time()-started):>4}s] {status}")
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break
        time.sleep(10)
    if status != "SUCCEEDED":
        log(f"  ! Run ended {status}")
        return []
    return http_json(f"{APIFY_API_BASE}/datasets/{ds_id}/items?token={token}&format=json")


def parse_iso(ts):
    if not ts:
        return None
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            try:
                return datetime.fromtimestamp(int(ts), tz=timezone.utc)
            except (ValueError, OSError):
                return None
    return None


def days_active(start, end=None):
    s = parse_iso(start)
    if not s:
        return 0
    e = parse_iso(end) or datetime.now(timezone.utc)
    return max(0, (e - s).days)


def first(*candidates):
    for c in candidates:
        if c not in (None, "", [], {}):
            return c
    return None


def extract_link_domain(ad):
    link = first(
        ad.get("link_url"),
        ad.get("linkUrl"),
        (ad.get("snapshot") or {}).get("link_url"),
        (ad.get("snapshot") or {}).get("linkUrl"),
    )
    if not link:
        return None
    try:
        netloc = urllib.parse.urlparse(link).netloc.lower().replace("www.", "")
        return netloc or None
    except Exception:
        return None


def normalize(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def load_segment(skill_dir, segment_name):
    path = skill_dir / "config" / "known-competitors.json"
    if not path.exists():
        sys.exit(f"ERROR: {path} not found.")
    data = json.loads(path.read_text())
    if segment_name not in data:
        sys.exit(f"ERROR: segment '{segment_name}' not in known-competitors.json. Available: {[k for k in data if not k.startswith('_')]}")
    return data[segment_name]


def discover_pages_from_brand_search(token, search_terms, deny_domains, deny_page_names, country="US"):
    """
    Run brand-name keyword search. For each returned ad:
      - Skip if page_name matches a deny list
      - Skip if landing-page domain matches a deny list
      - Keep page_id otherwise (these are the real candidates)
    Returns dict of page_id -> {"page_name": ..., "match_reasons": [...]}.
    """
    if not search_terms:
        return {}
    urls = [build_keyword_url(term, country) for term in search_terms]
    ads = run_apify(token, urls, count_per_url=200, label="brand-name discovery")
    log(f"  Got {len(ads)} ads from brand-name search")

    deny_doms_norm = {d.lower() for d in (deny_domains or [])}
    deny_names_norm = {normalize(n) for n in (deny_page_names or [])}

    discovered = {}
    for ad in ads:
        pid = ad.get("page_id")
        if not pid:
            continue
        name = ad.get("page_name") or ""
        name_norm = normalize(name)
        dom = extract_link_domain(ad)

        if name_norm in deny_names_norm:
            continue
        if dom and any(dom == d or dom.endswith("." + d) for d in deny_doms_norm):
            continue

        if pid not in discovered:
            discovered[pid] = {"page_name": name, "first_domain": dom, "first_term_match": ad.get("url", "")}
    return discovered


def aggregate_by_advertiser(ads):
    by_page = defaultdict(lambda: {
        "page_name": None, "page_id": None, "page_url": None,
        "ad_count": 0, "max_days_active": 0, "min_days_active": 9999,
        "countries": set(), "link_domains": set(),
        "unique_hooks": [], "first_seen": None,
    })

    for ad in ads:
        page_id = first(ad.get("page_id"), ad.get("pageId"), (ad.get("snapshot") or {}).get("page_id"))
        if not page_id:
            continue
        page_name = first(ad.get("page_name"), ad.get("pageName"), (ad.get("snapshot") or {}).get("page_name"))
        entry = by_page[page_id]
        entry["page_name"] = page_name or entry["page_name"] or f"Page {page_id}"
        entry["page_id"] = page_id
        entry["page_url"] = entry["page_url"] or f"https://www.facebook.com/{page_id}"
        entry["ad_count"] += 1

        start = first(ad.get("start_date"), ad.get("startDate"),
                      ad.get("ad_delivery_start_time"), ad.get("adDeliveryStartTime"),
                      (ad.get("snapshot") or {}).get("creation_time"))
        end = first(ad.get("end_date"), ad.get("endDate"),
                    ad.get("ad_delivery_stop_time"), ad.get("adDeliveryStopTime"))
        d = days_active(start, end)
        if d > entry["max_days_active"]: entry["max_days_active"] = d
        if d < entry["min_days_active"]: entry["min_days_active"] = d

        for c in (ad.get("targeted_or_reached_countries") or []) or []:
            if c: entry["countries"].add(c)

        dom = extract_link_domain(ad)
        if dom: entry["link_domains"].add(dom)

        snap = ad.get("snapshot") or {}
        body = snap.get("body")
        if isinstance(body, dict): body = body.get("text", "")
        body = str(body or "").strip()
        if body and "{{" not in body:
            key = body[:80]
            if not any(h["key"] == key for h in entry["unique_hooks"]):
                arch = first(ad.get("ad_archive_id"), ad.get("adArchiveId"))
                entry["unique_hooks"].append({
                    "key": key, "days": d, "title": snap.get("title", ""),
                    "body": body[:500], "link_url": snap.get("link_url", ""),
                    "archive_id": arch,
                })

    out = []
    for v in by_page.values():
        if v["min_days_active"] == 9999: v["min_days_active"] = 0
        v["countries"] = sorted(v["countries"])
        v["link_domains"] = sorted(v["link_domains"])
        v["unique_hooks"] = sorted(v["unique_hooks"], key=lambda h: -h["days"])
        out.append(v)
    return out


def threat_score(adv):
    score = 0
    d = adv["max_days_active"]
    if d >= 180: score += 40
    elif d >= 60: score += 30
    elif d >= 30: score += 20
    elif d >= 14: score += 10

    n = adv["ad_count"]
    if n >= 100: score += 35
    elif n >= 20: score += 25
    elif n >= 5: score += 15
    elif n >= 2: score += 5

    g = len(adv["countries"])
    if g >= 5: score += 20
    elif g >= 2: score += 10
    elif g >= 1: score += 5

    return score


def render_report(title, advertisers, output_path, context_notes=""):
    advertisers = sorted(advertisers, key=lambda a: -threat_score(a))
    lines = [f"# {title}", "", f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}"]
    if context_notes:
        lines.append("")
        lines.append(context_notes)
    lines.append("")
    lines.append(f"**Total advertisers**: {len(advertisers)}")
    lines.append(f"**Hero candidates (60+ days active)**: {sum(1 for a in advertisers if a['max_days_active'] >= 60)}")
    lines.append(f"**Scaled (30+ days)**: {sum(1 for a in advertisers if a['max_days_active'] >= 30)}")
    lines.append("")

    for adv in advertisers:
        s = threat_score(adv)
        if adv["ad_count"] == 0: continue
        lines.append(f"## {adv['page_name']}  -  Score: {s}")
        lines.append(f"- **Page ID**: {adv['page_id']}")
        lines.append(f"- **Active ads**: {adv['ad_count']}")
        lines.append(f"- **Age range**: {adv['min_days_active']}-{adv['max_days_active']} days")
        lines.append(f"- **Top countries**: {', '.join(adv['countries'][:8]) if adv['countries'] else 'unknown'}")
        lines.append(f"- **Domains**: {', '.join(adv['link_domains'][:8]) if adv['link_domains'] else 'none'}")
        lines.append(f"- **Ad Library**: https://www.facebook.com/ads/library/?active_status=active&search_type=page&view_all_page_id={adv['page_id']}")
        if adv["unique_hooks"]:
            lines.append("")
            lines.append(f"**Top hooks ({len(adv['unique_hooks'])} unique, oldest first):**")
            for h in adv["unique_hooks"][:5]:
                lines.append("")
                lines.append(f"- **{h['days']}d** | Title: \"{h['title']}\"")
                lines.append(f"  - Body: \"{h['body'][:280]}\"")
                if h["link_url"]:
                    lines.append(f"  - LP: {h['link_url']}")
                if h["archive_id"]:
                    lines.append(f"  - Ad: https://www.facebook.com/ads/library/?id={h['archive_id']}")
        lines.append("")
    output_path.write_text("\n".join(lines))


def default_output_dir(label, mode_tag=""):
    """Output goes to ~/competitor-research/<label>/<YYYY-MM-DD>[-<mode>]/. Niche-agnostic."""
    folder = datetime.now().strftime("%Y-%m-%d")
    if mode_tag: folder += f"-{mode_tag}"
    safe_label = re.sub(r"[^a-z0-9_-]+", "-", (label or "scan").lower()).strip("-") or "scan"
    return DEFAULT_OUTPUT_ROOT / safe_label / folder


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--keywords", nargs="+", help="Keyword mode: search the Ad Library for these terms")
    grp.add_argument("--seed", help="Seed mode: load segment from config/known-competitors.json (e.g. 'weight-loss-demo', 'ai-coaching-demo')")
    grp.add_argument("--pages", nargs="+", help="Page-direct mode: scrape these page_ids directly")
    ap.add_argument("--label", help="Label for the output folder (e.g. 'weight-loss'). Defaults to the segment name when using --seed, or 'keyword-scan' / 'pages-scan' otherwise.")
    ap.add_argument("--country", default="US", help="Country code(s) for keyword search. Default: US. Multi: 'US,CA,AU,UK'. All: 'ALL'.")
    ap.add_argument("--max-per-keyword", type=int, default=200)
    ap.add_argument("--output-dir", help="Override output directory")
    args = ap.parse_args()

    skill_dir = Path(__file__).resolve().parent.parent
    token = get_apify_token()

    if args.pages:
        # MODE 3: page-direct
        log(f"Mode: page-direct ({len(args.pages)} pages)")
        urls = [build_page_url(pid) for pid in args.pages]
        ads = run_apify(token, urls, count_per_url=500, label="page-direct")
        label = args.label or "pages-scan"
        output_dir = Path(args.output_dir) if args.output_dir else default_output_dir(label, "pages")
        output_dir.mkdir(parents=True, exist_ok=True)
        advertisers = aggregate_by_advertiser(ads)
        (output_dir / "raw-ads.json").write_text(json.dumps(ads, indent=2, default=str))
        (output_dir / "competitors.json").write_text(json.dumps(advertisers, indent=2, default=str))
        render_report(f"Page-Direct Scrape: {label}", advertisers, output_dir / "report.md",
                      context_notes=f"**Mode**: page-direct\n**Pages scraped**: {', '.join(args.pages)}")
        log(f"\nDONE. Report: {output_dir / 'report.md'}")
        return

    if args.seed:
        # MODE 2: seed (LLM-curated list + brand-name discovery + page-direct scrape)
        seg = load_segment(skill_dir, args.seed)
        log(f"Mode: seed ('{args.seed}')")
        log(f"  Description: {seg.get('description','')}")
        log(f"  Seeds (known competitors): {len(seg.get('seeds',[]))}")
        log(f"  Search terms (for expanding): {len(seg.get('search_terms',[]))}")

        # Collect seed page_ids
        page_ids = {s["page_id"]: s for s in seg.get("seeds", []) if s.get("page_id")}
        log(f"\nKnown seed page_ids: {list(page_ids.keys())}")

        # Discover new page_ids via brand-name search + domain validation
        if seg.get("search_terms"):
            log(f"\nDiscovering new pages via brand-name search...")
            discovered = discover_pages_from_brand_search(
                token,
                seg["search_terms"],
                seg.get("deny_domains", []),
                seg.get("deny_page_names", []),
                country=expand_countries(args.country)[0],
            )
            new_pids = [pid for pid in discovered if pid not in page_ids]
            log(f"  Discovered {len(discovered)} pages ({len(new_pids)} new beyond seeds)")
            for pid, info in discovered.items():
                if pid not in page_ids:
                    log(f"    + {pid}  {info['page_name']}  (domain: {info.get('first_domain')})")
                    page_ids[pid] = {"company": info["page_name"], "domain": info.get("first_domain", "?"),
                                     "founder": "unknown", "page_id": pid, "notes": "discovered via brand-name search"}

        # Page-direct scrape every page_id
        log(f"\nPage-direct scraping {len(page_ids)} pages...")
        page_urls = [build_page_url(pid) for pid in page_ids]
        ads = run_apify(token, page_urls, count_per_url=500, label="page-direct expansion")
        log(f"  Got {len(ads)} ads from page-direct scrape")

        label = args.label or args.seed
        output_dir = Path(args.output_dir) if args.output_dir else default_output_dir(label, "seed")
        output_dir.mkdir(parents=True, exist_ok=True)

        advertisers = aggregate_by_advertiser(ads)

        # Enrich with seed metadata (founder, offer_type, etc.)
        for adv in advertisers:
            meta = page_ids.get(adv["page_id"], {})
            adv["founder"] = meta.get("founder")
            adv["company_known_as"] = meta.get("company")
            adv["offer_type"] = meta.get("offer_type")
            adv["icp"] = meta.get("icp")
            adv["seed_notes"] = meta.get("notes")
            adv["threat_label"] = meta.get("threat", "unranked")

        (output_dir / "raw-ads.json").write_text(json.dumps(ads, indent=2, default=str))
        (output_dir / "competitors.json").write_text(json.dumps(advertisers, indent=2, default=str))

        # Build context block
        ctx_lines = [f"**Mode**: seed ('{args.seed}')",
                     f"**Description**: {seg.get('description','')}",
                     f"**Seed competitors (known)**: {len(seg.get('seeds',[]))}",
                     f"**Search terms (for expanding)**: {', '.join(seg.get('search_terms',[]))}",
                     f"**Deny-listed domains**: {', '.join(seg.get('deny_domains',[]))}"]
        render_report(f"Competitor Intelligence: {args.seed.upper()}", advertisers,
                      output_dir / "report.md", context_notes="\n".join(ctx_lines))

        top = sorted([a for a in advertisers if a["ad_count"] > 0], key=lambda a: -threat_score(a))[:10]
        (output_dir / "top-10-handoff.json").write_text(json.dumps(top, indent=2, default=str))

        log(f"\nDONE. Top advertisers:")
        for a in top[:5]:
            log(f"  [{threat_score(a):>3}] {a['page_name']}  {a['ad_count']} ads, {a['min_days_active']}-{a['max_days_active']}d")
        log(f"\n  Report: {output_dir / 'report.md'}")
        return

    # MODE 1: keyword
    keywords = args.keywords
    label = args.label or "keyword-scan"
    output_dir = Path(args.output_dir) if args.output_dir else default_output_dir(label, "keywords")
    output_dir.mkdir(parents=True, exist_ok=True)
    countries = expand_countries(args.country)
    urls = [build_keyword_url(kw, c) for c in countries for kw in keywords]
    log(f"Mode: keyword ({len(urls)} URLs = {len(keywords)} keywords x {len(countries)} countries)")

    ads = run_apify(token, urls, args.max_per_keyword, label="keyword search")
    log(f"  Got {len(ads)} ads")
    advertisers = aggregate_by_advertiser(ads)
    (output_dir / "raw-ads.json").write_text(json.dumps(ads, indent=2, default=str))
    (output_dir / "competitors.json").write_text(json.dumps(advertisers, indent=2, default=str))
    render_report(f"Keyword Discovery: {label}", advertisers, output_dir / "report.md",
                  context_notes=f"**Mode**: keyword | **Countries**: {args.country} | **Keywords**: {', '.join(keywords)}")
    top = sorted([a for a in advertisers if a["ad_count"] > 0], key=lambda a: -threat_score(a))[:10]
    (output_dir / "top-10-handoff.json").write_text(json.dumps(top, indent=2, default=str))
    log(f"\nDONE. Report: {output_dir / 'report.md'}")


if __name__ == "__main__":
    main()
