from __future__ import annotations


class LLMError(Exception):
    """Raised when an LLM call fails or a response cannot be parsed."""

    def __init__(self, message: str, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.cause = cause
