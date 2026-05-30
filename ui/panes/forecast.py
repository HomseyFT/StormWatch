"""Forecast pane — 24-hour hourly forecast display."""

from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from api.open_meteo import Forecast, HourlySlice


def _bar(pct: float, width: int = 10) -> str:
    """Simple ASCII progress bar for precipitation probability."""
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _render_slice(s: HourlySlice) -> str:
    time_str = s.time.strftime("%H:%M")
    precip_bar = _bar(s.precipitation_prob_pct)
    cape_flag = " ⚡" if s.cape_jkg >= 1000 else ""
    return (
        f"  {time_str}  "
        f"{s.temperature_f:>5.1f}°F  "
        f"💨{s.wind_speed_mph:>4.0f}mph  "
        f"💧{precip_bar} {s.precipitation_prob_pct:>3.0f}%  "
        f"{s.weather_desc:<22}"
        f"{cape_flag}"
    )


class ForecastPane(Widget):
    data = reactive[Optional[Forecast]](None)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield Static("Loading forecast…", id="forecast-content")

    def update_data(self, data: Forecast) -> None:
        self.data = data

    def watch_data(self, old: Optional[Forecast], new: Optional[Forecast]) -> None:
        self._update_display()

    def on_mount(self) -> None:
        self._update_display()

    def _update_display(self) -> None:
        try:
            content = self.query_one("#forecast-content", Static)
        except:
            return

        if self.data is None:
            content.update("Loading forecast... (waiting for first fetch)")
            return

        d = self.data
        cache_note = "  [CACHED]" if d.from_cache else ""
        ts = d.updated_at.strftime("%H:%M:%S")

        header = [
            f"24-Hour Forecast — Updated: {ts}{cache_note}",
            "─" * 60,
            f"  {'TIME':<6}  {'TEMP':>7}  {'WIND':>8}  {'PRECIP PROB':>14}  {'CONDITIONS':<22}",
            "  " + "─" * 58,
        ]

        rows = [_render_slice(s) for s in d.hourly]

        footer = [
            "",
            "  ⚡ = CAPE ≥ 1000 J/kg (elevated storm potential)",
        ]

        output = "\n".join(header + rows + footer)
        content.update(output)
