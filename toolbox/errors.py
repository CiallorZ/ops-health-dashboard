"""Shared error types for toolbox tools and the HTTP registry."""

from __future__ import annotations


class ToolError(ValueError):
    """A caller-facing validation or execution error."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field

    def public_dict(self) -> dict[str, str]:
        payload = {"message": str(self)}
        if self.field:
            payload["field"] = self.field
        return payload
