"""Alerts pane — displays active NWS storm alerts with distance and timing."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from api.nws import Alert, AlertsResult

_SEVERITY_STYLE = {
    4: ("⛔ EXTREME",  "severity-extreme"),
    3: ("🔴 SEVERE",   "severity-severe"),
    2: ("🟠 MODERATE", "severity-moderate"),
    1: ("🟡 MINOR",    "severity-minor"),
    0: ("⚪ UNKNOWN",  "severity-minor"),
}


def _fmt_dt(dt: Optional[datetime]) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%b %d %H:%M")


def _fmt_distance(edge: Optional[float], center: Optional[float]) -> str:
    if edge is None:
        return "Distance: unavailable"
    if edge == 0.0:
        return f"⚠ INSIDE POLYGON  |  Center: {center:.0f}mi" if center else "⚠ INSIDE POLYGON"
    return f"Edge: {edge:.1f}mi  |  Center: {center:.0f}mi"


def _render_alert(alert: Alert) -> str:
    label, _ = _SEVERITY_STYLE.get(alert.severity_level, _SEVERITY_STYLE[0])
    onset = _fmt_dt(alert.onset)
    expires = _fmt_dt(alert.expires)
    dist = _fmt_distance(alert.distance_to_edge_miles, alert.distance_to_center_miles)

    lines = [
        f"{label} — {alert.event}",
        f"Area:    {alert.area_desc}",
        f"Onset:   {onset}   Expires: {expires}",
        f"{dist}",
        f"Urgency: {alert.urgency}  |  Certainty: {alert.certainty}",
    ]
    if alert.headline:
        lines.append(f"\n{alert.headline}")
    return "\n".join(lines)


class AlertsPane(Widget):
    DEFAULT_CSS = """
    AlertsPane .alert-card {
        border: round $primary;
        padding: 1 2;
        margin-bottom: 1;
    }
    AlertsPane .alert-card.severity-extreme { border: round $error; }
    AlertsPane .alert-card.severity-severe  { border: round $warning; }
    AlertsPane .no-alerts {
        color: $success;
        text-style: bold;
        padding: 2;
    }
    AlertsPane .staleness {
        text-align: right;
        color: $text-muted;
        padding-bottom: 1;
    }
    """

    result = reactive[Optional[AlertsResult]](None)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield Static("Loading alerts…", id="alerts-content")

    def update_data(self, data: AlertsResult) -> None:
        self.result = data

    def watch_result(self, old: Optional[AlertsResult], new: Optional[AlertsResult]) -> None:
        """Called when result changes - update the display."""
        self._update_display()

    def on_mount(self) -> None:
        """Widget is now mounted, safe to update."""
        self._update_display()

    def _update_display(self) -> None:
        """Update the display with current data."""
        try:
            content = self.query_one("#alerts-content", Static)
        except:
            # Not mounted yet
            return

        if self.result is None:
            content.update("Loading alerts... (waiting for first fetch)")
            return

        cache_note = "  [CACHED]" if self.result.from_cache else ""
        updated = self.result.updated_at
        ts = updated.strftime("%H:%M:%S") if updated else "—"
        header = f"Active Alerts — Updated: {ts}{cache_note}\n{'─' * 60}\n"

        if not self.result.alerts:
            content.update(header + "✅  No active alerts in your area.")
            return

        sections = [header]
        for alert in self.result.alerts:
            sections.append(_render_alert(alert))
            sections.append("─" * 60)

        content.update("\n".join(sections))
