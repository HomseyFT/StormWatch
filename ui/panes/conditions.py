"""Conditions pane — current weather conditions display."""

from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from api.open_meteo import CurrentConditions


class ConditionsPane(Widget):
    DEFAULT_CSS = """
    ConditionsPane .section-header {
        text-style: bold;
        color: $primary;
        padding-bottom: 1;
    }
    """

    data = reactive[Optional[CurrentConditions]](None)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield Static("Loading conditions…", id="conditions-content")

    def update_data(self, data: CurrentConditions) -> None:
        self.data = data

    def watch_data(self, old: Optional[CurrentConditions], new: Optional[CurrentConditions]) -> None:
        self._update_display()

    def on_mount(self) -> None:
        self._update_display()

    def _update_display(self) -> None:
        try:
            content = self.query_one("#conditions-content", Static)
        except:
            return

        if self.data is None:
            content.update("Loading conditions... (waiting for first fetch)")
            return

        d = self.data
        cache_note = "  [CACHED]" if d.from_cache else ""
        ts = d.updated_at.strftime("%H:%M:%S")

        lines = [
            f"Current Conditions — Updated: {ts}{cache_note}",
            "─" * 60,
            f"  {d.weather_desc}",
            "",
            f"  {'Temperature:':<22} {d.temperature_f:.1f}°F",
            f"  {'Feels Like:':<22} {d.feels_like_f:.1f}°F",
            f"  {'Dew Point:':<22} {d.dew_point_f:.1f}°F",
            f"  {'Humidity:':<22} {d.humidity_pct:.0f}%",
            "",
            f"  {'Wind:':<22} {d.wind_speed_mph:.1f} mph {d.wind_direction_label} ({d.wind_direction_deg:.0f}°)",
            f"  {'Wind Gusts:':<22} {d.wind_gusts_mph:.1f} mph",
            "",
            f"  {'Pressure:':<22} {d.pressure_inhg:.2f} inHg",
            f"  {'Visibility:':<22} {d.visibility_miles:.1f} mi",
            f"  {'Precipitation:':<22} {d.precipitation_in:.2f} in",
        ]

        content.update("\n".join(lines))
