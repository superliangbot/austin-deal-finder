"""Tests for the deal scoring engine."""

from datetime import datetime, timedelta, timezone

from src.scoring.deal_scorer import calculate_deal_score, classify_deal


class TestCalculateDealScore:
    """Tests for calculate_deal_score()."""

    def test_baseline_score_with_empty_listing(self):
        """Empty listing should get the baseline score of 50."""
        assert calculate_deal_score({}) == 50

    def test_cheap_price_boosts_score(self):
        """A price well below market ($1600) should add up to 30 points."""
        # $1000 / $1600 = 0.625 -> < 0.7 -> +30
        score = calculate_deal_score({"price": 1000})
        assert score == 80  # 50 + 30

    def test_good_price_gives_moderate_boost(self):
        # $1300 / $1600 = 0.8125 -> < 0.85 -> +20
        score = calculate_deal_score({"price": 1300})
        assert score == 70  # 50 + 20

    def test_slightly_under_market(self):
        # $1500 / $1600 = 0.9375 -> < 1.0 -> +10
        score = calculate_deal_score({"price": 1500})
        assert score == 60  # 50 + 10

    def test_overpriced_penalizes(self):
        # $2000 / $1600 = 1.25 -> > 1.2 -> -15
        score = calculate_deal_score({"price": 2000})
        assert score == 35  # 50 - 15

    def test_at_market_price(self):
        # $1600 / $1600 = 1.0 -> between 1.0 and 1.2 -> no change
        score = calculate_deal_score({"price": 1600})
        assert score == 50

    def test_close_distance_boosts(self):
        assert calculate_deal_score({"distance_miles": 0.3}) == 70  # 50 + 20
        assert calculate_deal_score({"distance_miles": 0.8}) == 65  # 50 + 15
        assert calculate_deal_score({"distance_miles": 1.2}) == 60  # 50 + 10
        assert calculate_deal_score({"distance_miles": 1.8}) == 55  # 50 + 5

    def test_far_distance_penalizes(self):
        assert calculate_deal_score({"distance_miles": 5.0}) == 40  # 50 - 10

    def test_urgency_score_adds_points(self):
        assert calculate_deal_score({"urgency_score": 5}) == 55  # 50 + 5
        assert calculate_deal_score({"urgency_score": 10}) == 60  # 50 + 10
        # Capped at 10
        assert calculate_deal_score({"urgency_score": 15}) == 60  # 50 + 10

    def test_incentives_add_points(self):
        assert calculate_deal_score({"incentives": ["free month"]}) == 55  # 50 + 5
        assert calculate_deal_score({"incentives": ["a", "b"]}) == 60  # 50 + 10
        # Capped at 10
        assert calculate_deal_score({"incentives": ["a", "b", "c"]}) == 60  # 50 + 10

    def test_freshness_very_recent(self):
        now = datetime.now(timezone.utc)
        # 30 minutes ago -> < 2 hours -> +10
        score = calculate_deal_score({"first_seen_at": now - timedelta(minutes=30)})
        assert score == 60  # 50 + 10

    def test_freshness_moderate(self):
        now = datetime.now(timezone.utc)
        # 6 hours ago -> < 12 hours -> +7
        score = calculate_deal_score({"first_seen_at": now - timedelta(hours=6)})
        assert score == 57  # 50 + 7

    def test_freshness_same_day(self):
        now = datetime.now(timezone.utc)
        # 18 hours ago -> < 24 hours -> +4
        score = calculate_deal_score({"first_seen_at": now - timedelta(hours=18)})
        assert score == 54  # 50 + 4

    def test_freshness_old_listing(self):
        now = datetime.now(timezone.utc)
        # 48 hours ago -> no bonus
        score = calculate_deal_score({"first_seen_at": now - timedelta(hours=48)})
        assert score == 50

    def test_furnished_bonus(self):
        assert calculate_deal_score({"furnished": True}) == 55  # 50 + 5
        assert calculate_deal_score({"furnished": False}) == 50  # no bonus

    def test_combined_steal_scenario(self):
        """A listing with all positive factors should be a STEAL."""
        now = datetime.now(timezone.utc)
        listing = {
            "price": 1000,         # +30 (way under market)
            "distance_miles": 0.3,  # +20
            "urgency_score": 8,     # +8
            "incentives": ["free month", "bonus"],  # +10
            "first_seen_at": now - timedelta(minutes=30),  # +10
            "furnished": True,      # +5
        }
        score = calculate_deal_score(listing)
        # 50 + 30 + 20 + 8 + 10 + 10 + 5 = 133 -> capped at 100
        assert score == 100

    def test_score_is_clamped_to_0_100(self):
        """Score should never go below 0 or above 100."""
        # Very overpriced and far away
        score = calculate_deal_score({"price": 5000, "distance_miles": 10.0})
        assert 0 <= score <= 100

    def test_string_first_seen_at(self):
        """first_seen_at as ISO string should work."""
        now = datetime.now(timezone.utc)
        score = calculate_deal_score(
            {"first_seen_at": (now - timedelta(minutes=30)).isoformat()}
        )
        assert score == 60  # 50 + 10

    def test_fixture_steal_listing(self):
        """The furnished $1100 studio with incentives should score high."""
        from tests.conftest import FIXTURE_LISTINGS

        listing = FIXTURE_LISTINGS[0]
        score = calculate_deal_score(listing)
        assert score >= 80
        assert classify_deal(score) == "STEAL"

    def test_fixture_overpriced_listing(self):
        """The $2500 luxury 2BR should score low."""
        from tests.conftest import FIXTURE_LISTINGS

        listing = FIXTURE_LISTINGS[2]
        score = calculate_deal_score(listing)
        assert score < 50
        assert classify_deal(score) in ("OVERPRICED", "AVERAGE")


class TestClassifyDeal:
    """Tests for classify_deal()."""

    def test_steal_range(self):
        assert classify_deal(80) == "STEAL"
        assert classify_deal(100) == "STEAL"
        assert classify_deal(90) == "STEAL"

    def test_good_deal_range(self):
        assert classify_deal(65) == "GOOD_DEAL"
        assert classify_deal(79) == "GOOD_DEAL"
        assert classify_deal(70) == "GOOD_DEAL"

    def test_average_range(self):
        assert classify_deal(40) == "AVERAGE"
        assert classify_deal(64) == "AVERAGE"
        assert classify_deal(50) == "AVERAGE"

    def test_overpriced_range(self):
        assert classify_deal(0) == "OVERPRICED"
        assert classify_deal(39) == "OVERPRICED"
        assert classify_deal(20) == "OVERPRICED"
