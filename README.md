# competitor-discovery

Discovers competitors running Meta (Facebook + Instagram) ads in any niche by scraping the Meta Ad Library via the Apify "Facebook Ad Library Scraper" actor, then ranks advertisers by threat score (longevity + ad count + geographic spread).

Three modes: **seed** (curated niche list), **keyword** (search any term), **page-direct** (scrape specific Page IDs).

## One-time setup

1. **Sign up for Apify** (free): https://console.apify.com/sign-up
   - Free plan gives ~$5/month credit. A full discovery run costs ~$0.05-$0.30, so the free tier covers 15-100 runs/month.
2. **Copy your API token**: https://console.apify.com/account/integrations
3. **Save the token locally**:
   ```bash
   mkdir -p ~/.config/apify
   echo 'YOUR_APIFY_TOKEN_HERE' > ~/.config/apify/token
   chmod 600 ~/.config/apify/token
   ```
4. (Optional) **Verify**:
   ```bash
   curl -s "https://api.apify.com/v2/users/me?token=$(cat ~/.config/apify/token)" | python3 -m json.tool
   ```

## Usage

### Via Claude Code (preferred)

Type any of:
- `/competitor-discovery weight loss US`
- `find me competitors running ads on "AI bootcamp" and "AAA agency"`
- `scan Meta ads for sunglasses brands`

Claude reads `SKILL.md`, picks the right mode, runs the discovery script, then summarizes findings.

### Direct CLI

```bash
# Demo segment, US ads
python3 ~/.claude/skills/competitor-discovery/helpers/discover.py --seed weight-loss-demo --country US

# Custom keywords for any niche
python3 ~/.claude/skills/competitor-discovery/helpers/discover.py \
  --keywords "AI agency course" "AAA accelerator" "Claude Code mastermind" \
  --label ai-coaching

# Page-direct (works in any country — bypasses the keyword-search US-only bug)
python3 ~/.claude/skills/competitor-discovery/helpers/discover.py \
  --pages 102201386497398 --label noom

# Cap ads per keyword (default 200)
python3 ~/.claude/skills/competitor-discovery/helpers/discover.py --seed weight-loss-demo --max-per-keyword 100
```

## What gets created

Output lands in `~/competitor-research/<label>/<YYYY-MM-DD>-<mode>/`:

| File | Purpose |
|---|---|
| `report.md` | Ranked Markdown report (Top Threats / Watch List / Noise) |
| `competitors.json` | All advertisers with scores, ready to import to a CRM |
| `top-10-handoff.json` | Top 10 ranked, consumed by `/funnel-spy` for deep teardowns |
| `raw-ads.json` | Full Apify output (every ad found) |

## Add your own niche segment

Edit `~/.claude/skills/competitor-discovery/config/known-competitors.json`. Copy one of the two demo segments (`weight-loss-demo` or `ai-coaching-demo`), rename to your niche, and replace:

- `seeds[]` — known competitor pages you want to scrape every time
- `search_terms[]` — brand names or hook keywords for discovering NEW competitors
- `deny_domains[]` — landing-page domains to filter out (kills false positives like big SaaS or .edu pages whose ad copy happens to match your keywords)
- `deny_page_names[]` — Page names to filter out

To find a Facebook Page ID: go to `facebook.com/ads/library`, search the brand, open their advertiser profile, and copy the `view_all_page_id` parameter from the URL.

## Threat scoring

| Signal | Weight |
|---|---|
| Run duration (60+ days = 30 pts, 30+ = 20, 14+ = 10) | 30 |
| Ad count (20+ = 25 pts, 5+ = 15, 2+ = 5) | 25 |
| Geographic spread (5+ countries = 20 pts, 2+ = 10, 1+ = 5) | 20 |

Total max: 75.

- **50+** = Top Threat (model this advertiser)
- **25-49** = Watch List
- **<25** = Noise (likely testing or one-off)

## Known limitations

1. **Keyword search is US-only**. The Apify actor returns near-zero results for non-US country keyword queries. For multi-country, use page-direct or seed mode (page-direct expansion works in any country).
2. **Keyword mode = noisy in small niches**. Academic terms in small-TAM B2B niches surface SaaS vendors and unrelated brands. Use seed mode with curated brand-name terms instead.
3. **Keyword mode = great in big niches**. Weight loss, fitness, ecom, dropship — real competitors surface fast.
4. **Long-runner threshold**: 30+ days = scaled, 60+ days = certified winner, 180+ days = hero ad (advertiser is almost certainly profitable on this creative).

## Costs

| Item | Cost |
|---|---|
| Apify ad scrape | ~$0.05-0.30 per run depending on # of ads pulled |
| Free tier covers | ~15-100 runs/month |
| Claude API | $0 (synthesis is just file reading + Markdown rendering) |

## Next step

After this skill finds your top competitors, run `/funnel-spy` on the top 1-2 most interesting advertisers to deconstruct their full marketing funnel (LP → opt-in → call/checkout → upsell).
