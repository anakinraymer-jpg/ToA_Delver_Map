from __future__ import annotations

LESSER_CURSE  = "Lesser Curse"
GREATER_CURSE = "Greater Curse"
CURSE_LEVELS: list[str] = [LESSER_CURSE, GREATER_CURSE]


class CurseMap:
    def __init__(self):
        self._data: dict[int, str] = {}

    def set(self, node: int, level: str) -> None:
        self._data[node] = level

    def clear(self, node: int) -> None:
        self._data.pop(node, None)

    def clear_all(self) -> None:
        self._data.clear()

    def get(self, node: int) -> str | None:
        return self._data.get(node)

    @property
    def all(self):
        return self._data.items()

    def to_dict(self) -> dict[str, str]:
        return {str(k): v for k, v in self._data.items()}

    def from_dict(self, data: dict) -> None:
        self._data.clear()
        for k, v in data.items():
            try:
                self._data[int(k)] = v
            except (ValueError, TypeError):
                pass
