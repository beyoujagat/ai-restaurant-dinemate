"""HTTP API Router (Phase 5)."""
from __future__ import annotations
import logging, time, uuid
from typing import Any
from fastapi import APIRouter, HTTPException, Request
from app.catalog.store import CatalogNotFoundError, CatalogStore
from app.domain.models import Preference, RecommendationResponse
from app.services.recommend import RecommendService

logger = logging.getLogger(__name__)
router = APIRouter()

_store = None


def _get_store():
    global _store
    if _store is None:
        _store = CatalogStore()
    return _store


@router.get("/meta/options", summary="Catalog facet options")
def get_meta_options() -> dict:
    try:
        store = _get_store()
    except CatalogNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return store.get_meta_options()


@router.get("/meta/nearby", summary="Nearby verified neighbourhoods")
def get_nearby_neighbourhoods(
    location: str,
    radius_km: float = 10.0,
) -> dict[str, Any]:
    """
    Lookup verified nearby neighbourhoods within radius_km (default 10 km),
    categorized by 5 km and requested radius bands for UI suggestions.
    """
    if radius_km <= 0:
        return {
            "location": location,
            "nearby_5km": [],
            "nearby_10km": [],
        }

    from app.catalog.geo import find_nearby_neighbourhoods_with_distance
    requested_nearby = find_nearby_neighbourhoods_with_distance(location, radius_km=radius_km)
    nearby_items = [{"name": name, "distance_km": dist} for name, dist in requested_nearby]
    nearby_5km = [item for item in nearby_items if item["distance_km"] <= 5.0]

    return {
        "location": location,
        "nearby_5km": nearby_5km,
        "nearby_10km": nearby_items,
    }


@router.post("/recommend", response_model=RecommendationResponse)
def post_recommend(preference: Preference, request: Request) -> RecommendationResponse:
    request_id = str(uuid.uuid4())[:8]
    t_start = time.perf_counter()
    logger.info("[%s] POST /api/recommend filters=%s", request_id, preference.model_dump(exclude_none=True))
    try:
        store = _get_store()
    except CatalogNotFoundError as exc:
        logger.error("[%s] Catalog not found: %s", request_id, exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    service = RecommendService(store=store)
    t0 = time.perf_counter()
    response = service.recommend(preference)
    t1 = time.perf_counter()
    logger.info(
        "[%s] Done candidate_count=%d results=%d source=%s service_ms=%.0f total_ms=%.0f",
        request_id, response.candidate_count, len(response.recommendations),
        response.source, (t1-t0)*1000, (time.perf_counter()-t_start)*1000,
    )
    return response
