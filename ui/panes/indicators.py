"""Indicators pane — severe weather atmospheric indicators and composite risk score."""

from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from api.open_meteo import SevereIndicators
from cache.store import CacheStore, DataKey

_RISK_STYLE = {
    "Low": "🟢",
    "Moderate": "🟡",
    "High": "🟠",
    "Extreme": "🔴",
    "N/A": "⚪",
}

_CAPE_DESC = [
    (0, "Stable — no convective energy"),
    (500, "Weak — marginal storm potential"),
    (1000, "Moderate — storm development possible"),
    (2000, "High — significant storm potential"),
    (3000, "Very High — severe storms likely"),
]

_LI_DESC = [
    (2, "Stable"),
    (0, "Near neutral"),
    (-2, "Slightly unstable"),
    (-4, "Moderately unstable"),
    (-6, "Very unstable — severe potential"),
]


def _cape_label(cape: float) -> str:
    label = _CAPE_DESC[0][1]
    for threshold, desc in _CAPE_DESC:
        if cape >= threshold:
            label = desc
    return label


def _li_label(li: float) -> str:
    label = _LI_DESC[0][1]
    for threshold, desc in _LI_DESC:
        if li <= threshold:
            label = desc
    return label


class IndicatorsPane(Widget):
    data = reactive[Optional[SevereIndicators]](None)
    nws_severe = reactive[Optional[dict]](None)

    def __init__(self, cache: Optional[CacheStore] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._cache = cache

    def compose(self) -> ComposeResult:
        yield Static("Loading indicators…", id="indicators-content")

    def update_data(self, data: SevereIndicators) -> None:
        self.data = data
        if self._cache:
            import asyncio
            asyncio.create_task(self._load_nws_severe())

    async def _load_nws_severe(self) -> None:
        if self._cache:
            nws_data = await self._cache.get(DataKey.NWS_SEVERE)
            if nws_data:
                self.nws_severe = nws_data

    def watch_data(self, old: Optional[SevereIndicators], new: Optional[SevereIndicators]) -> None:
        self._update_display()

    def watch_nws_severe(self, old: Optional[dict], new: Optional[dict]) -> None:
        self._update_display()

    def on_mount(self) -> None:
        self._update_display()

    def _update_display(self) -> None:
        try:
            content = self.query_one("#indicators-content", Static)
        except Exception:
            return

        if self.data is None:
            content.update("Loading indicators… (waiting for first fetch)")
            return

        d = self.data
        cache_note = "  [CACHED]" if d.from_cache else ""
        ts = d.updated_at.strftime("%H:%M:%S")
        risk_icon = _RISK_STYLE.get(d.risk_label, "⚪")

        lines = [
            f"Severe Weather Indicators — Updated: {ts}{cache_note}",
            "─" * 60,
            f"  Composite Risk:  {risk_icon} {d.risk_label.upper()} ({d.risk_score}/10)",
        ]

        # Add NWS summary if available
        if self.nws_severe and self.nws_severe.get("risk_level"):
            nws = self.nws_severe
            if nws.get("active_warnings"):
                lines.append(f"  ⚠️ NWS Active: {', '.join(nws['active_warnings'])}")
            lines.append(f"  NWS Threats: 🌪️{nws.get('tornado_risk', 'Low')}  🧊{nws.get('hail_risk', 'Low')}  💨{nws.get('wind_risk', 'Low')}  💧{nws.get('flood_risk', 'Low')}")
            lines.append("")

        lines.extend([
            "",
            "  ── Atmospheric Parameters ──────────────────────────",
            f"  {'CAPE:':<28} {d.cape_jkg:>8.0f} J/kg",
            f"  {'  → ' + _cape_label(d.cape_jkg):<32}",
            "",
            f"  {'Lifted Index (LI):':<28} {d.lifted_index:>+8.1f} °C",
            f"  {'  → ' + _li_label(d.lifted_index):<32}",
            "",
            f"  {'Conv. Inhibition (CIN):':<28} {d.cin_jkg:>+8.0f} J/kg",
            f"  {'  → ' + ('Weak inhibition' if d.cin_jkg > -100 else 'Strong inhibition — storms suppressed'):<32}",
            "",
            f"  {'Precipitable Water:':<28} {d.precipitable_water_in:>8.2f} in",
            f"  {'Wind Shear (0-6km proxy):':<28} {d.wind_shear_mph:>8.1f} mph",
            "",
            "  ── Interpretation ──────────────────────────────────",
        ])

        # Plain-language summary (prioritize NWS if available)
        if self.nws_severe and self.nws_severe.get("risk_level") in ["High", "Extreme"]:
            lines.append("  ⚠️ NWS indicates significant severe weather potential.")
            lines.append("  Monitor alerts tab for official warnings.")
        elif d.risk_score <= 2:
            lines.append("  Atmosphere is stable. Severe weather unlikely.")
        elif d.risk_score <= 5:
            lines.append("  Some instability present. Monitor conditions.")
        elif d.risk_score <= 7:
            lines.append("  Significant instability. Severe storms possible.")
        else:
            lines.append("  ⚠ Extreme instability. Severe weather highly likely.")

        if self.nws_severe and self.nws_severe.get("detailed_summary"):
            lines.append(f"\n  {self.nws_severe['detailed_summary']}")

        content.update("\n".join(lines))
