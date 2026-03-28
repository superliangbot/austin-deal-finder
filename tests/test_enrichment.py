"""Tests for the enrichment layer (geocoder, cost estimator)."""

from src.enrichment.geocoder import (
    calculate_distance_from_target,
    estimate_walk_minutes,
    haversine_distance,
)
from src.enrichment.cost_estimator import estimate_total_cost


class TestHaversineDistance:
    """Tests for the haversine distance function."""

    def test_same_point_returns_zero(self):
        assert haversine_distance(30.0, -97.0, 30.0, -97.0) == 0.0

    def test_known_distance_austin_to_dallas(self):
        # Austin (30.2672, -97.7431) to Dallas (32.7767, -96.7970)
        # ~ 182 miles
        d = haversine_distance(30.2672, -97.7431, 32.7767, -96.7970)
        assert 175 < d < 200  # rough check

    def test_short_distance_downtown_austin(self):
        # 600 Congress Ave (30.2672, -97.7431) to a point ~1 mile north
        # 1 degree lat ~ 69 miles, so 0.0145 degrees ~ 1 mile
        d = haversine_distance(30.2672, -97.7431, 30.2817, -97.7431)
        assert 0.9 < d < 1.1

    def test_symmetry(self):
        d1 = haversine_distance(30.0, -97.0, 31.0, -96.0)
        d2 = haversine_distance(31.0, -96.0, 30.0, -97.0)
        assert abs(d1 - d2) < 0.001


class TestEstimateWalkMinutes:
    """Tests for the walking time estimator."""

    def test_zero_distance(self):
        assert estimate_walk_minutes(0.0) == 0

    def test_one_mile(self):
        assert estimate_walk_minutes(1.0) == 20

    def test_half_mile(self):
        assert estimate_walk_minutes(0.5) == 10

    def test_two_miles(self):
        assert estimate_walk_minutes(2.0) == 40


class TestCalculateDistanceFromTarget:
    """Tests for distance from 600 Congress Ave."""

    def test_at_target_is_zero(self):
        d = calculate_distance_from_target(30.2672, -97.7431)
        assert d < 0.01

    def test_nearby_point(self):
        # A point ~0.5 miles north
        d = calculate_distance_from_target(30.2745, -97.7431)
        assert 0.4 < d < 0.6


class TestEstimateTotalCost:
    """Tests for the cost estimator."""

    def test_basic_1br_no_extras(self):
        listing = {"price": 1400, "bedrooms": 1}
        total = estimate_total_cost(listing)
        # 1400 (rent) + 120 (utilities) + 15 (insurance) + 50 (parking) = 1585
        assert total == 1585.0

    def test_studio_with_pets(self):
        listing = {"price": 1100, "bedrooms": 0, "pets_allowed": True}
        total = estimate_total_cost(listing)
        # 1100 + 120 + 15 + 35 (pet rent) + 50 (parking) = 1320
        assert total == 1320.0

    def test_2br_apartment(self):
        listing = {"price": 1800, "bedrooms": 2}
        total = estimate_total_cost(listing)
        # 1800 + 160 + 15 + 50 = 2025
        assert total == 2025.0

    def test_3br_apartment(self):
        listing = {"price": 2000, "bedrooms": 3}
        total = estimate_total_cost(listing)
        # 2000 + 200 + 15 + 50 = 2265
        assert total == 2265.0

    def test_parking_included(self):
        listing = {
            "price": 1400,
            "bedrooms": 1,
            "title": "Nice 1BR with parking included",
        }
        total = estimate_total_cost(listing)
        # 1400 + 120 + 15 + 0 (parking included) = 1535
        assert total == 1535.0

    def test_pet_mention_in_title(self):
        listing = {
            "price": 1400,
            "bedrooms": 1,
            "title": "Pet friendly apartment downtown",
        }
        total = estimate_total_cost(listing)
        # 1400 + 120 + 15 + 35 (pet) + 50 (parking) = 1620
        assert total == 1620.0

    def test_no_price_returns_zero(self):
        assert estimate_total_cost({}) == 0.0
        assert estimate_total_cost({"price": None}) == 0.0

    def test_unknown_bedrooms_defaults_to_1br(self):
        listing = {"price": 1400}
        total = estimate_total_cost(listing)
        # 1400 + 120 (1BR default) + 15 + 50 = 1585
        assert total == 1585.0
