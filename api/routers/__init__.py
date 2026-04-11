from .candidates import router as candidates_router
from .jobs import router as jobs_router
from .legacy import router as legacy_router
from .match import router as match_router
from .parse import router as parse_router
from .taxonomy import router as taxonomy_router

__all__ = ["parse_router", "candidates_router", "match_router", "taxonomy_router", "jobs_router", "legacy_router"]
