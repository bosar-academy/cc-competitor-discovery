---
name: competitor-discovery
description: Discover and analyze competitors running Meta (Facebook/Instagram) ads in any niche. Use when the user says "find competitors", "/competitor-discovery", "scan Meta ads for X", "competitor scan", "find advertisers selling Y", "who runs ads on Z" — for ANY niche (weight loss, fitness, SaaS, coaching, ecom, real estate, etc.). Returns ranked advertisers with creative hooks, longevity, landing-page domains, and Meta Ad Library URLs.
---

# Competitor Discovery (Meta Ad Library)

Discovers and analyzes competitors running paid Meta ads in any niche. Three modes for different use cases.

## How to invoke

When the user asks to find competitors in any market, decide which mode fits:

| User intent | Mode | Example command |
|---|---|---|
| "Find competitors selling weight loss in US" | seed (if segment exists) or keyword | `--seed weight-loss-demo` OR `--keywords "lose weight" "GLP-1" --label weight-loss` |
| "Scan ads for term X" | keyword | `--keywords "term X" --label X` |
| "Analyze these specific Facebook pages" | page-direct | `--pages 102201386497398 --label noom` |
| "Run my saved competitor list for niche X" | seed | `--seed niche-x` |

If the user names a niche that already has a segment in `config/known-competitors.json`, use `--seed`. Otherwise default to **keyword mode with hook-style terms** the niche uses (e.g. for weight loss: "lose weight", "GLP-1", "stubborn belly fat"). Always pass `--label` so the output folder is named clearly.

## Three modes

### 1. Seed mode (best when seeds exist for the niche)

Loads a curated segment from `config/known-competitors.json`, page-direct scrapes the known seeds, AND expands by running brand-name keyword search filtered against deny lists.

```bash
python3 ~/.claude/skills/competitor-discovery/helpers/discover.py --seed weight-loss-demo --country US
```

The segment file defines:
- `seeds[]` - known competitor pages (page_id, founder, domain, offer notes)
- `search_terms[]` - terms to discover NEW competitors (brand names for small niches, hook keywords for big niches)
- `deny_domains[]` - landing-page domains to filter out (filters false positives like GSK careers matching unrelated terms)
- `deny_page_names[]` - Page names to filter out

### 2. Keyword mode (best for big niches, no seed list needed)

Direct keyword search of the Meta Ad Library. Returns pages whose ad copy contains the search terms.

```bash
python3 ~/.claude/skills/competitor-discovery/helpers/discover.py --keywords "lose 30 pounds" "GLP-1" "semaglutide" --label weight-loss --country US
```

**Important caveat**: keyword mode only works reliably for `country=US` (Apify actor has a bug with AU/UK/CA keyword search). For other countries, use page-direct or seed mode.

### 3. Page-direct mode (when you already know the Pages)

Bulk-scrape specific Facebook Page IDs. Works in ANY country (no actor bugs).

```bash
python3 ~/.claude/skills/competitor-discovery/helpers/discover.py --pages 102201386497398 117446295957 --label weight-loss-known
```

## Adding a new niche segment

To create a reusable segment, edit `~/.claude/skills/competitor-discovery/config/known-competitors.json`. Add a top-level key:

```json
{
  "your-niche-name": {
    "description": "What this segment covers and who the ICP is.",
    "seeds": [
      {
        "company": "BrandName",
        "founder": "Founder Name",
        "domain": "brand.com",
        "page_id": "1234567890",
        "offer_type": "course / DFY / app / coaching / SaaS",
        "icp": "who they target",
        "threat": "HIGH / MEDIUM / reference",
        "notes": "important context"
      }
    ],
    "search_terms": ["hook-style or brand-name terms"],
    "deny_domains": ["domains to filter out"],
    "deny_page_names": ["Page names to filter out"]
  }
}
```

To find a Facebook Page ID for the seeds: go to `facebook.com/ads/library`, search the brand, open their advertiser profile, and copy the `view_all_page_id` parameter from the URL.

## Step-by-step workflow when the user invokes the skill

### Step 1 - Identify niche + country
Ask only if unclear:
- What niche? (weight loss, fitness, SaaS, etc.)
- What country? Default US. Multi: `US,CA,AU,UK`. All: `ALL`.

### Step 2 - Choose mode
- If a segment already exists in `known-competitors.json` for this niche → use `--seed <segment>`
- If not, but you can quickly draft 5-10 hook-style search terms → use `--keywords ... --label <niche>`
- If the user provided specific pages → use `--pages ... --label <niche>`

### Step 3 - Run
```bash
python3 ~/.claude/skills/competitor-discovery/helpers/discover.py [mode flag and args]
```

Output goes to `~/competitor-research/<label>/<YYYY-MM-DD>-<mode>/`:
- `report.md` - ranked Markdown report with hooks
- `competitors.json` - structured data
- `top-10-handoff.json` - ready to pipe into `/funnel-spy`
- `raw-ads.json` - full Apify output

### Step 4 - Summarize for user
1. Read `report.md`
2. Highlight pages with 30+ active ads OR 60+ days runtime (real scaled competitors)
3. Flag NEW pages discovered beyond the seed list (unknown competitors)
4. Mention top 3 by threat score with hook samples
5. Suggest next step: `/funnel-spy` on the top 1-2 most interesting advertisers

## Iron rules

- **Never expose the Apify token in chat output.**
- **Always include the output directory path** in your summary so the user can find the report.
- **Filter aggressively**: if the report includes obvious SaaS noise or off-niche pages, update `deny_domains` / `deny_page_names` in the relevant segment (or suggest the user do so) before the next run.
- **Empty Apify credits = check billing**: https://console.apify.com/billing
- **Keyword search is US-only**: the actor returns near-zero results for non-US country keyword queries. For multi-country, use page-direct or seed mode (page-direct expansion works in any country).
- **Pick search terms that match how ads talk, not how academics talk.** "Lose 30 pounds" beats "weight management methodology" for weight loss. "AI audit" beats "AI transformation" for AI services.

## Quick reference

| Operation | Command |
|---|---|
| Find competitors in a saved niche | `discover.py --seed <niche> --country US` |
| Find competitors via hook keywords (any niche) | `discover.py --keywords "term1" "term2" --label <niche>` |
| Scrape known Facebook pages | `discover.py --pages PID1 PID2 --label <niche>` |
| Multi-country (only with seeds or pages) | add `--country US,CA,AU,UK` |
| Add a new niche segment | Edit `~/.claude/skills/competitor-discovery/config/known-competitors.json` |

## Known limitations & key learnings

1. **Keyword mode = noisy in small niches**. If you scan a small-TAM B2B niche with academic terms, you'll get SaaS vendors and unrelated brands mentioning those words in their copy. For small niches, prefer seed mode with curated brand-name terms.

2. **Keyword mode = great in big niches**. Weight loss, fitness, ecom, dropship — high signal density. Real competitors surface fast.

3. **Non-US keyword search is broken** in the current actor. Workaround: use page-direct mode (works in any country) or run keyword search in US then expand to other geos by page-direct.

4. **Long-runner threshold**: 30+ days = scaled, 60+ days = certified winner, 180+ days = hero ad (advertiser is almost certainly profitable on this creative).

5. **Page-direct is the most reliable mode**. If you know the pages, always use this.
