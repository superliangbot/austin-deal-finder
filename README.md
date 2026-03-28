# Austin Deal Finder

A production-ready housing deal-finding engine for downtown Austin. Scrapes multiple listing sources, normalizes data into a common schema, enriches listings with geocoding and LLM analysis, scores deals on a 0--100 scale, and delivers real-time Telegram notifications for the best finds.

**Target area:** Within walking distance of 600 Congress Avenue, Austin, TX 78701 (30.2672 N, 97.7431 W).
**Budget ceiling:** Under $2,000/month all-in (rent + utilities + fees).

---

## Quick Start

```bash
# 1. Clone the repository
git clone <repo-url> austin-deal-finder
cd austin-deal-finder

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env and fill in your API keys and secrets

# 5. Create the PostgreSQL database
createdb -p 5433 austin_deals

# 6. Run database migrations
alembic upgrade head

# 7. Verify everything works
pytest tests/ -v

# 8. Run the full pipeline
python -m src.cli run-all
```

---

## Table of Contents

- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Setup Instructions](#setup-instructions)
- [Configuration](#configuration)
- [CLI Commands](#cli-commands)
- [API Endpoints](#api-endpoints)
- [Data Sources](#data-sources)
- [Deal Scoring Algorithm](#deal-scoring-algorithm)
- [Notification Format](#notification-format)
- [Testing](#testing)
- [License](#license)

---

## Tech Stack

| Component        | Technology                                      |
|------------------|-------------------------------------------------|
| Language         | Python 3.12                                     |
| Web Framework    | FastAPI                                         |
| ORM              | SQLAlchemy (async)                              |
| Database         | PostgreSQL                                      |
| Migrations       | Alembic                                         |
| HTTP Client      | httpx                                           |
| HTML Parsing     | BeautifulSoup4                                  |
| Reddit API       | PRAW (Python Reddit API Wrapper)                |
| LLM              | OpenAI (gpt-4o-mini for classification, gpt-4o for enrichment) |
| Scheduling       | APScheduler                                     |
| CLI              | Click                                           |
| JS Fallback      | Playwright (for JS-heavy sites)                 |
| Geocoding        | Haversine formula / OpenStreetMap Nominatim      |
| Notifications    | Telegram Bot API                                |

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
│   └── dashboard.html          # Dark-theme HTML dashboard
└── tests/
    ├── __init__.py
    ├── test_scrapers.py
    ├── test_scoring.py
    └── test_enrichment.py
```

---

## Setup Instructions

### Prerequisites

- Python 3.12+
- PostgreSQL (running on port 5433)
- A Reddit application (create one at [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps), script type)
- An OpenAI API key
- A Telegram bot token and chat ID

### Step-by-step

1. **Clone the repository and enter the project directory:**

   ```bash
   git clone <repo-url> austin-deal-finder
   cd austin-deal-finder
   ```

2. **Create and activate a virtual environment:**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**

   ```bash
   cp .env.example .env
   ```

   Open `.env` in your editor and fill in all required API keys and secrets. See the [Configuration](#configuration) section for details on each variable.

5. **Create the PostgreSQL database:**

   ```bash
   createdb -p 5433 austin_deals
   ```

6. **Run database migrations:**

   ```bash
   alembic upgrade head
   ```

7. **Run the test suite to verify the setup:**

   ```bash
   pytest tests/ -v
   ```

---

## Configuration

All configuration is managed through environment variables. Copy `.env.example` to `.env` and populate the values.

### Required Variables

| Variable                | Description                                      |
|-------------------------|--------------------------------------------------|
| `DATABASE_URL`          | PostgreSQL connection string (e.g., `postgresql://user:pass@localhost:5433/austin_deals`) |
| `REDDIT_CLIENT_ID`      | Reddit application client ID                     |
| `REDDIT_CLIENT_SECRET`  | Reddit application client secret                 |
| `REDDIT_USER_AGENT`     | Reddit API user agent string (e.g., `AustinDealFinder/1.0`) |
| `OPENAI_API_KEY`        | OpenAI API key for LLM enrichment                |
| `TELEGRAM_BOT_TOKEN`    | Telegram Bot API token                           |
| `TELEGRAM_CHAT_ID`      | Telegram chat ID for notifications               |

### Optional / Tuning Variables

| Variable                | Default    | Description                                    |
|-------------------------|------------|------------------------------------------------|
| `SCRAPE_INTERVAL_HOURS` | `3`        | Hours between automated scrape cycles          |
| `MAX_PRICE`             | `2000`     | Maximum monthly rent to consider               |
| `TARGET_LAT`            | `30.2672`  | Latitude of target location (600 Congress Ave) |
| `TARGET_LON`            | `-97.7431` | Longitude of target location                   |
| `MAX_DISTANCE_MILES`    | `2.0`      | Maximum distance from target in miles          |

### Example `.env` file

```env
DATABASE_URL=postgresql://openclaw:@localhost:5433/austin_deals

REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
REDDIT_USER_AGENT=AustinDealFinder/1.0

OPENAI_API_KEY=sk-...

TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_CHAT_ID=your_chat_id

SCRAPE_INTERVAL_HOURS=3
MAX_PRICE=2000
TARGET_LAT=30.2672
TARGET_LON=-97.7431
MAX_DISTANCE_MILES=2.0
```

---

## CLI Commands

All operations are accessible through the CLI module:

| Command                          | Description                                  |
|----------------------------------|----------------------------------------------|
| `python -m src.cli scrape`       | Run all scrapers to collect new listings      |
| `python -m src.cli score`        | Score all unscored listings                   |
| `python -m src.cli enrich`       | Run LLM enrichment on listings                |
| `python -m src.cli notify`       | Send Telegram alerts for high-score deals     |
| `python -m src.cli dashboard`    | Start the FastAPI web dashboard               |
| `python -m src.cli run-all`      | Run the full pipeline (scrape, enrich, score, notify) |

### Examples

Run a single scrape cycle and score the results:

```bash
python -m src.cli scrape
python -m src.cli score
```

Start the dashboard on the default port:

```bash
python -m src.cli dashboard
```

Run the entire pipeline end to end:

```bash
python -m src.cli run-all
```

---

## API Endpoints

The FastAPI dashboard provides the following endpoints:

| Method | Path                    | Description                          |
|--------|-------------------------|--------------------------------------|
| GET    | `/`                     | Serve the dark-theme HTML dashboard  |
| GET    | `/api/listings`         | List listings with filter support    |
| GET    | `/api/listings/{id}`    | Retrieve a single listing by ID      |
| GET    | `/api/stats`            | Dashboard statistics (counts, averages, score distribution) |
| POST   | `/api/listings/manual`  | Submit a listing manually (for Facebook groups, etc.) |

### Query Parameters for `/api/listings`

Listings can be filtered by price range, distance, source, deal classification, and sort order. Consult the API documentation at `/docs` (auto-generated by FastAPI) for the full parameter list.

---

## Data Sources

The engine scrapes and aggregates listings from six sources:

### 1. Reddit (PRAW)

Monitors subreddits **r/AustinHousing**, **r/Austin**, and **r/UTAustin** for posts matching housing-related keywords: sublease, apartment, housing, roommate, lease takeover, rent. Uses the official Reddit API via PRAW (100 requests/min on free tier).

### 2. Craigslist Austin

Scrapes apartment listings (`/search/apa`), rooms and shared housing (`/search/roo`), and sublets (`/search/sub`) from the Austin Craigslist. Filters by maximum price and recency. Uses httpx with BeautifulSoup for parsing static HTML, with randomized delays (2--8 seconds) and rotating user agents for polite scraping.

### 3. Apartments.com

Fetches rental listings from Apartments.com filtered to the Austin area under $2,000/month. Parses listing cards for price, bedroom count, address, and direct links. Falls back to Playwright for JS-rendered content if needed.

### 4. Zillow Rentals

Extracts listing data from Zillow's embedded `__NEXT_DATA__` JSON blobs in the page source. Filters by price and property type. Uses careful header management and optional Playwright fallback to handle Zillow's anti-bot measures.

### 5. HotPads

Scrapes rental listings from HotPads using a similar approach to Zillow -- locating and parsing embedded JSON data within the page source.

### 6. Manual Input (Facebook Groups, etc.)

Since Facebook aggressively blocks automated scraping, listings from Facebook groups (Austin Housing, Austin Subleases, UT Austin Housing Exchange) are submitted manually through the `/api/listings/manual` endpoint. This endpoint accepts structured listing data and feeds it into the same normalization and scoring pipeline as all other sources.

---

## Deal Scoring Algorithm

Each listing receives a composite score from 0 to 100, calculated from multiple weighted factors. The baseline score starts at 50.

### Scoring Factors

**Price Factor (up to 30 points)**

Compares the listing price against an average market rate of $1,600/month for a one-bedroom near downtown Austin.

| Price Ratio vs. Market | Points |
|------------------------|--------|
| Below 70% of market    | +30    |
| 70--85% of market      | +20    |
| 85--100% of market     | +10    |
| Above 120% of market   | -15    |

**Distance Factor (up to 20 points)**

Measures walking distance from 600 Congress Avenue using haversine calculation.

| Distance             | Points |
|----------------------|--------|
| Less than 0.5 miles  | +20    |
| 0.5 -- 1.0 miles     | +15    |
| 1.0 -- 1.5 miles     | +10    |
| 1.5 -- 2.0 miles     | +5     |
| Over 2.0 miles       | -10    |

**Urgency Factor (up to 10 points)**

Derived from the LLM-assigned urgency score (1--10). Added directly to the composite score, capped at 10.

**Incentives (up to 10 points)**

Awards 5 points per incentive (e.g., free month, move-in bonus), capped at 10 points total.

**Freshness (up to 10 points)**

| Listing Age          | Points |
|----------------------|--------|
| Less than 2 hours    | +10    |
| 2 -- 12 hours        | +7     |
| 12 -- 24 hours       | +4     |

**Furnished Bonus**

Furnished listings receive an additional +5 points.

### Deal Classification

| Score Range | Classification |
|-------------|----------------|
| 80 -- 100   | STEAL          |
| 65 -- 79    | GOOD_DEAL      |
| 40 -- 64    | AVERAGE        |
| 0 -- 39     | OVERPRICED     |

---

## Notification Format

When a listing scores high enough, a Telegram message is sent with the following structure:

```
STEAL ALERT -- Deal Score: 92/100

Downtown Austin Studio -- $1,100/mo
Studio | 450 sqft | Furnished
0.3 miles from Congress Ave (6 min walk)
Est. all-in: $1,250/mo
Incentives: First month free, $500 move-in bonus
Available: April 1
Urgency: HIGH -- "Need someone ASAP"

Summary: Furnished studio sublease in the Whitley,
   tenant relocating for work. Below market by ~$400/mo.

Suggested outreach: "Hey! Super interested in your
   sublease at the Whitley. I can move in April 1 and
   sign whatever paperwork needed. When's a good time to see it?"

View listing: https://reddit.com/r/AustinHousing/...
Source: Reddit r/AustinHousing | Posted: 2 hours ago
```

Notifications include a deal summary, an LLM-generated outreach suggestion, and a direct link to the original listing.

---

## Database Schema

Listings are stored in a `listings` table in PostgreSQL with the following key fields:

- **Identity:** `id` (UUID), `source`, `source_id`, `source_url`
- **Listing details:** `title`, `description`, `price`, `estimated_total`, `bedrooms`, `bathrooms`, `sqft`, `address`, `listing_type`, `furnished`, `pets_allowed`, `available_date`
- **Location:** `latitude`, `longitude`, `distance_miles`, `walk_minutes`
- **LLM enrichment:** `summary`, `urgency_score`, `negotiability_score`, `incentives`, `deal_classification`, `outreach_suggestion`
- **Scoring:** `deal_score` (0--100)
- **Tracking:** `first_seen_at`, `last_seen_at`, `price_history` (JSONB), `is_active`, `notified`

Deduplication is enforced by a unique constraint on `(source, source_id)`. Cross-source deduplication uses fuzzy matching on title, price, and address.

---

## Testing

Run the full test suite:

```bash
pytest tests/ -v
```

Tests cover:

- **Scraper parsing** (`test_scrapers.py`) -- validates HTML/JSON parsing against saved fixture data
- **Deal scoring** (`test_scoring.py`) -- verifies scoring math and classification boundaries
- **Enrichment** (`test_enrichment.py`) -- tests geocoding, distance calculations, and cost estimation

---

## License

This project is private and not currently published under an open-source license.
