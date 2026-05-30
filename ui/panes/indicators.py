"""Indicators pane — severe weather atmospheric indicators."""

from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from api.open_meteo import SevereIndicators


class IndicatorsPane(Widget):
    data = reactive[Optional[SevereIndicators]](None)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield Static("Loading indicators…", id="indicators-content")

    def update_data(self, data: SevereIndicators) -> None:
        self.data = data

    def watch_data(self, old: Optional[SevereIndicators], new: Optional[SevereIndicators]) -> None:
        self._update_display()

    def on_mount(self) -> None:
        self._update_display()

    def _update_display(self) -> None:
        try:
            content = self.query_one("#indicators-content", Static)
        except Exception:
            return

        if self.data is None:
            content.update("Loading indicators... (waiting for first fetch)")
            return

        d = self.data
        cache_note = "  [CACHED]" if d.from_cache else ""
        ts = d.updated_at.strftime("%H:%M:%S")

        if d.risk_label == "N/A":
            lines = [
                f"Severe Weather Indicators — Updated: {ts}{cache_note}",
                "─" * 60,
                "",
                "⚠️  Severe weather indicators are not available for your region.",
                "",
                "The Open-Meteo standard API does not provide CAPE, lifted index,",
                "or other severe weather parameters at this location.",
                "",
                "Consider using the NWS API for severe weather alerts instead.",
                "",
                "The Alerts tab will show any active warnings for your area.",
            ]
        else:
            lines = [
                f"Severe Weather Indicators — Updated: {ts}{cache_note}",
                "─" * 60,
                f"  Composite Risk:  {d.risk_label.upper()} ({d.risk_score}/10)",
                "",
                f"  CAPE:                 {d.cape_jkg:>8.0f} J/kg",
                f"  Lifted Index (LI):    {d.lifted_index:>+8.1f} °C",
                f"  CIN:                  {d.cin_jkg:>+8.0f} J/kg",
                f"  Precipitable Water:   {d.precipitable_water_in:>8.2f} in",
                f"  Wind Shear (0-6km):   {d.wind_shear_mph:>8.1f} mph",
            ]

        content.update("\n".join(lines))
