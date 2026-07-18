"""Pydantic v2 schemas for SourcePreset (Item 18)."""

from pydantic import BaseModel


class SourcePresetRead(BaseModel):
    """A monitoring source exposed to the frontend "add product" form.

    ``key`` is the value the caller supplies as ``source_type`` on
    ``POST /products``; ``queue`` is informational (which worker runs it).
    """

    key: str
    label: str
    queue: str
