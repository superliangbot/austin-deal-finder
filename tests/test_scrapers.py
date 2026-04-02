"""Tests for scraper parsing logic using fixture data."""

from unittest.mock import MagicMock, patch

from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper
from src.scrapers.manual import ManualInput
from src.scrapers.reddit import (
    RedditScraper,
    _detect_listing_type,
    _extract_price,
)
from tests.conftest import FIXTURE_CRAIGSLIST_HTML, FIXTURE_FACEBOOK_PASTE


class TestBaseScraper:
    """Tests for the base scraper normalize_listing helper."""

    def test_normalize_listing_all_fields(self):
        result = BaseScraper.normalize_listing(
            source="test",
            source_id="test-123",
            source_url="https://example.com",
            title="Test Listing",
            description="A test listing",
            price=1500.0,
            bedrooms=1,
            bathrooms=1.0,
            sqft=650,
            address="123 Main St",
            listing_type="apartment",
            furnished=True,
            pets_allowed=False,
        )
        assert result["source"] == "test"
        assert result["source_id"] == "test-123"
        assert result["title"] == "Test Listing"
        assert result["price"] == 1500.0
        assert result["bedrooms"] == 1
        assert result["furnished"] is True
        assert result["images"] == []
        assert result["raw_data"] == {}

    def test_normalize_listing_minimal(self):
        result = BaseScraper.normalize_listing(source="test")
        assert result["source"] == "test"
        assert result["title"] is None
        assert result["price"] is None
        assert result["images"] == []

    def test_normalize_listing_with_images(self):
        images = ["https://example.com/1.jpg", "https://example.com/2.jpg"]
        result = BaseScraper.normalize_listing(
            source="test", images=images
        )
        assert result["images"] == images


class TestCraigslistParsing:
    """Test Craigslist HTML parsing logic."""

    def test_parse_craigslist_listings_count(self):
        """Fixture HTML should contain 3 listing rows."""
        soup = BeautifulSoup(FIXTURE_CRAIGSLIST_HTML, "html.parser")
        rows = soup.select("li.cl-static-search-result")
        assert len(rows) == 3

    def test_parse_craigslist_title(self):
        soup = BeautifulSoup(FIXTURE_CRAIGSLIST_HTML, "html.parser")
        rows = soup.select("li.cl-static-search-result")
        link = rows[0].select_one("a")
        assert link is not None
        title = link.get_text(strip=True)
        assert "Downtown Studio" in title

    def test_parse_craigslist_price(self):
        import re
        soup = BeautifulSoup(FIXTURE_CRAIGSLIST_HTML, "html.parser")
        rows = soup.select("li.cl-static-search-result")
        price_el = rows[0].select_one(".priceinfo")
        assert price_el is not None
        price_text = price_el.get_text(strip=True)
        match = re.search(r"\$([\d,]+)", price_text)
        assert match is not None
        price = float(match.group(1).replace(",", ""))
        assert price == 1200.0

    def test_parse_craigslist_housing_details(self):
        import re
        soup = BeautifulSoup(FIXTURE_CRAIGSLIST_HTML, "html.parser")
        rows = soup.select("li.cl-static-search-result")
        housing = rows[0].select_one(".housing")
        assert housing is not None
        text = housing.get_text(strip=True)
        br_match = re.search(r"(\d+)br", text)
        assert br_match is not None
        assert int(br_match.group(1)) == 1
        sqft_match = re.search(r"(\d+)ft", text)
        assert sqft_match is not None
        assert int(sqft_match.group(1)) == 500

    def test_parse_craigslist_source_id_from_url(self):
        import re
        soup = BeautifulSoup(FIXTURE_CRAIGSLIST_HTML, "html.parser")
        rows = soup.select("li.cl-static-search-result")
        link = rows[0].select_one("a")
        href = link.get("href", "")
        match = re.search(r"/(\d+)\.html", href)
        assert match is not None
        assert match.group(1) == "7654321"

    def test_overpriced_listing_in_fixture(self):
        """The $5000 listing should be identifiable as expensive."""
        import re
        soup = BeautifulSoup(FIXTURE_CRAIGSLIST_HTML, "html.parser")
        rows = soup.select("li.cl-static-search-result")
        price_el = rows[2].select_one(".priceinfo")
        price_text = price_el.get_text(strip=True)
        match = re.search(r"\$([\d,]+)", price_text)
        price = float(match.group(1).replace(",", ""))
        assert price == 5000.0
        assert price > 2000  # over budget


