"""Phase 5 API tests.

Covered cases (from spec):
  1. /health works without LLM_API_KEY.
  2. 422 on bad budget.
  3. 200 with empty recommendations when nothing matches.
  4. 200 with up to 5 items, each with required fields.
  5. GET /api/meta/options returns all expected keys.
"""
from __future__ import annotations
import sqlite3
import json
import pytest
from fastapi.testclient import TestClient


def _build_fixture_db(path: str) -> None:
    from tests.fixtures.sample_catalog import FIXTURE_RESTAURANTS
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE IF NOT EXISTS restaurants (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, address TEXT DEFAULT '',
        neighborhood TEXT DEFAULT '', listed_city TEXT DEFAULT '',
        cuisines TEXT DEFAULT '[]', cuisines_raw TEXT DEFAULT '',
        cost_for_two INTEGER, rating REAL, votes INTEGER DEFAULT 0,
        rest_types TEXT DEFAULT '[]', listed_types TEXT DEFAULT '[]',
        online_order INTEGER DEFAULT 0, book_table INTEGER DEFAULT 0,
        dishes_liked TEXT DEFAULT '[]', review_snippets TEXT DEFAULT '[]',
        url TEXT)""")
    for r in FIXTURE_RESTAURANTS:
        conn.execute(
            "INSERT OR REPLACE INTO restaurants VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (r.id, r.name, r.address, r.neighborhood, r.listed_city,
             json.dumps(r.cuisines), r.cuisines_raw, r.cost_for_two, r.rating,
             r.votes, json.dumps(r.rest_types), json.dumps(r.listed_types),
             int(r.online_order), int(r.book_table), json.dumps(r.dishes_liked),
             json.dumps(r.review_snippets), r.url))
    conn.execute("CREATE TABLE IF NOT EXISTS locations (neighborhood TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS cuisines (cuisine TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS restaurant_cuisine (id TEXT, cuisine TEXT)")
    # Populate cuisine junction from fixtures
    seen = set()
    for r in FIXTURE_RESTAURANTS:
        for c in r.cuisines:
            c = c.strip()
            if c and c not in seen:
                seen.add(c)
                conn.execute("INSERT INTO restaurant_cuisine VALUES (?, ?)", (r.id, c))
    conn.commit(); conn.close()


@pytest.fixture(scope="module")
def fixture_db_path(tmp_path_factory):
    p = tmp_path_factory.mktemp("catalog") / "restaurants.sqlite"
    _build_fixture_db(str(p))
    return str(p)


@pytest.fixture()
def client(fixture_db_path, monkeypatch):
    monkeypatch.setenv("CATALOG_DB_PATH", fixture_db_path)
    import app.api.routes as routes_module
    monkeypatch.setattr(routes_module, "_store", None)
    import app.llm.client as llm_module
    monkeypatch.setattr(llm_module, "_get_client", lambda: None)
    from app.main import app
    return TestClient(app)


class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_health_without_llm_key(self, fixture_db_path, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.setenv("CATALOG_DB_PATH", fixture_db_path)
        import app.api.routes as r; monkeypatch.setattr(r, "_store", None)
        from app.main import app; c = TestClient(app)
        assert c.get("/health").status_code == 200


class TestMetaOptions:
    def test_meta_options_keys_present(self, client):
        resp = client.get("/api/meta/options")
        assert resp.status_code == 200
        data = resp.json()
        for key in ("locations", "cuisines", "budget_labels", "rating_choices"):
            assert key in data

    def test_budget_labels_bands(self, client):
        labels = client.get("/api/meta/options").json()["budget_labels"]
        assert set(labels.keys()) == {"low", "medium", "high"}

    def test_rating_choices_numeric(self, client):
        choices = client.get("/api/meta/options").json()["rating_choices"]
        assert all(isinstance(r, (int, float)) for r in choices)


class TestMetaNearby:
    def test_nearby_returns_5km_and_10km_lists(self, client):
        resp = client.get("/api/meta/nearby?location=Indiranagar")
        assert resp.status_code == 200
        data = resp.json()
        assert data["location"] == "Indiranagar"
        assert "nearby_5km" in data
        assert "nearby_10km" in data
        assert len(data["nearby_5km"]) > 0
        assert len(data["nearby_10km"]) >= len(data["nearby_5km"])
        # Check item structure
        first_item = data["nearby_5km"][0]
        assert "name" in first_item
        assert "distance_km" in first_item
        assert isinstance(first_item["distance_km"], (int, float))

    def test_nearby_broad_area_returns_empty(self, client):
        resp = client.get("/api/meta/nearby?location=Central%20Bangalore")
        assert resp.status_code == 200
        data = resp.json()
        assert data["nearby_5km"] == []
        assert data["nearby_10km"] == []

    def test_nearby_respects_custom_radius_below_10km(self, client):
        resp = client.get("/api/meta/nearby?location=Indiranagar&radius_km=3.0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["location"] == "Indiranagar"
        # All items in requested radius must be <= 3.0 km
        assert len(data["nearby_10km"]) > 0
        for item in data["nearby_10km"]:
            assert 0.0 < item["distance_km"] <= 3.0
        # 5 km results must be subset and <= 3.0 km
        for item in data["nearby_5km"]:
            assert 0.0 < item["distance_km"] <= 3.0
        names_10km = {item["name"] for item in data["nearby_10km"]}
        names_5km = {item["name"] for item in data["nearby_5km"]}
        assert names_5km.issubset(names_10km)

    def test_nearby_negative_and_zero_radius(self, client):
        for bad_r in (-5.0, 0.0):
            resp = client.get(f"/api/meta/nearby?location=Indiranagar&radius_km={bad_r}")
            assert resp.status_code == 200
            data = resp.json()
            assert data["nearby_5km"] == []
            assert data["nearby_10km"] == []

    def test_nearby_5km_is_always_subset_of_requested_radius(self, client):
        for radius in (2.0, 5.0, 7.5, 12.0):
            resp = client.get(f"/api/meta/nearby?location=Indiranagar&radius_km={radius}")
            assert resp.status_code == 200
            data = resp.json()
            names_10km = [item["name"] for item in data["nearby_10km"]]
            names_5km = [item["name"] for item in data["nearby_5km"]]
            assert set(names_5km).issubset(set(names_10km))
            for item in data["nearby_5km"]:
                assert item["distance_km"] <= 5.0
                assert item["distance_km"] <= radius


class TestRecommendValidation:
    def test_invalid_budget_returns_422(self, client):
        resp = client.post("/api/recommend", json={"location": "Banashankari", "budget": "mega-rich"})
        assert resp.status_code == 422

    def test_invalid_min_rating_returns_422(self, client):
        resp = client.post("/api/recommend", json={"location": "Banashankari", "min_rating": 9.9})
        assert resp.status_code == 422

    def test_negative_rating_returns_422(self, client):
        resp = client.post("/api/recommend", json={"min_rating": -1.0})
        assert resp.status_code == 422


class TestRecommendEmptyResults:
    def test_impossible_filter_returns_200_empty(self, client):
        resp = client.post("/api/recommend", json={"location": "Banashankari", "cuisine": "Ethiopian", "min_rating": 4.9})
        assert resp.status_code == 200
        assert resp.json()["recommendations"] == []

    def test_unknown_location_returns_200_empty(self, client):
        resp = client.post("/api/recommend", json={"location": "MoonBase Alpha"})
        assert resp.status_code == 200
        assert resp.json()["recommendations"] == []


class TestRecommendSuccess:
    def test_banashankari_returns_results(self, client):
        resp = client.post("/api/recommend", json={"location": "Banashankari", "cuisine": "North Indian"})
        assert resp.status_code == 200
        recs = resp.json()["recommendations"]
        assert 1 <= len(recs) <= 5

    def test_required_fields_on_each_card(self, client):
        resp = client.post("/api/recommend", json={"location": "Banashankari"})
        assert resp.status_code == 200
        for item in resp.json()["recommendations"]:
            for field in ("id", "name", "cuisines", "explanation", "rank"):
                assert field in item, f"Missing field: {field}"

    def test_result_count_does_not_exceed_5(self, client):
        resp = client.post("/api/recommend", json={"location": "Koramangala 5th Block"})
        assert resp.status_code == 200
        assert len(resp.json()["recommendations"]) <= 5

    def test_response_has_source_field(self, client):
        resp = client.post("/api/recommend", json={"location": "Banashankari", "budget": "medium"})
        assert resp.status_code == 200
        assert resp.json()["source"] in {"llm", "heuristic"}

    def test_response_echoes_query(self, client):
        payload = {"location": "Indiranagar", "budget": "high", "cuisine": "Italian"}
        resp = client.post("/api/recommend", json=payload)
        assert resp.status_code == 200
        query = resp.json()["query"]
        assert query["location"] == "Indiranagar"
        assert query["budget"] == "high"
        assert query["cuisine"] == "Italian"
