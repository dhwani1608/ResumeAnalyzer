from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from api.middleware.auth import api_key_auth


router = APIRouter()


@router.get("/skills/taxonomy")
async def get_taxonomy(request: Request, _: str = Depends(api_key_auth)):
    normalizer = request.app.state.normalizer
    return {
        "request_id": request.state.request_id,
        "total_skills": len(normalizer.taxonomy),
        "taxonomy": normalizer.taxonomy,
    }


@router.get("/skills/search")
async def search_skills(request: Request, q: str = Query(""), _: str = Depends(api_key_auth)):
    normalizer = request.app.state.normalizer
    query = q.lower().strip()
    results = []
    for canonical, payload in normalizer.taxonomy.items():
        aliases = payload.get("aliases", [])
        if query in canonical.lower() or any(query in a.lower() for a in aliases):
            results.append({"skill": canonical, **payload})
    return {"request_id": request.state.request_id, "query": q, "results": results[:100]}