class TestManualInput:
    """Tests for the manual input handler."""

    def test_add_listing_basic(self):
        handler = ManualInput()
        result = handler.add_listing({
            "title": "Test Studio",
            "price": 1200,
            "description": "A nice studio downtown",
        })
        assert result["source"] == "manual"
        assert result["title"] == "Test Studio"
        assert result["price"] == 1200.0
        assert result["source_id"] is not None

    def test_add_listing_missing_title_raises(self):
        handler = ManualInput()
        try:
            handler.add_listing({"price": 1200})
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "title" in str(e).lower()

    def test_add_listing_missing_price_and_description_raises(self):
        handler = ManualInput()
        try:
            handler.add_listing({"title": "Test", "source_url": "https://example.com"})
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "price" in str(e).lower() or "description" in str(e).lower()

    def test_from_facebook_paste(self):
        handler = ManualInput()
        result = handler.from_facebook_paste(FIXTURE_FACEBOOK_PASTE)

        assert result["source"] == "manual"
        assert result["source_id"] is not None
        assert result["price"] == 1150.0
        assert result["listing_type"] == "sublease"
        assert result["furnished"] is True
        assert result["pets_allowed"] is True
        assert result["contact_info"] is not None
        assert "john@example.com" in result["contact_info"]
        assert result["source_url"] is not None
        assert "facebook.com" in result["source_url"]

    def test_from_facebook_paste_extracts_beds(self):
        handler = ManualInput()
        result = handler.from_facebook_paste(FIXTURE_FACEBOOK_PASTE)
        assert result["bedrooms"] == 1

    def test_from_facebook_paste_extracts_sqft(self):
        handler = ManualInput()
        result = handler.from_facebook_paste(FIXTURE_FACEBOOK_PASTE)
        assert result["sqft"] == 550

    def test_from_facebook_paste_empty_raises(self):
        handler = ManualInput()
        try:
            handler.from_facebook_paste("")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_deterministic_source_id(self):
        """Same content should produce the same source_id."""
        handler = ManualInput()
        r1 = handler.from_facebook_paste(FIXTURE_FACEBOOK_PASTE)
        r2 = handler.from_facebook_paste(FIXTURE_FACEBOOK_PASTE)
        assert r1["source_id"] == r2["source_id"]


class TestRedditPriceExtraction:
    """Tests for Reddit price extraction helper."""

    def test_extract_price_basic(self):
        assert _extract_price("$1200") == 1200.0

    def test_extract_price_with_comma(self):
        assert _extract_price("$1,200") == 1200.0

    def test_extract_price_with_mo_suffix(self):
        assert _extract_price("$1,200/mo") == 1200.0

    def test_extract_price_none_for_empty(self):
        assert _extract_price("") is None

    def test_extract_price_none_for_no_match(self):
        assert _extract_price("no price here") is None

    def test_extract_price_from_sentence(self):
        assert _extract_price("Nice studio for $950/mo downtown") == 950.0


class TestRedditListingTypeDetection:
    """Tests for Reddit listing type detection."""

    def test_detect_sublease(self):
        assert _detect_listing_type("Sublease available ASAP") == "sublease"

    def test_detect_sublet(self):
        assert _detect_listing_type("Looking for a sublet") == "sublease"

    def test_detect_lease_takeover(self):
        assert _detect_listing_type("Lease takeover at the Vue") == "lease_takeover"

    def test_detect_roommate(self):
        assert _detect_listing_type("Roommate wanted in East Austin") == "roommate"

    def test_detect_apartment(self):
        assert _detect_listing_type("Studio apartment near UT") == "apartment"

    def test_detect_none(self):
        assert _detect_listing_type("This is a random post about Austin") is None


