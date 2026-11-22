"""Shared base of the input errors raised by the simulation, run and overlay use cases."""

from __future__ import annotations

from typing import Any


class InputError(ValueError):
    """Invalid input: HTTP 422 with the valid values when there is a closed set, 404 when
    `not_found` (it names something that does not exist) and 409 when `conflict`."""

    def __init__(
        self,
        field: str,
        message: str,
        valid: list[str] | None = None,
        not_found: bool = False,
        conflict: bool = False,
    ) -> None:
        super().__init__(message)
        self.field, self.message, self.valid = field, message, valid or []
        self.not_found, self.conflict = not_found, conflict

    def detail(self) -> dict[str, Any]:
        out: dict[str, Any] = {"field": self.field, "message": self.message}
        if self.valid:
            out["valid"] = self.valid
        return out
