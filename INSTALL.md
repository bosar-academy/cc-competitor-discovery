# Part 1: What You're Getting

A Claude Code skill that scans the Meta Ad Library and surfaces real, scaled competitors in any niche, ranked by how seriously they're spending. Give it a niche - weight loss, AI coaching, sunglasses, real estate, SaaS, whatever - and it returns a list of advertisers, ranked by ad longevity (60+ days = certified winner), ad volume (20+ active = real budget), and geographic spread.

I walk through this skill in the Meta Ads + Claude Code video here: https://youtu.be/_TODO_VIDEO_URL_

Watch the competitor discovery section first so you see what the output looks like. The prompt below installs the same skill on your machine.

## What It Does

You give it any niche. It scrapes the Meta Ad Library via Apify, ranks every advertiser it finds by threat score (longevity + ad count + geo spread), and writes a Markdown report with:

- **Top Threats** - advertisers running 60+ day ads with high volume. Almost certainly profitable. Model these.
- **Watch List** - newer or smaller players to keep an eye on.
- **Noise** - one-off testers, irrelevant matches.

For each advertiser you get: their hook copy samples, their landing page domains, their ad count, run duration, geo coverage, and a direct link to their Meta Ad Library page so you can scroll their creatives.

## Three Modes

**Seed mode** (best for niches you've researched once) - You define a segment in a JSON config with known competitor Page IDs + brand-name search terms + deny lists. Run it any time to get a fresh ranked report.

**Keyword mode** (best for big niches like weight loss, ecom, fitness) - Just give it 5-10 hook terms. No setup. Returns competitors whose ad copy contains those terms.

**Page-direct mode** (when you already know the brands) - Pass Facebook Page IDs directly. Works in any country (no actor bugs).

## What You Need

- **Apify account** (free tier covers 15-100 runs/month) - https://console.apify.com/sign-up
- **Apify API token** - https://console.apify.com/account/integrations
- **Python 3** on your machine (already installed on Mac/Linux)
- **Claude Code** - https://claude.ai/code

## Cost

Apify charges ~$0.05-$0.30 per discovery run. The $5/month free tier covers 15-100 runs.

## Heads Up

- **Keyword search is US-only**. The Apify actor has a bug with AU/UK/CA keyword search. For non-US niches, use page-direct or seed mode (page-direct works in any country).
- The skill ships with 2 demo segments (`weight-loss-demo`, `ai-coaching-demo`) so you can test immediately. Add your own segments in `~/.claude/skills/competitor-discovery/config/known-competitors.json`.

## Next Step

Once this skill finds your top competitors, run `/funnel-spy` on the top 1-2 to deconstruct their full marketing funnel.

---

# Part 2: Copy-Paste This Into Claude Code

```
I want you to install the competitor-discovery Claude Code skill from https://github.com/bosar-academy/cc-competitor-discovery and walk me through setup.

Step 1 - Install the skill:

Run:
  git clone https://github.com/bosar-academy/cc-competitor-discovery ~/.claude/skills/competitor-discovery

Confirm the folder exists at ~/.claude/skills/competitor-discovery/ with SKILL.md inside.

Step 2 - Get my Apify API token:

Tell me to:
  1. Sign up for free at https://console.apify.com/sign-up
  2. Copy my API token from https://console.apify.com/account/integrations
  3. Paste the token back to you.

Once I give you the token, run:
  mkdir -p ~/.config/apify
  echo 'MY_TOKEN_HERE' > ~/.config/apify/token
  chmod 600 ~/.config/apify/token

Verify with:
  curl -s "https://api.apify.com/v2/users/me?token=$(cat ~/.config/apify/token)" | python3 -m json.tool

If it returns a JSON with my username, the token is valid.

Step 3 - Smoke test:

Run a quick test against the demo segment to confirm everything works:

  python3 ~/.claude/skills/competitor-discovery/helpers/discover.py --seed weight-loss-demo --country US --max-per-keyword 50

This should:
- Cost about $0.05 on my Apify account
- Write output to ~/competitor-research/weight-loss-demo/<today>/
- Return a ranked report.md with at least 3 advertisers

Open the report.md for me and confirm it has competitors with threat scores.

Step 4 - Confirm I'm ready:

Tell me the skill is installed and remind me of the trigger phrases:
- "/competitor-discovery weight loss US"
- "find me competitors running ads on 'AI bootcamp'"
- "scan Meta ads for sunglasses brands"

Also tell me how to add my own niche segment:
- Edit ~/.claude/skills/competitor-discovery/config/known-competitors.json
- Copy one of the demo segments, rename to my niche, fill in seeds + search_terms + deny lists
- Find Facebook Page IDs at facebook.com/ads/library (search the brand, open advertiser profile, copy view_all_page_id from the URL)

That's it - the skill is ready.
```
