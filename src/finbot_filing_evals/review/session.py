"""Session-only drafts; no persistence or Streamlit dependency."""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from .editor import COLUMNS, labels_to_rows, validate_rows


@dataclass
class EditorDraft:
    saved_labels: dict[str, Any]
    opened_fingerprint: str
    base_rows: list[dict[str, Any]] = field(init=False)
    rows: list[dict[str, Any]] = field(init=False)
    generation: int = 0

    def __post_init__(self) -> None:
        self.saved_labels = deepcopy(self.saved_labels)
        self.base_rows = labels_to_rows(self.saved_labels)
        self.rows = deepcopy(self.base_rows)

    @property
    def dirty(self) -> bool:
        result = validate_rows(self.rows)
        return bool(result.errors) or result.labels != self.saved_labels

    def capture_widget_changes(self, changes: Mapping[str, Any]) -> None:
        """Read the editor's public delta state before a navigation callback.

        An edit and a filing selection can arrive together before the next
        script run reads data_editor's return value. Check those latest cells,
        deletions and additions rather than only the previous run's draft.
        Indices refer to the stable base input, as in Streamlit's EditorState.
        """
        rows = deepcopy(self.base_rows)
        for index, cells in changes.get("edited_rows", {}).items():
            rows[int(index)].update(cells)
        for index in sorted(changes.get("deleted_rows", []), reverse=True):
            del rows[index]
        rows.extend(
            {column: row.get(column) for column in COLUMNS}
            for row in changes.get("added_rows", [])
        )
        self.rows = rows

    def discard(self) -> None:
        self.rows = deepcopy(self.base_rows)
        # A fresh widget key drops Streamlit's old edit/add/delete deltas.
        self.generation += 1
