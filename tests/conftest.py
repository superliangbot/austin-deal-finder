"""Shared fixtures for the test suite."""

from datetime import datetime, timezone


FIXTURE_LISTINGS = [
    {
        "source": "reddit",
        "source_id": "abc123",
        "source_url": "https://reddit.com/r/AustinHousing/comments/abc123",
        "title": "Sublease - Downtown Austin Studio $1,100/mo",
        "description": (
            "Furnished studio at the Whitley, 0.3 miles from Congress Ave. "
            "Tenant relocating for work. Available April 1. First month free. "
            "Need someone ASAP. Pets ok. $500 move-in bonus."
        ),
        "price": 1100.0,
        "bedrooms": 0,
        "bathrooms": 1.0,
        "sqft": 450,
        "address": "1300 S Congress Ave, Austin, TX 78704",
        "listing_type": "sublease",
        "furnished": True,
        "pets_allowed": True,
        "available_date": "2026-04-01",
        "contact_info": "DM on Reddit",
        "images": ["https://i.redd.it/example1.jpg"],
        "raw_data": {"subreddit": "AustinHousing", "author": "test_user"},
        "urgency_score": 8,
        "incentives": ["First month free", "$500 move-in bonus"],
        "first_seen_at": datetime.now(timezone.utc),
    },
    {
        "source": "craigslist",
        "source_id": "7891011",
        "source_url": "https://austin.craigslist.org/apa/d/7891011.html",
        "title": "1BR Downtown Condo - $1,400/mo",
        "description": "Nice 1BR condo downtown. No pets. Parking included.",
        "price": 1400.0,
        "bedrooms": 1,
        "bathrooms": 1.0,
        "sqft": 650,
        "address": "200 Congress Ave, Austin, TX 78701",
        "listing_type": "apartment",
        "furnished": False,
        "pets_allowed": False,
        "available_date": "2026-05-01",
        "contact_info": "reply to ad",
        "images": [],
        "raw_data": {"category": "apa"},
        "first_seen_at": datetime.now(timezone.utc),
    },
    {
        "source": "apartments_com",
        "source_id": "apt-456",
        "source_url": "https://www.apartments.com/austin-tx/apt-456",
        "title": "Luxury 2BR at The Independent",
        "description": "Modern 2BR at The Independent. Amazing views.",
        "price": 2500.0,
        "bedrooms": 2,
        "bathrooms": 2.0,
        "sqft": 1100,
        "address": "100 Congress Ave, Austin, TX 78701",
        "listing_type": "apartment",
        "furnished": False,
        "pets_allowed": True,
        "available_date": "2026-04-15",
        "contact_info": "555-0100",
        "images": ["https://example.com/img1.jpg", "https://example.com/img2.jpg"],
        "raw_data": {},
        "first_seen_at": datetime.now(timezone.utc),
    },
    {
        "source": "manual",
        "source_id": "fb-manual-001",
        "source_url": None,
        "title": "Roommate wanted - East Austin $800/mo",
        "description": (
            "Looking for a roommate in a 3BR house in East Austin. "
            "$800/mo + 1/3 utilities. Furnished room. Dog friendly."
        ),
        "price": 800.0,
        "bedrooms": 1,
        "bathrooms": 1.0,
        "sqft": None,
        "address": "1500 E 6th St, Austin, TX 78702",
        "listing_type": "roommate",
        "furnished": True,
        "pets_allowed": True,
        "available_date": "2026-04-01",
        "contact_info": "512-555-0199",
        "images": [],
        "raw_data": {"input_method": "facebook_paste"},
        "first_seen_at": datetime.now(timezone.utc),
    },
]


FIXTURE_CRAIGSLIST_HTML = """
<html>
<body>
<ul id="search-results">
  <li class="cl-static-search-result">
    <a href="/apa/d/downtown-studio/7654321.html">
      Downtown Studio - Great Location
    </a>
    <div class="priceinfo">$1,200</div>
    <div class="result-hood">(Downtown Austin)</div>
    <div class="housing">1br - 500ft2</div>
  </li>
  <li class="cl-static-search-result">
    <a href="/apa/d/cozy-apartment/7654322.html">
      Cozy 2BR Apartment Near UT
    </a>
    <div class="priceinfo">$1,800</div>
    <div class="result-hood">(West Campus)</div>
    <div class="housing">2br - 850ft2</div>
  </li>
  <li class="cl-static-search-result">
    <a href="/apa/d/overpriced-penthouse/7654323.html">
      Luxury Penthouse
    </a>
    <div class="priceinfo">$5,000</div>
    <div class="result-hood">(Downtown)</div>
    <div class="housing">3br - 2000ft2</div>
  </li>
</ul>
</body>
</html>
"""

FIXTURE_FACEBOOK_PASTE = """Sublease available ASAP - Downtown Austin!

$1,150/mo for a furnished studio at the Rainey St apartments.
1 bed / 1 bath, about 550 sqft.
Pets allowed! Parking included.
Lease runs through December 2026.

Contact: john@example.com or 512-555-0123
Available starting April 1st.

https://facebook.com/groups/austinhousing/posts/12345
"""
