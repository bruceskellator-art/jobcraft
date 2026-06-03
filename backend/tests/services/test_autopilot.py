"""Service-layer tests for autopilot config persistence."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.services.autopilot import AutopilotConfig, get_autopilot_config, set_autopilot_config


async def _make_user(session: AsyncSession) -> User:
    user = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@test.com", name="Test")
    session.add(user)
    await session.flush()
    return user


class TestAutopilotConfig:
    async def test_defaults_when_unset(self, session: AsyncSession) -> None:
        # Arrange
        user = await _make_user(session)

        # Act
        cfg = await get_autopilot_config(session, user.id)

        # Assert — returns default AutopilotConfig
        assert cfg.mode == "selective"
        assert cfg.min_confidence == 0.75
        assert cfg.min_fit == 0.55
        assert cfg.daily_cap == 80
        assert "linkedin_easy_apply" in cfg.auto_submit_sources
        assert "mycareersfuture" in cfg.auto_submit_sources

    async def test_set_then_get_round_trips(self, session: AsyncSession) -> None:
        # Arrange
        user = await _make_user(session)
        cfg = AutopilotConfig(
            mode="full",
            auto_submit_sources=["linkedin_easy_apply"],
            min_confidence=0.9,
            min_fit=0.7,
            daily_cap=50,
        )

        # Act
        await set_autopilot_config(session, user.id, cfg)
        retrieved = await get_autopilot_config(session, user.id)

        # Assert
        assert retrieved.mode == "full"
        assert retrieved.auto_submit_sources == ["linkedin_easy_apply"]
        assert abs(retrieved.min_confidence - 0.9) < 1e-9
        assert abs(retrieved.min_fit - 0.7) < 1e-9
        assert retrieved.daily_cap == 50

    async def test_set_twice_updates_config(self, session: AsyncSession) -> None:
        # Arrange
        user = await _make_user(session)
        cfg1 = AutopilotConfig(mode="off", daily_cap=10)
        cfg2 = AutopilotConfig(mode="full", daily_cap=100)

        # Act
        await set_autopilot_config(session, user.id, cfg1)
        await set_autopilot_config(session, user.id, cfg2)
        retrieved = await get_autopilot_config(session, user.id)

        # Assert — second write wins
        assert retrieved.mode == "full"
        assert retrieved.daily_cap == 100

    async def test_config_isolated_per_user(self, session: AsyncSession) -> None:
        # Arrange
        user_a = await _make_user(session)
        user_b = await _make_user(session)
        cfg_a = AutopilotConfig(mode="off", daily_cap=5)

        # Act — only user_a has config set
        await set_autopilot_config(session, user_a.id, cfg_a)
        cfg_b = await get_autopilot_config(session, user_b.id)

        # Assert — user_b gets defaults
        assert cfg_b.mode == "selective"
        assert cfg_b.daily_cap == 80

    async def test_autopilot_config_default_list_is_not_shared(self) -> None:
        # Arrange — create two independent default instances
        cfg1 = AutopilotConfig()
        cfg2 = AutopilotConfig()

        # Act
        cfg1.auto_submit_sources.append("indeed")

        # Assert — cfg2 is not mutated (Field(default_factory=...) gives independent lists)
        assert "indeed" not in cfg2.auto_submit_sources
