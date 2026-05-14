"""Top-level scene composition: tavern background + the active NPC."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import pygame

from .assets import idle_offset, load_font, load_npc_sprite, render_tavern_background


@dataclass
class TavernScene:
    """Owns the procedural tavern background and the current NPC sprite.

    Keeping it small means the main loop can swap personas mid-game by
    calling ``set_npc(persona)`` without rebuilding state.
    """

    screen_size: tuple[int, int]

    def __post_init__(self) -> None:
        self.background = render_tavern_background(self.screen_size)
        self._npc_persona: dict[str, Any] | None = None
        self._npc_surface: pygame.Surface | None = None
        self._npc_label_font = load_font(22, bold=True)
        self._t0 = time.monotonic()
        # Where the bottom of the NPC name plate should land. Set by
        # the main game once the dialogue box rect is known so the NPC
        # always hovers just above the chat panel.
        self._floor_y: int | None = None

    def set_npc(self, persona: dict[str, Any] | None) -> None:
        self._npc_persona = persona
        self._npc_surface = load_npc_sprite(persona) if persona else None

    def set_floor_y(self, y: int) -> None:
        """Pin the bottom of the NPC name plate to ``y`` (screen pixels)."""
        self._floor_y = y

    def set_screen_size(self, size: tuple[int, int]) -> None:
        """Rebuild the tavern backdrop for a new window size."""
        self.screen_size = size
        self.background = render_tavern_background(size)

    def draw(self, surface: pygame.Surface) -> None:
        surface.blit(self.background, (0, 0))
        if not (self._npc_surface and self._npc_persona):
            return

        sw, sh = self.screen_size
        sprite_w, sprite_h = self._npc_surface.get_size()

        label = self._npc_label_font.render(
            self._npc_persona["name"], True, (236, 222, 196)
        )
        label_w = label.get_width() + 24
        label_h = label.get_height() + 12
        gap_sprite_to_label = 6
        bob = idle_offset(time.monotonic() - self._t0)

        # Anchor the bottom of the name plate just above the dialogue
        # box (or at the screen's lower-third if no floor was set).
        floor_y = self._floor_y if self._floor_y is not None else int(sh * 0.78)
        label_y = floor_y - label_h
        sprite_y = label_y - gap_sprite_to_label - sprite_h + bob

        x = sw // 2 - sprite_w // 2
        surface.blit(self._npc_surface, (x, sprite_y))

        label_bg = pygame.Surface((label_w, label_h), pygame.SRCALPHA)
        label_bg.fill((20, 14, 8, 200))
        pygame.draw.rect(label_bg, (180, 140, 70), label_bg.get_rect(), 2)
        label_x = sw // 2 - label_w // 2
        surface.blit(label_bg, (label_x, label_y))
        surface.blit(label, (label_x + 12, label_y + 6))
