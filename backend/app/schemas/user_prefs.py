from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

ThemePreference = Literal["light", "dark", "system"]


class UiPrefs(BaseModel):
    """User interface preferences persisted on the user record.

    Kept deliberately small; add fields here as new cross-device UI
    settings are introduced.
    """

    theme: ThemePreference = "system"
