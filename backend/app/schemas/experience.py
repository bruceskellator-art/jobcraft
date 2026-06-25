from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _empty_str_to_none(v: object) -> object:
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


NullableDate = Annotated[date | None, BeforeValidator(_empty_str_to_none)]

ExperienceKind = Literal["work", "project", "education", "skill", "achievement"]


class ExperienceItemBase(BaseModel):
    kind: ExperienceKind
    title: str | None = None
    organization: str | None = None
    start_date: NullableDate = None
    end_date: NullableDate = None
    content: str = Field(..., min_length=1)
    tags: list[str] | None = None
    metadata_: dict | None = Field(default=None, alias="metadata")

    model_config = ConfigDict(populate_by_name=True)


class ExperienceItemCreate(ExperienceItemBase):
    pass


class ExperienceItemUpdate(BaseModel):
    kind: ExperienceKind | None = None
    title: str | None = None
    organization: str | None = None
    start_date: NullableDate = None
    end_date: NullableDate = None
    content: str | None = Field(default=None, min_length=1)
    tags: list[str] | None = None
    metadata_: dict | None = Field(default=None, alias="metadata")

    model_config = ConfigDict(populate_by_name=True)


class ExperienceItemRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    kind: ExperienceKind
    title: str | None
    organization: str | None
    start_date: date | None
    end_date: date | None
    content: str
    tags: list[str] | None
    sort_order: int | None = None
    metadata_: dict | None = Field(default=None, serialization_alias="metadata")
    created_at: datetime | None
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ReorderRequest(BaseModel):
    kind: ExperienceKind
    ids: list[uuid.UUID]
