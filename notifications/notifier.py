"""
Alert notifier.
Abstracts sound and visual notification so the cyberdeck build
can swap in richer audio without touching anything else.

Sound backends (tried in order):
  1. pygame.mixer — if available and audio hardware present
  2. Terminal bell (\a) — universal fallback
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Optional

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, sound_enabled: bool = True, visual_enabled: bool = True) -> None:
        self._sound = sound_enabled
        self._visual = visual_enabled
        self._pygame_available = False
        self._flash_callback: Optional[callable] = None

        if sound_enabled:
            self._pygame_available = self._init_pygame()

    def _init_pygame(self) -> bool:
        try:
            import pygame.mixer  # type: ignore
            pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
            logger.debug("pygame.mixer initialized for audio alerts")
            return True
        except Exception as exc:
            logger.debug("pygame.mixer unavailable (%s), will use terminal bell", exc)
            return False

    def register_flash_callback(self, callback: callable) -> None:
        """Register a function to call for visual flash (e.g. Textual reactive update)."""
        self._flash_callback = callback

    async def alert(self, severity_level: int = 3) -> None:
        """
        Fire both sound and visual notifications for a new alert.
        severity_level 1–4 maps to number of bell repeats / tone urgency.
        """
        tasks = []
        if self._sound:
            tasks.append(self._play_sound(severity_level))
        if self._visual and self._flash_callback:
            tasks.append(self._trigger_flash())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _play_sound(self, severity_level: int) -> None:
        if self._pygame_available:
            await self._play_pygame_tone(severity_level)
        else:
            await self._play_terminal_bell(severity_level)

    async def _play_pygame_tone(self, severity_level: int) -> None:
        """Generate a simple beep tone via pygame. Pitch scales with severity."""
        try:
            import pygame.mixer
            import numpy as np
            import array

            freq = {1: 440, 2: 660, 3: 880, 4: 1100}.get(severity_level, 880)
            duration_ms = {1: 200, 2: 300, 3: 400, 4: 600}.get(severity_level, 400)
            sample_rate = 44100
            n_samples = int(sample_rate * duration_ms / 1000)

            # Generate sine wave
            import math
            samples = array.array("h", [
                int(32767 * math.sin(2 * math.pi * freq * t / sample_rate))
                for t in range(n_samples)
            ])

            sound = pygame.mixer.Sound(buffer=samples)

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, sound.play)
            await asyncio.sleep(duration_ms / 1000 + 0.05)

        except Exception as exc:
            logger.warning("pygame tone failed: %s — falling back to bell", exc)
            await self._play_terminal_bell(severity_level)

    async def _play_terminal_bell(self, severity_level: int) -> None:
        """Ring terminal bell N times based on severity."""
        rings = min(severity_level, 4)
        for i in range(rings):
            sys.stdout.write("\a")
            sys.stdout.flush()
            if i < rings - 1:
                await asyncio.sleep(0.3)

    async def _trigger_flash(self) -> None:
        try:
            result = self._flash_callback()
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:
            logger.warning("Visual flash callback failed: %s", exc)
