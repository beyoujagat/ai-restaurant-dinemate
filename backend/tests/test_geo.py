"""
Unit tests for Core Geo Engine Module (Step 2).
Covers Haversine calculation, bounding box validation, coordinate loading,
strict verification gating, broad area exclusion, and radius expansion lookups.

Reference: docs/geo_proximity_plan.md §9, §10.2
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.catalog.geo import (
    BBOX_LAT_MAX,
    BBOX_LAT_MIN,
    BBOX_LNG_MAX,
    BBOX_LNG_MIN,
    clear_geo_cache,
    find_nearby_neighbourhoods,
    find_nearby_neighbourhoods_with_distance,
    haversine_km,
    is_in_bangalore_bbox,
    load_coords,
    load_raw_coords,
)


@pytest.fixture(autouse=True)
def clean_cache_before_each():
    """Ensure LRU cache does not leak state across tests."""
    clear_geo_cache()
    yield
    clear_geo_cache()


# ============================================================================
# Haversine Formula Tests
# ============================================================================

def test_haversine_symmetry_and_zero():
    """Haversine distance between identical points is 0; dist(A, B) == dist(B, A)."""
    lat1, lng1 = 12.9784, 77.6408
    lat2, lng2 = 12.9352, 77.6245

    # Zero distance for identical points
    assert haversine_km(lat1, lng1, lat1, lng1) == 0.0

    # Symmetry
    d_ab = haversine_km(lat1, lng1, lat2, lng2)
    d_ba = haversine_km(lat2, lng2, lat1, lng1)
    assert pytest.approx(d_ab, rel=1e-6) == d_ba
    assert d_ab > 0.0


def test_haversine_known_pair():
    """
    Test Haversine distance against known Bangalore pair:
    Indiranagar (12.9733, 77.6405) <-> Koramangala 5th Block (12.9348, 77.6190) ≈ 4.8 km (±0.5 km).
    """
    coords = load_coords()
    indira = coords["Indiranagar"]
    kora5 = coords["Koramangala 5th Block"]

    dist = haversine_km(indira["lat"], indira["lng"], kora5["lat"], kora5["lng"])
    assert 4.3 <= dist <= 5.3, f"Expected distance ~4.8 km, got {dist:.2f} km"


# ============================================================================
# Bounding Box & Coordinate Validation Tests
# ============================================================================

def test_is_in_bangalore_bbox():
    """Validate bounding box helper boundary conditions."""
    # Within Bangalore
    assert is_in_bangalore_bbox(12.97, 77.59) is True
    assert is_in_bangalore_bbox(BBOX_LAT_MIN, BBOX_LNG_MIN) is True
    assert is_in_bangalore_bbox(BBOX_LAT_MAX, BBOX_LNG_MAX) is True

    # Outside Bangalore (e.g., Delhi, Mumbai, or slightly beyond borders)
    assert is_in_bangalore_bbox(28.6139, 77.2090) is False  # Delhi
    assert is_in_bangalore_bbox(12.6, 77.5) is False       # Lat too low
    assert is_in_bangalore_bbox(13.3, 77.5) is False       # Lat too high
    assert is_in_bangalore_bbox(12.9, 77.3) is False       # Lng too low
    assert is_in_bangalore_bbox(12.9, 78.0) is False       # Lng too high


def test_load_coords_bbox():
    """All entries with coordinates in neighbourhood_coords.json satisfy the Bangalore bounding box."""
    raw = load_raw_coords()
    assert len(raw) >= 90

    for name, data in raw.items():
        lat = data.get("lat")
        lng = data.get("lng")
        if lat is not None and lng is not None:
            assert BBOX_LAT_MIN <= lat <= BBOX_LAT_MAX, (
                f"Neighbourhood {name} lat {lat} outside [{BBOX_LAT_MIN}, {BBOX_LAT_MAX}]"
            )
            assert BBOX_LNG_MIN <= lng <= BBOX_LNG_MAX, (
                f"Neighbourhood {name} lng {lng} outside [{BBOX_LNG_MIN}, {BBOX_LNG_MAX}]"
            )


# ============================================================================
# Gating & Exclusion Tests (Unverified and Broad Areas)
# ============================================================================

def test_unverified_coords_excluded():
    """
    Neighbourhoods with verified: false must be excluded from load_coords()
    and must return [] from find_nearby_neighbourhoods().
    """
    raw = load_raw_coords()
    coords = load_coords()

    # BTM, HSR, Koramangala are currently marked verified: false (Step 1.2)
    unverified_names = [k for k, v in raw.items() if not v.get("verified", False)]
    assert len(unverified_names) > 0

    for name in unverified_names:
        assert name not in coords, f"Unverified location '{name}' should not be in load_coords()"
        assert find_nearby_neighbourhoods(name, 5.0) == [], (
            f"Querying unverified location '{name}' must return empty list"
        )


def test_broad_area_coords_excluded():
    """
    Broad regional areas ('Central Bangalore', 'East Bangalore', 'West Bangalore',
    'North Bangalore', 'South Bangalore') must return [] from find_nearby_neighbourhoods().
    """
    coords = load_coords()
    broad_zones = [
        "Central Bangalore",
        "East Bangalore",
        "West Bangalore",
        "North Bangalore",
        "South Bangalore",
    ]

    for zone in broad_zones:
        assert zone not in coords, f"Broad area '{zone}' must not be present in verified load_coords()"
        nearby = find_nearby_neighbourhoods(zone, radius_km=10.0)
        assert nearby == [], f"Broad area '{zone}' must return [] from find_nearby_neighbourhoods"


def test_missing_or_unknown_location_excluded():
    """Locations not present or missing lat/lng return []."""
    assert find_nearby_neighbourhoods("NonExistentCity123", radius_km=5.0) == []
    assert find_nearby_neighbourhoods("", radius_km=5.0) == []
    assert find_nearby_neighbourhoods("Indiranagar", radius_km=0.0) == []
    assert find_nearby_neighbourhoods("Indiranagar", radius_km=-5.0) == []


# ============================================================================
# Radius Proximity & Expansion Tests
# ============================================================================

def test_find_nearby_5km_vs_10km():
    """
    Proximity check around Indiranagar:
    - Domlur is adjacent (~1.2 km) and must be returned in 5 km.
    - Koramangala 5th Block (~4.87 km) is in 5 km.
    - Whitefield is far (~12.96 km) and must NOT be in 5 km or 10 km.
    - Query location itself ('Indiranagar') is excluded from the results.
    """
    nearby_5km = find_nearby_neighbourhoods("Indiranagar", radius_km=5.0)
    nearby_10km = find_nearby_neighbourhoods("Indiranagar", radius_km=10.0)

    # Indiranagar itself must be excluded
    assert "Indiranagar" not in nearby_5km
    assert "Indiranagar" not in nearby_10km

    # Domlur is within 5 km and 10 km
    assert "Domlur" in nearby_5km
    assert "Domlur" in nearby_10km

    # 10 km is a superset of 5 km
    assert set(nearby_5km).issubset(set(nearby_10km))
    assert len(nearby_10km) > len(nearby_5km)

    # Whitefield is > 10 km away from Indiranagar
    assert "Whitefield" not in nearby_5km
    assert "Whitefield" not in nearby_10km


def test_find_nearby_case_insensitivity():
    """Nearby lookup handles case variations smoothly (e.g. 'indiranagar' vs 'Indiranagar')."""
    res_lower = find_nearby_neighbourhoods("indiranagar", 5.0)
    res_canonical = find_nearby_neighbourhoods("Indiranagar", 5.0)
    res_upper = find_nearby_neighbourhoods("INDIRANAGAR", 5.0)

    assert res_lower == res_canonical
    assert res_upper == res_canonical
    assert len(res_lower) > 0


def test_find_nearby_with_distance_ordering():
    """find_nearby_neighbourhoods_with_distance returns results sorted in strictly ascending distance."""
    detailed = find_nearby_neighbourhoods_with_distance("Indiranagar", radius_km=10.0)
    assert len(detailed) > 0

    distances = [dist for _, dist in detailed]
    assert distances == sorted(distances), "Results must be ordered by ascending distance"
    assert all(0.0 < dist <= 10.0 for dist in distances)


# ============================================================================
# Mock Coordinates File Fixture Tests
# ============================================================================

def test_mock_coords_gating(tmp_path: Path):
    """Test loading and proximity using an isolated custom coordinates file."""
    mock_file = tmp_path / "mock_coords.json"
    mock_data = {
        "__version__": "1.0",
        "ValidA": {"lat": 12.93, "lng": 77.62, "verified": True, "broad_area": False},
        "ValidB": {"lat": 12.94, "lng": 77.63, "verified": True, "broad_area": False},
        "UnverifiedC": {"lat": 12.95, "lng": 77.64, "verified": False, "broad_area": False},
        "BroadD": {"lat": 12.96, "lng": 77.65, "verified": True, "broad_area": True},
        "OutOfBoundsE": {"lat": 15.00, "lng": 77.66, "verified": True, "broad_area": False},
        "MissingCoordsF": {"lat": None, "lng": None, "verified": True, "broad_area": False},
    }
    with open(mock_file, "w", encoding="utf-8") as f:
        json.dump(mock_data, f)

    coords = load_coords(str(mock_file))
    # Only ValidA and ValidB should pass all gating checks
    assert set(coords.keys()) == {"ValidA", "ValidB"}

    # Proximity queries on mock data
    res_a = find_nearby_neighbourhoods("ValidA", radius_km=5.0, coords_path_str=str(mock_file))
    assert res_a == ["ValidB"]

    # Unverified / Broad / Out of bounds return empty list
    assert find_nearby_neighbourhoods("UnverifiedC", radius_km=5.0, coords_path_str=str(mock_file)) == []
    assert find_nearby_neighbourhoods("BroadD", radius_km=5.0, coords_path_str=str(mock_file)) == []
    assert find_nearby_neighbourhoods("OutOfBoundsE", radius_km=5.0, coords_path_str=str(mock_file)) == []


# ============================================================================
# Regression Tests for Corrected Coordinates & Verified Locations
# ============================================================================

def test_corrected_coordinates_proximity():
    """
    Asserts that Vijay Nagar, Sanjay Nagar, and Thippasandra have accurate centroids
    matching real Bangalore geography rather than displaced shop/rural coordinates.
    """
    coords = load_coords()

    # 1. Vijay Nagar is in West Bangalore near Rajajinagar and Basaveshwara Nagar
    vn = coords["Vijay Nagar"]
    raj = coords["Rajajinagar"]
    bn = coords["Basaveshwara Nagar"]
    ec = coords["Electronic City"]
    assert haversine_km(vn["lat"], vn["lng"], raj["lat"], raj["lng"]) < 4.0
    assert haversine_km(vn["lat"], vn["lng"], bn["lat"], bn["lng"]) < 3.0
    assert haversine_km(vn["lat"], vn["lng"], ec["lat"], ec["lng"]) > 15.0

    # 2. Sanjay Nagar is in North Bangalore near New BEL Road and Hebbal
    sn = coords["Sanjay Nagar"]
    nbel = coords["New BEL Road"]
    heb = coords["Hebbal"]
    mar = coords["Marathahalli"]
    assert haversine_km(sn["lat"], sn["lng"], nbel["lat"], nbel["lng"]) < 1.5
    assert haversine_km(sn["lat"], sn["lng"], heb["lat"], heb["lng"]) < 2.5
    assert haversine_km(sn["lat"], sn["lng"], mar["lat"], mar["lng"]) > 10.0

    # 3. Thippasandra is in East Bangalore near Indiranagar and Jeevan Bhima Nagar
    th = coords["Thippasandra"]
    ind = coords["Indiranagar"]
    jbn = coords["Jeevan Bhima Nagar"]
    kp = coords["Kanakapura Road"]
    assert haversine_km(th["lat"], th["lng"], ind["lat"], ind["lng"]) < 1.5
    assert haversine_km(th["lat"], th["lng"], jbn["lat"], jbn["lng"]) < 1.5
    assert haversine_km(th["lat"], th["lng"], kp["lat"], kp["lng"]) > 12.0


def test_verified_target_neighbourhoods():
    """
    Asserts that BTM, HSR, Koramangala, Rammurthy Nagar, Sadashiv Nagar,
    and ITPL Main Road, Whitefield are verified and produce valid nearby results.
    """
    coords = load_coords()
    target_names = [
        "BTM",
        "HSR",
        "Koramangala",
        "Rammurthy Nagar",
        "Sadashiv Nagar",
        "ITPL Main Road, Whitefield",
    ]

    for name in target_names:
        assert name in coords, f"Expected {name} to be in verified coords"
        pt = coords[name]
        assert is_in_bangalore_bbox(pt["lat"], pt["lng"])
        nearby = find_nearby_neighbourhoods(name, radius_km=5.0)
        assert len(nearby) > 0, f"Expected {name} to have neighbours within 5 km"

    # Specific neighbour validations
    btm_nearby = find_nearby_neighbourhoods("BTM", radius_km=5.0)
    assert "Bommanahalli" in btm_nearby or "JP Nagar" in btm_nearby

    hsr_nearby = find_nearby_neighbourhoods("HSR", radius_km=5.0)
    assert "Bellandur" in hsr_nearby or "Koramangala 1st Block" in hsr_nearby

    itpl_nearby = find_nearby_neighbourhoods("ITPL Main Road, Whitefield", radius_km=5.0)
    assert "Whitefield" in itpl_nearby
    assert "Brookefield" in itpl_nearby
