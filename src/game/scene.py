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

    def set_npc(self, persona: dict[str, Any] | None) -> None:
        self._npc_persona = persona
        self._npc_surface = load_npc_sprite(persona) if persona else None

    def draw(self, surface: pygame.Surface) -> None:
        surface.blit(self.background, (0, 0))
        if self._npc_surface and self._npc_persona:
            sw, sh = self.screen_size
            sprite_w, sprite_h = self._npc_surface.get_size()
            x = sw // 2 - sprite_w // 2
            y = int(sh * 0.18) + idle_offset(time.monotonic() - self._t0)
            surface.blit(self._npc_surface, (x, y))

            # Persona name plate, centred under the sprite.
            label = self._npc_label_font.render(
                self._npc_persona["name"], True, (236, 222, 196)
            )
            label_bg = pygame.Surface(
                (label.get_width() + 24, label.get_height() + 12),
                pygame.SRCALPHA,
            )
            label_bg.fill((20, 14, 8, 200))
            pygame.draw.rect(label_bg, (180, 140, 70), label_bg.get_rect(), 2)
            label_x = sw // 2 - label_bg.get_width() // 2
            label_y = y + sprite_h + 6
            surface.blit(label_bg, (label_x, label_y))
            surface.blit(label, (label_x + 12, label_y + 6))
