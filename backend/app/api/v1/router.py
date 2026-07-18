"""Aggregated APIRouter for /api/v1.

All sub-routers are registered here and exposed as ``api_router``.
``main.py`` mounts this under ``/api/v1``.
"""

from fastapi import APIRouter

from app.api.v1 import alerts, prices, products, sources

api_router = APIRouter()
api_router.include_router(products.router)
api_router.include_router(prices.router)
api_router.include_router(alerts.router)
api_router.include_router(sources.router)