class TestRedditScraperParsing:
    """Tests for Reddit JSON post parsing."""

    def _make_post_data(self, **overrides):
        """Create a sample Reddit post JSON structure."""
        post = {
            "id": "abc123",
            "title": "Sublease - Downtown Austin Studio $1,100/mo",
            "selftext": "Furnished studio near Congress Ave. Available April 1.",
            "author": "test_user",
            "created_utc": 1711900000,
            "score": 5,
            "upvote_ratio": 0.9,
            "num_comments": 3,
            "permalink": "/r/AustinHousing/comments/abc123/sublease_downtown/",
            "url": "https://www.reddit.com/r/AustinHousing/comments/abc123/sublease_downtown/",
            "link_flair_text": "Housing",
        }
        post.update(overrides)
        return post

    def test_parse_post_returns_normalized_listing(self):
        scraper = RedditScraper()
        post = self._make_post_data()
        result = scraper._parse_post(post, "AustinHousing")
        assert result is not None
        assert result["source"] == "reddit"
        assert result["source_id"] == "abc123"
        assert result["title"] == "Sublease - Downtown Austin Studio $1,100/mo"
        assert result["price"] == 1100.0
        assert result["listing_type"] == "sublease"
        assert result["contact_info"] == "u/test_user"
        assert "reddit.com" in result["source_url"]
        scraper.close()

    def test_parse_post_extracts_price_from_body(self):
        scraper = RedditScraper()
        post = self._make_post_data(
            title="Room available downtown",
            selftext="Nice room for $900/mo, utilities included.",
        )
        result = scraper._parse_post(post, "Austin")
        assert result is not None
        assert result["price"] == 900.0
        scraper.close()

    def test_parse_post_filters_irrelevant(self):
        scraper = RedditScraper()
        post = self._make_post_data(
            title="Best tacos in Austin?",
            selftext="Where can I get great tacos downtown?",
        )
        result = scraper._parse_post(post, "Austin")
        assert result is None
        scraper.close()

    def test_parse_post_keeps_post_with_price_only(self):
        scraper = RedditScraper()
        post = self._make_post_data(
            title="$1,500 downtown",
            selftext="",
        )
        result = scraper._parse_post(post, "Austin")
        assert result is not None
        assert result["price"] == 1500.0
        scraper.close()

    def test_parse_post_image_extraction(self):
        scraper = RedditScraper()
        post = self._make_post_data(
            url="https://i.redd.it/example.jpg",
        )
        result = scraper._parse_post(post, "AustinHousing")
        assert result is not None
        assert "https://i.redd.it/example.jpg" in result["images"]
        scraper.close()

    def test_parse_post_no_author(self):
        scraper = RedditScraper()
        post = self._make_post_data(author=None)
        result = scraper._parse_post(post, "AustinHousing")
        assert result is not None
        assert result["contact_info"] is None
        scraper.close()

    @patch("src.scrapers.reddit.time.sleep")
    def test_scrape_calls_endpoints(self, mock_sleep):
        """Test that scrape() makes HTTP requests and deduplicates."""
        scraper = RedditScraper()
        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "data": {
                "children": [
                    {"data": self._make_post_data()},
                    {"data": self._make_post_data(id="def456", title="Apartment near UT $1,400")},
                ]
            }
        }
        fake_response.raise_for_status = MagicMock()

        with patch.object(scraper.http, "get", return_value=fake_response):
            listings = scraper.scrape()

        # Should deduplicate across subreddits and search terms
        assert len(listings) == 2
        ids = {l["source_id"] for l in listings}
        assert "abc123" in ids
        assert "def456" in ids
        scraper.close()
