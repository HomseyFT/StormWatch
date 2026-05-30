"""
Sidebar navigation widget.
Renders tab list with arrow key + enter/space selection.
Highlights active tab and supports alert flash state.
"""

from __future__ import annotations

from enum import Enum

from textual.app import ComposeResult
from textual.binding import Binding
from textual.reactive import reactive
from textual.widgets import Static
from textual.widget import Widget


class TabId(str, Enum):
    ALERTS = "alerts"
    CONDITIONS = "conditions"
    INDICATORS = "indicators"
    FORECAST = "forecast"


_TAB_LABELS: dict[TabId, str] = {
    TabId.ALERTS:     "⚡ Alerts",
    TabId.CONDITIONS: "🌡  Conditions",
    TabId.INDICATORS: "🌪  Indicators",
    TabId.FORECAST:   "📅 Forecast",
}

_KEYBIND_LABELS: dict[TabId, str] = {
    TabId.ALERTS:     "[1]",
    TabId.CONDITIONS: "[2]",
    TabId.INDICATORS: "[3]",
    TabId.FORECAST:   "[4]",
}


class Sidebar(Widget):
    """
    Vertical tab list. Arrow keys move selection; Enter/Space confirms.
    The app listens for TabSelected messages to switch panes.
    """

    DEFAULT_CSS = """
    Sidebar {
        padding: 1 1;
    }

    Sidebar Static.tab-item {
        padding: 0 1;
        height: 3;
        content-align: left middle;
        border: round $surface-lighten-1;
        margin-bottom: 1;
        color: $text-muted;
    }

    Sidebar Static.tab-item.active {
        border: round $primary;
        color: $primary;
        text-style: bold;
        background: $primary 15%;
    }

    Sidebar Static.tab-item:hover {
        background: $surface-lighten-2;
    }

    Sidebar .sidebar-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        padding-bottom: 1;
        border-bottom: solid $primary;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("up,k", "prev_tab", "Previous", show=False),
        Binding("down,j", "next_tab", "Next", show=False),
        Binding("enter,space", "select_tab", "Select", show=False),
    ]

    _tabs = list(TabId)
    _cursor: reactive[int] = reactive(0)

    def compose(self) -> ComposeResult:
        yield Static("STORMWATCH", classes="sidebar-title")
        for i, tid in enumerate(self._tabs):
            label = f"{_KEYBIND_LABELS[tid]}  {_TAB_LABELS[tid]}"
            classes = "tab-item active" if i == 0 else "tab-item"
            yield Static(label, id=f"tab-{tid.value}", classes=classes)

    def set_active(self, tab: TabId) -> None:
        for tid in self._tabs:
            widget = self.query_one(f"#tab-{tid.value}", Static)
            if tid == tab:
                widget.add_class("active")
            else:
                widget.remove_class("active")
        self._cursor = self._tabs.index(tab)

    def watch__cursor(self, cursor: int) -> None:
        for i, tid in enumerate(self._tabs):
            widget = self.query_one(f"#tab-{tid.value}", Static)
            if i == cursor:
                widget.add_class("active")
            else:
                widget.remove_class("active")

    def action_prev_tab(self) -> None:
        self._cursor = (self._cursor - 1) % len(self._tabs)

    def action_next_tab(self) -> None:
        self._cursor = (self._cursor + 1) % len(self._tabs)

    def action_select_tab(self) -> None:
        tid = self._tabs[self._cursor]
        self.app.action_show_tab(tid.value)  # type: ignore[attr-defined]
