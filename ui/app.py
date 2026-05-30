"""
StormWatch — main Textual application.
Mounts the sidebar and pane stack, wires the scheduler,
handles data update messages and alert flash state.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.css.query import NoMatches
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Footer, Header

from cache.store import CacheStore, DataKey
from core.config import AppConfig
from core.location import Coordinates, resolve_location
from core.geocoder import reverse_geocode
from core.scheduler import Scheduler, SchedulerConfig
from notifications.notifier import Notifier
from ui.sidebar import Sidebar, TabId
from ui.panes.alerts import AlertsPane
from ui.panes.conditions import ConditionsPane
from ui.panes.indicators import IndicatorsPane
from ui.panes.forecast import ForecastPane

logger = logging.getLogger(__name__)


class DataUpdated(Message):
    """Posted to the app when fresh data arrives from the scheduler."""
    def __init__(self, channel: str, payload: object) -> None:
        super().__init__()
        self.channel = channel
        self.payload = payload


class NewAlertReceived(Message):
    """Posted when a new NWS alert is detected."""


class StormWatchApp(App):
    """Root Textual application."""

    CSS = """
    Screen {
        layout: horizontal;
    }

    Sidebar {
        width: 20;
        height: 100%;
        background: $surface;
        border-right: tall $primary;
    }

    #pane-container {
        width: 1fr;
        height: 100%;
    }

    AlertsPane, ConditionsPane, IndicatorsPane, ForecastPane {
        width: 100%;
        height: 100%;
        padding: 1 2;
    }

    .hidden {
        display: none;
    }

    /* Staleness indicator colours */
    .staleness-fresh  { color: $success; }
    .staleness-amber  { color: $warning; }
    .staleness-red    { color: $error; }

    /* Alert severity colours */
    .severity-extreme { color: $error; text-style: bold; }
    .severity-severe  { color: $warning; text-style: bold; }
    .severity-moderate{ color: $accent; }
    .severity-minor   { color: $text; }

    /* Alert flash animation */
    Sidebar .flash {
        background: $error 40%;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("1", "show_tab('alerts')", "Alerts"),
        Binding("2", "show_tab('conditions')", "Conditions"),
        Binding("3", "show_tab('indicators')", "Indicators"),
        Binding("4", "show_tab('forecast')", "Forecast"),
        Binding("r", "force_refresh", "Refresh"),
    ]

    # Reactive: which tab is active
    active_tab: reactive[TabId] = reactive(TabId.ALERTS)
    # Reactive: flash the alerts tab (True for ~1s on new alert)
    alert_flash: reactive[bool] = reactive(False)

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config
        self._cache: Optional[CacheStore] = None
        self._scheduler: Optional[Scheduler] = None
        self._notifier = Notifier(
            sound_enabled=config.notifications.sound,
            visual_enabled=config.notifications.visual_flash,
        )
        self._notifier.register_flash_callback(self._flash_alert_tab)
        self._coords: Optional[Coordinates] = None

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Sidebar(id="sidebar")
        from textual.containers import Container
        with Container(id="pane-container"):
            yield AlertsPane(id="pane-alerts")
            yield ConditionsPane(id="pane-conditions")
            yield IndicatorsPane(id="pane-indicators")
            yield ForecastPane(id="pane-forecast")
        yield Footer()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def on_mount(self) -> None:
        self._show_pane(TabId.ALERTS)
        self.title = "StormWatch"
        self.sub_title = "Initializing…"

        # Open cache
        self._cache = CacheStore(
            amber_minutes=self._config.cache.staleness_amber_minutes,
            red_minutes=self._config.cache.staleness_red_minutes,
        )
        await self._cache.open()

        # Resolve location in background
        asyncio.create_task(self._initialize_location())

    async def _initialize_location(self) -> None:
        try:
            self._coords = await resolve_location(
                manual_lat=self._config.location.lat,
                manual_lon=self._config.location.lon,
                manual_label=self._config.location.label,
            )
            label = self._coords.label or await reverse_geocode(
                self._coords.lat, self._coords.lon
            )
            self.sub_title = f"{label}  [{self._coords.source}]"
            await self._start_scheduler()
        except RuntimeError as exc:
            self.sub_title = f"Location error: {exc}"
            logger.error("Location resolution failed: %s", exc)

    async def _start_scheduler(self) -> None:
        assert self._coords and self._cache
        self._scheduler = Scheduler(
            config=SchedulerConfig(
                alert_poll_seconds=self._config.refresh.alert_poll_seconds,
                conditions_poll_seconds=self._config.refresh.conditions_poll_seconds,
            ),
            cache=self._cache,
            on_new_alert=self._on_new_alert,
            on_data_update=self._on_data_update,
        )
        self._scheduler.set_coordinates(self._coords)
        await self._scheduler.start()

    async def on_unmount(self) -> None:
        if self._scheduler:
            await self._scheduler.stop()
        if self._cache:
            await self._cache.close()

    # ------------------------------------------------------------------
    # Scheduler callbacks → post Textual messages (thread-safe)
    # ------------------------------------------------------------------

    async def _on_new_alert(self) -> None:
        await self._notifier.alert(severity_level=3)
        self.post_message(NewAlertReceived())

    async def _on_data_update(self, channel: str, payload: object) -> None:
        self.post_message(DataUpdated(channel=channel, payload=payload))

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

    def on_data_updated(self, message: DataUpdated) -> None:
        pane_map = {
            "alerts": "pane-alerts",
            "conditions": "pane-conditions",
            "indicators": "pane-indicators",
            "forecast": "pane-forecast",
        }
        pane_id = pane_map.get(message.channel)
        if not pane_id:
            return
        try:
            pane = self.query_one(f"#{pane_id}")
            pane.update_data(message.payload)  # type: ignore[attr-defined]
        except NoMatches:
            pass

    def on_new_alert_received(self, _: NewAlertReceived) -> None:
        # Switch to alerts tab automatically
        self.active_tab = TabId.ALERTS
        self._show_pane(TabId.ALERTS)
        self.alert_flash = True
        self.set_timer(1.2, self._clear_flash)

    def _clear_flash(self) -> None:
        self.alert_flash = False

    # ------------------------------------------------------------------
    # Tab switching
    # ------------------------------------------------------------------

    def action_show_tab(self, tab: str) -> None:
        try:
            tid = TabId(tab)
        except ValueError:
            return
        self.active_tab = tid
        self._show_pane(tid)
        try:
            self.query_one("#sidebar", Sidebar).set_active(tid)
        except NoMatches:
            pass

    def _show_pane(self, tab: TabId) -> None:
        pane_ids = {
            TabId.ALERTS: "pane-alerts",
            TabId.CONDITIONS: "pane-conditions",
            TabId.INDICATORS: "pane-indicators",
            TabId.FORECAST: "pane-forecast",
        }
        for tid, pid in pane_ids.items():
            try:
                pane = self.query_one(f"#{pid}")
                if tid == tab:
                    pane.remove_class("hidden")
                else:
                    pane.add_class("hidden")
            except NoMatches:
                pass

    def action_force_refresh(self) -> None:
        if self._scheduler and self._coords:
            asyncio.create_task(self._scheduler._fetch_alerts())
            asyncio.create_task(self._scheduler._fetch_conditions())

    # ------------------------------------------------------------------
    # Flash helper (called by Notifier)
    # ------------------------------------------------------------------

    async def _flash_alert_tab(self) -> None:
        try:
            sidebar = self.query_one("#sidebar", Sidebar)
            sidebar.add_class("flash")
            await asyncio.sleep(0.8)
            sidebar.remove_class("flash")
        except NoMatches:
            pass
