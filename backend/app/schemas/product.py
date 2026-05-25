"""Pydantic v2 schemas for Product."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.product import SourceType


class ProductBase(BaseModel):
    name: str
    url: str
    source_type: SourceType
    css_selector: str | None = None
    is_active: bool = True


class ProductCreate(ProductBase):
    pass


class ProductRead(ProductBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    source_type: SourceType | None = None
    css_selector: str | None = None
    is_active: bool | None = None
