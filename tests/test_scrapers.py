"""Tests for scraper parsing logic using fixture data."""

from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper
from src.scrapers.manual import ManualInput
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
