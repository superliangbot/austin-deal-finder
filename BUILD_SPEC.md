# Austin Deal Finder — Build Specification

## Overview
Production-ready housing deal-finding engine for downtown Austin. Scrapes multiple sources, normalizes listings, scores deals with LLM intelligence, stores in Postgres, and sends notifications via Telegram.

## Target Location
- **Center point:** 600 Congress Avenue, Austin, TX 78701
- **Coordinates:** 30.2672° N, 97.7431° W
- **Radius:** ~30 min walk (~1.5 miles / 2.4 km)

## Budget
- Under $2,000/month ALL-IN (rent + utilities + fees)
- Types: apartments, subleases, roommate situations, lease takeovers

---

## Tech Stack
- **Language:** Python 3.12
- **Scraping:** httpx + BeautifulSoup4 (primary), Playwright (fallback for JS-heavy sites)
- **Database:** PostgreSQL (port 5433, already running on this machine)
- **Queue:** Redis + BullMQ-style (or Python equivalent like `rq` or `apscheduler`)
- **LLM:** OpenAI API (gpt-4o-mini for classification, gpt-4o for enrichment) — key available via `OPENAI_API_KEY` env var
- **Notifications:** Telegram Bot API (we'll add config for this)
- **Geocoding:** OpenStreetMap Nominatim (free) or haversine distance calc
- **Web framework:** FastAPI (for optional dashboard API)
- **Scheduler:** APScheduler for periodic runs

---

## Data Sources (in priority order)

### 1. Reddit (PRAW - Python Reddit API Wrapper)
- **Subreddits:** r/AustinHousing, r/Austin, r/UTAustin
- **Method:** PRAW library (official API, free tier: 100 requests/min)
- **Search terms:** sublease, apartment, housing, roommate, lease takeover, rent
- **Note:** User needs to create Reddit app at reddit.com/prefs/apps (script type)
- Config: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`

### 2. Craigslist Austin
- **URL pattern:** `https://austin.craigslist.org/search/apa` (apartments)
- Also: `https://austin.craigslist.org/search/roo` (rooms/shared)
- Also: `https://austin.craigslist.org/search/sub` (sublets/temporary)
- **Method:** httpx + BeautifulSoup (Craigslist is mostly static HTML)
- **Filters:** max_price=2000, near downtown, posted today/this week
- **Anti-blocking:** Rotate User-Agent, 2-5 second delays between requests

### 3. Apartments.com
- **URL:** `https://www.apartments.com/austin-tx/under-2000/`
- **Method:** httpx with proper headers (renders server-side mostly)
- **Parse:** listing cards with price, beds, address, link
- **Fallback:** Playwright if JS-rendered content is needed

### 4. Zillow Rentals
- **URL:** `https://www.zillow.com/austin-tx/rentals/`
- **Method:** Look for `__NEXT_DATA__` JSON blob in page source (Zillow embeds listing data in script tags)
- **Filters:** max price 2000, apartment type
- **Anti-blocking:** This one is aggressive — use proper headers, consider Playwright

### 5. Facebook Groups (MANUAL/SEMI-AUTO)
- **Reality check:** Facebook aggressively blocks scraping. Mark this as "manual input" source.
- **Implementation:** Create a simple form/endpoint where Logan can paste Facebook listings manually
- **Groups to monitor:** Austin Housing, Austin Subleases, UT Austin Housing Exchange
- **Future:** Could use Facebook Graph API if Logan has a developer app

### 6. HotPads
- **URL:** `https://hotpads.com/austin-tx/apartments-for-rent`
- **Method:** Similar to Zillow — look for embedded JSON data

---

## Project Structure

```
austin-deal-finder/
├── README.md
├── pyproject.toml              # Python project config
├── requirements.txt
├── .env.example                # Template for secrets
├── alembic/                    # DB migrations
│   └── versions/
├── src/
│   ├── __init__.py
│   ├── config.py               # Settings from env vars
│   ├── database/
│   │   ├── __init__.py
│   │   ├── models.py           # SQLAlchemy models
│   │   ├── connection.py       # DB connection setup
│   │   └── crud.py             # Create/Read/Update operations
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── base.py             # Abstract base scraper
│   │   ├── reddit.py           # PRAW-based Reddit scraper
│   │   ├── craigslist.py       # Craigslist scraper
│   │   ├── apartments_com.py   # Apartments.com scraper
│   │   ├── zillow.py           # Zillow scraper
│   │   ├── hotpads.py          # HotPads scraper
│   │   └── manual.py           # Manual input handler (Facebook, etc.)
│   ├── enrichment/
│   │   ├── __init__.py
│   │   ├── geocoder.py         # Distance calculation to 600 Congress
│   │   ├── llm_enricher.py     # LLM-based listing analysis
│   │   └── cost_estimator.py   # Estimate total monthly cost
│   ├── scoring/
│   │   ├── __init__.py
│   │   └── deal_scorer.py      # Deal scoring engine (0-100)
│   ├── notifications/
│   │   ├── __init__.py
│   │   └── telegram.py         # Telegram alert sender
│   ├── api/
│   │   ├── __init__.py
│   │   └── app.py              # FastAPI dashboard API
│   └── cli.py                  # CLI entry point
├── scripts/
│   ├── run_scrape.py           # One-shot scrape all sources
│   ├── run_scorer.py           # Score all unscored listings
│   └── setup_db.py             # Initialize database
├── templates/
│   └── dashboard.html          # Simple HTML dashboard
└── tests/
    ├── __init__.py
    ├── test_scrapers.py
    ├── test_scoring.py
    └── test_enrichment.py
```

---

## Database Schema

### listings table
```sql
CREATE TABLE listings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source VARCHAR(50) NOT NULL,          -- reddit, craigslist, apartments_com, zillow, manual
    source_id VARCHAR(255),                -- unique ID from source platform
    source_url TEXT,                        -- direct link to listing
    title TEXT,
    description TEXT,
    price DECIMAL(10,2),                   -- monthly rent
    estimated_total DECIMAL(10,2),         -- rent + utilities estimate
    bedrooms INTEGER,
    bathrooms DECIMAL(3,1),
    sqft INTEGER,
    address TEXT,
    latitude DECIMAL(10,7),
    longitude DECIMAL(10,7),
    distance_miles DECIMAL(5,2),           -- from 600 Congress Ave
    walk_minutes INTEGER,
    listing_type VARCHAR(50),              -- apartment, sublease, roommate, lease_takeover
    furnished BOOLEAN,
    pets_allowed BOOLEAN,
    available_date DATE,
    contact_info TEXT,
    images TEXT[],                          -- array of image URLs
    raw_data JSONB,                        -- full raw scraped data
    
    -- LLM enrichment fields
    summary TEXT,
    urgency_score INTEGER,                 -- 1-10
    negotiability_score INTEGER,           -- 1-10
    incentives TEXT[],                     -- free month, discount, etc.
    deal_classification VARCHAR(20),       -- STEAL, GOOD_DEAL, AVERAGE, OVERPRICED
    outreach_suggestion TEXT,
    
    -- Scoring
    deal_score INTEGER,                    -- 0-100 composite score
    
    -- Meta
    first_seen_at TIMESTAMP DEFAULT NOW(),
    last_seen_at TIMESTAMP DEFAULT NOW(),
    price_history JSONB DEFAULT '[]',
    is_active BOOLEAN DEFAULT TRUE,
    notified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(source, source_id)
);

CREATE INDEX idx_listings_deal_score ON listings(deal_score DESC);
CREATE INDEX idx_listings_source ON listings(source);
CREATE INDEX idx_listings_price ON listings(price);
CREATE INDEX idx_listings_active ON listings(is_active);
```

---

## Deal Scoring Algorithm

```python
def calculate_deal_score(listing) -> int:
    """Score 0-100 based on multiple factors."""
    score = 50  # baseline
    
    # Price factor (biggest weight — 30 points max)
    avg_market = 1600  # average 1br near downtown Austin
    if listing.price:
        price_ratio = listing.price / avg_market
        if price_ratio < 0.7: score += 30      # way under market
        elif price_ratio < 0.85: score += 20   # good deal
        elif price_ratio < 1.0: score += 10    # slightly under
        elif price_ratio > 1.2: score -= 15    # overpriced
    
    # Distance factor (20 points max)
    if listing.distance_miles:
        if listing.distance_miles < 0.5: score += 20
        elif listing.distance_miles < 1.0: score += 15
        elif listing.distance_miles < 1.5: score += 10
        elif listing.distance_miles < 2.0: score += 5
        else: score -= 10
    
    # Urgency factor (10 points max)
    if listing.urgency_score:
        score += min(listing.urgency_score, 10)
    
    # Incentives (10 points max)
    if listing.incentives:
        score += min(len(listing.incentives) * 5, 10)
    
    # Freshness (10 points max)
    age_hours = (now - listing.first_seen_at).total_seconds() / 3600
    if age_hours < 2: score += 10
    elif age_hours < 12: score += 7
    elif age_hours < 24: score += 4
    
    # Furnished bonus
    if listing.furnished: score += 5
    
    return max(0, min(100, score))
```

### Classification:
- 80-100: "STEAL" 🔥
- 65-79: "GOOD DEAL" ✅
- 40-64: "AVERAGE" ➡️
- 0-39: "OVERPRICED" ❌

---

## Notification Format (Telegram)

```
🔥 STEAL ALERT — Deal Score: 92/100

📍 Downtown Austin Studio — $1,100/mo
🏠 Studio | 450 sqft | Furnished
📏 0.3 miles from Congress Ave (6 min walk)
💰 Est. all-in: $1,250/mo
🏷️ Incentives: First month free, $500 move-in bonus
📅 Available: April 1
⚡ Urgency: HIGH — "Need someone ASAP"

📝 Summary: Furnished studio sublease in the Whitley, 
   tenant relocating for work. Below market by ~$400/mo.

💬 Suggested outreach: "Hey! Super interested in your 
   sublease at the Whitley. I can move in April 1 and 
   sign whatever paperwork needed. When's a good time to see it?"

🔗 [View listing](https://reddit.com/r/AustinHousing/...)
Source: Reddit r/AustinHousing | Posted: 2 hours ago
```

---

## Configuration (.env.example)

```env
# Database
DATABASE_URL=postgresql://openclaw:@localhost:5433/austin_deals

# Reddit API
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=AustinDealFinder/1.0

# OpenAI (for LLM enrichment)
OPENAI_API_KEY=

# Telegram notifications
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Geocoding (optional — defaults to haversine calc)
# GOOGLE_MAPS_API_KEY=

# Scraping
SCRAPE_INTERVAL_HOURS=3
MAX_PRICE=2000
TARGET_LAT=30.2672
TARGET_LON=-97.7431
MAX_DISTANCE_MILES=2.0
```

---

## Implementation Notes

1. **Start with what works reliably:** Reddit (PRAW) and Craigslist (static HTML) are the most reliable. Build and test these first.
2. **Apartments.com and Zillow:** These require more care with anti-bot. Implement with good headers and fallback to Playwright.
3. **Facebook:** Mark as manual-input only. Create an API endpoint where listings can be manually submitted.
4. **LLM enrichment:** Use gpt-4o-mini for classification (cheap, fast). Only use gpt-4o for detailed summaries of high-score deals.
5. **Deduplication:** Use (source + source_id) as unique key. Also implement fuzzy matching on title+price+address for cross-source dedup.
6. **Distance calculation:** Use haversine formula with 600 Congress Ave coords. No external API needed for basic distance. Walk time ≈ distance_miles * 20 minutes.
7. **Price history:** When a listing is re-seen at a different price, append to price_history JSON array.
8. **Anti-blocking:** Random delays (2-8 seconds), rotating user agents, respect robots.txt.
9. **Run as CLI:** `python -m src.cli scrape` / `python -m src.cli score` / `python -m src.cli notify` / `python -m src.cli dashboard`
10. **Tests:** Write real tests for scraper parsing (use saved HTML fixtures), scoring math, and distance calculation.

## Important
- Create a proper venv: `python3 -m venv .venv`
- Use conventional commits
- Write a good README with setup instructions
- Make the first commit with the full project structure
- DO NOT actually run scrapes (we don't have API keys configured yet) — just make sure the code is correct and ready to run
- Include example fixture data for testing
