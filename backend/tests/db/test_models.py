from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.experience_item import ExperienceItem
from app.db.models.llm_call import LlmCall
from app.db.models.prompt_version import PromptVersion
from app.db.models.user import User


async def test_create_and_query_user(session: AsyncSession) -> None:
    # Arrange
    user = User(id=uuid.uuid4(), email="alice@example.com", name="Alice")

    # Act
    session.add(user)
    await session.flush()
    result = await session.execute(select(User).where(User.email == "alice@example.com"))
    fetched = result.scalar_one()

    # Assert
    assert fetched.email == "alice@example.com"
    assert fetched.name == "Alice"


async def test_experience_item_linked_to_user(session: AsyncSession) -> None:
    # Arrange
    user = User(id=uuid.uuid4(), email="bob@example.com", name="Bob")
    session.add(user)
    await session.flush()

    item = ExperienceItem(
        id=uuid.uuid4(),
        user_id=user.id,
        kind="work",
        content="Built a rocket",
        metadata_={"source": "manual"},
    )

    # Act
    session.add(item)
    await session.flush()
    result = await session.execute(
        select(ExperienceItem).where(ExperienceItem.user_id == user.id)
    )
    fetched = result.scalar_one()

    # Assert
    assert fetched.user_id == user.id
    assert fetched.kind == "work"
    assert fetched.metadata_ == {"source": "manual"}


async def test_prompt_version_with_json_metadata(session: AsyncSession) -> None:
    # Arrange
    pv = PromptVersion(
        id=uuid.uuid4(),
        name="cover-letter",
        version=1,
        template="Write a cover letter for {{job}}",
        model="claude-sonnet-4-5",
        temperature=0.7,
        metadata_={"author": "bruce"},
    )

    # Act
    session.add(pv)
    await session.flush()
    result = await session.execute(
        select(PromptVersion).where(PromptVersion.name == "cover-letter")
    )
    fetched = result.scalar_one()

    # Assert
    assert fetched.metadata_ == {"author": "bruce"}
    assert fetched.is_active is False


async def test_llm_call_linked_to_prompt_version(session: AsyncSession) -> None:
    # Arrange
    pv = PromptVersion(
        id=uuid.uuid4(),
        name="resume-summary",
        version=1,
        template="Summarize {{content}}",
        model="claude-haiku-4-5",
        temperature=0.5,
    )
    session.add(pv)
    await session.flush()

    call = LlmCall(
        id=uuid.uuid4(),
        prompt_version_id=pv.id,
        inputs={"content": "my resume"},
        rendered_prompt="Summarize my resume",
        response="You are a great engineer.",
        model="claude-haiku-4-5",
        cost_usd=Decimal("0.000123"),
    )

    # Act
    session.add(call)
    await session.flush()
    result = await session.execute(
        select(LlmCall).where(LlmCall.prompt_version_id == pv.id)
    )
    fetched = result.scalar_one()

    # Assert
    assert fetched.inputs == {"content": "my resume"}
    assert fetched.cost_usd == Decimal("0.000123")


@pytest.mark.parametrize(
    "kind",
    ["work", "project", "education", "skill", "achievement"],
)
async def test_experience_item_kind_values(session: AsyncSession, kind: str) -> None:
    # Arrange
    user = User(id=uuid.uuid4(), email=f"{kind}@example.com", name=kind.title())
    session.add(user)
    await session.flush()

    item = ExperienceItem(
        id=uuid.uuid4(),
        user_id=user.id,
        kind=kind,
        content=f"Did {kind} things",
    )

    # Act
    session.add(item)
    await session.flush()
    result = await session.execute(
        select(ExperienceItem).where(ExperienceItem.id == item.id)
    )
    fetched = result.scalar_one()

    # Assert
    assert fetched.kind == kind
