"""FastAPI route handlers for /sources.

Exposes the enabled ``SourcePreset`` registry so the frontend "add product" form
is populated from the backend rather than a hardcoded list (Item 18).

Routes
------
GET /sources → 200 list[SourcePresetRead]   enabled monitoring sources
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.source_preset import SourcePresetRead
from app.services import source_preset_service

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get(
    "",
    response_model=list[SourcePresetRead],
    summary="List enabled monitoring sources",
)
async def list_sources(db: AsyncSession = Depends(get_db)) -> list[SourcePresetRead]:
    presets = await source_preset_service.list_enabled_presets(db)
    return [SourcePresetRead(key=p.source_type, label=p.label, queue=p.queue) for p in presets]
