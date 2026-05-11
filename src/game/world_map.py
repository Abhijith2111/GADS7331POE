"""World-map and location rendering scenes.

Two pygame scenes used while the player is *out* of the tavern:

- :class:`WorldMapScene` is a parchment-style overview of the four
  locations, drawn as 2x2 cards. Cards with active quests glow.
- :class:`LocationScene` is the in-location search view: procedural
  background by palette + pulsing hotspot dots + a small "Active
  quests" list in the corner.

Both scenes draw inside a caller-provided ``canvas_rect`` so they
co-operate with the persistent status bar / action panel from the
main game UI.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

import pygame

from .assets import load_font
from .world_map_data import LOCATIONS, get_location


# ---------------------------------------------------------------------------
# Palette table for procedural backgrounds
# ---------------------------------------------------------------------------
# Each palette is (sky_top, sky_bottom, ground_top, ground_bottom, accent).
PALETTES: dict[str, tuple[tuple[int, int, int], ...]] = {
    "stone":  ((24, 22, 26),  (38, 36, 42),  (32, 28, 30),  (18, 16, 18),  (200, 130, 60)),
    "warm":   ((60, 48, 38),  (110, 86, 56), (80, 60, 40),  (40, 30, 22),  (220, 180, 90)),
    "forest": ((28, 50, 60),  (48, 78, 70),  (40, 60, 38),  (18, 28, 18),  (200, 220, 140)),
    "cold":   ((28, 36, 54),  (50, 60, 86),  (38, 44, 56),  (18, 22, 32),  (160, 190, 230)),
}


def _grad_fill(surface: pygame.Surface, top: tuple, bottom: tuple, rect: pygame.Rect) -> None:
    """Linear vertical gradient between ``top`` and ``bottom`` colours."""
    h = max(1, rect.height)
    for y in range(h):
        t = y / (h - 1) if h > 1 else 0
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        pygame.draw.line(surface, (r, g, b), (rect.left, rect.top + y), (rect.right, rect.top + y))


# ---------------------------------------------------------------------------
# Per-palette decorative overlays
# ---------------------------------------------------------------------------
def _paint_mines(surface: pygame.Surface, rect: pygame.Rect, palette: tuple) -> None:
    accent = palette[4]
    # Jagged stone outlines along the sides.
    for x_anchor, mirror in ((rect.left, 1), (rect.right, -1)):
        pts = [(x_anchor, rect.top)]
        y = rect.top
        x = x_anchor
        rng = [0.06, 0.18, 0.04, 0.22, 0.10, 0.20, 0.06]
        for i, w in enumerate(rng):
            y += rect.height // (len(rng) + 1)
            x = x_anchor + mirror * int(rect.width * w)
            pts.append((x, y))
        pts.append((x_anchor, rect.bottom))
        pygame.draw.polygon(surface, (28, 24, 28), pts)
    # Torch glow on one side.
    cx = rect.left + int(rect.width * 0.85)
    cy = rect.top + int(rect.height * 0.35)
    glow = pygame.Surface(rect.size, pygame.SRCALPHA)
    for r in range(180, 0, -30):
        alpha = max(0, 50 - r // 6)
        pygame.draw.circle(glow, (*accent, alpha), (cx - rect.left, cy - rect.top), r)
    surface.blit(glow, rect.topleft)
    # Faint rail tracks.
    for y_frac in (0.86, 0.92):
        y = rect.top + int(rect.height * y_frac)
        pygame.draw.line(surface, (60, 50, 40), (rect.left + 60, y), (rect.right - 60, y), 2)


def _paint_town(surface: pygame.Surface, rect: pygame.Rect, palette: tuple) -> None:
    accent = palette[4]
    # Silhouette buildings along the horizon.
    base_y = rect.top + int(rect.height * 0.55)
    for i, (w_frac, h_frac, x_frac) in enumerate([
        (0.12, 0.18, 0.10),
        (0.16, 0.26, 0.24),
        (0.10, 0.16, 0.42),
        (0.20, 0.30, 0.56),
        (0.12, 0.20, 0.78),
        (0.10, 0.14, 0.90),
    ]):
        w = int(rect.width * w_frac)
        h = int(rect.height * h_frac)
        x = rect.left + int(rect.width * x_frac) - w // 2
        body = pygame.Rect(x, base_y - h, w, h)
        pygame.draw.rect(surface, (38, 28, 20), body)
        # Peaked roof.
        roof = [(x, base_y - h), (x + w, base_y - h), (x + w // 2, base_y - h - h // 3)]
        pygame.draw.polygon(surface, (52, 36, 24), roof)
        # Window glow on roughly half the buildings.
        if i % 2 == 0:
            pygame.draw.rect(
                surface,
                (*accent, 255),
                (x + w // 3, base_y - h + h // 3, w // 4, h // 5),
            )
    # Cobble line on the foreground.
    cobble_y = rect.top + int(rect.height * 0.78)
    pygame.draw.rect(surface, (50, 36, 22), (rect.left, cobble_y, rect.width, 8))


def _paint_outskirts(surface: pygame.Surface, rect: pygame.Rect, palette: tuple) -> None:
    accent = palette[4]
    # Distant trees: irregular ovals.
    for i, (x_frac, y_frac, w_frac) in enumerate([
        (0.08, 0.55, 0.10),
        (0.18, 0.50, 0.13),
        (0.30, 0.55, 0.11),
        (0.58, 0.52, 0.14),
        (0.70, 0.55, 0.10),
        (0.85, 0.50, 0.13),
    ]):
        cx = rect.left + int(rect.width * x_frac)
        cy = rect.top + int(rect.height * y_frac)
        w = int(rect.width * w_frac)
        h = int(w * 1.1)
        pygame.draw.ellipse(surface, (24, 42, 28), (cx - w // 2, cy - h, w, h * 2))
        pygame.draw.ellipse(surface, (40, 64, 38), (cx - w // 3, cy - h + 4, w // 2, h))
    # A winding path on the ground.
    path = []
    for i in range(10):
        t = i / 9
        x = rect.left + int(rect.width * (0.1 + 0.8 * t))
        y = rect.top + int(rect.height * (0.78 + 0.04 * math.sin(t * math.pi * 2)))
        path.append((x, y))
    pygame.draw.lines(surface, (140, 110, 70), False, path, 6)


def _paint_castle_hall(surface: pygame.Surface, rect: pygame.Rect, palette: tuple) -> None:
    accent = palette[4]
    # Two columns flanking the center.
    for x_frac in (0.18, 0.82):
        cx = rect.left + int(rect.width * x_frac)
        col_w = int(rect.width * 0.05)
        col_top = rect.top + int(rect.height * 0.15)
        col_h = int(rect.height * 0.65)
        col_rect = pygame.Rect(cx - col_w // 2, col_top, col_w, col_h)
        pygame.draw.rect(surface, (60, 64, 78), col_rect)
        # Capital
        pygame.draw.rect(
            surface, (90, 96, 110), (col_rect.left - 6, col_rect.top - 10, col_w + 12, 10)
        )
        # Base
        pygame.draw.rect(
            surface,
            (90, 96, 110),
            (col_rect.left - 6, col_rect.bottom, col_w + 12, 10),
        )
    # Banner stripe overhead.
    banner_y = rect.top + int(rect.height * 0.10)
    banner_rect = pygame.Rect(rect.left + int(rect.width * 0.30), banner_y, int(rect.width * 0.40), 50)
    pygame.draw.rect(surface, (90, 30, 40), banner_rect)
    pygame.draw.line(surface, accent, (banner_rect.left, banner_rect.bottom), (banner_rect.right, banner_rect.bottom), 3)
    # Throne silhouette at center.
    throne_w = int(rect.width * 0.10)
    throne_h = int(rect.height * 0.18)
    tx = rect.centerx - throne_w // 2
    ty = rect.top + int(rect.height * 0.45)
    pygame.draw.rect(surface, (40, 42, 56), (tx, ty, throne_w, throne_h))
    pygame.draw.rect(surface, (60, 64, 80), (tx - 6, ty - 10, throne_w + 12, 12))


PAINTERS = {
    "stone": _paint_mines,
    "warm": _paint_town,
    "forest": _paint_outskirts,
    "cold": _paint_castle_hall,
}


def render_location_background(palette_id: str, size: tuple[int, int]) -> pygame.Surface:
    """Return a procedural background surface for a location palette."""
    palette = PALETTES.get(palette_id, PALETTES["stone"])
    surf = pygame.Surface(size)
    rect = surf.get_rect()
    sky_rect = pygame.Rect(rect.left, rect.top, rect.width, int(rect.height * 0.55))
    ground_rect = pygame.Rect(rect.left, sky_rect.bottom, rect.width, rect.height - sky_rect.height)
    _grad_fill(surf, palette[0], palette[1], sky_rect)
    _grad_fill(surf, palette[2], palette[3], ground_rect)
    painter = PAINTERS.get(palette_id, _paint_mines)
    painter(surf, rect, palette)
    # Vignette.
    vignette = pygame.Surface(rect.size, pygame.SRCALPHA)
    for i in range(48):
        pygame.draw.rect(vignette, (0, 0, 0, i * 2), (i, i, rect.width - 2 * i, rect.height - 2 * i), 1)
    surf.blit(vignette, (0, 0))
    return surf


# ---------------------------------------------------------------------------
# WorldMapScene — 2x2 location cards
# ---------------------------------------------------------------------------
@dataclass
class _MapCard:
    location_id: str
    rect: pygame.Rect
    glowing: bool = False
    hot: bool = False


class WorldMapScene:
    """Choose-a-location screen.

    ``set_active_locations`` highlights cards that have quests pointing
    at them. ``hit_test(pos)`` returns the location id of the clicked
    card or ``None``.
    """

    def __init__(self, canvas_rect: pygame.Rect) -> None:
        self.rect = canvas_rect
        self.title_font = load_font(34, bold=True)
        self.card_title_font = load_font(22, bold=True)
        self.body_font = load_font(16)
        self.small_font = load_font(14)
        self._t0 = time.monotonic()
        self.cards: list[_MapCard] = []
        self._build_cards()
        self._active_set: set[str] = set()

    def _build_cards(self) -> None:
        # 2 columns x 2 rows, centred in the canvas with margins.
        pad = 24
        title_h = 80
        inner = pygame.Rect(
            self.rect.left + pad,
            self.rect.top + pad + title_h,
            self.rect.width - pad * 2,
            self.rect.height - pad * 2 - title_h,
        )
        gap = 20
        card_w = (inner.width - gap) // 2
        card_h = (inner.height - gap) // 2
        positions = [
            (inner.left, inner.top),
            (inner.left + card_w + gap, inner.top),
            (inner.left, inner.top + card_h + gap),
            (inner.left + card_w + gap, inner.top + card_h + gap),
        ]
        loc_ids = list(LOCATIONS.keys())
        for (x, y), loc_id in zip(positions, loc_ids):
            self.cards.append(_MapCard(location_id=loc_id, rect=pygame.Rect(x, y, card_w, card_h)))

    def set_active_locations(self, locations: set[str]) -> None:
        self._active_set = set(locations)
        for c in self.cards:
            c.glowing = c.location_id in self._active_set

    def handle_event(self, event: pygame.event.Event) -> str | None:
        if event.type == pygame.MOUSEMOTION:
            for c in self.cards:
                c.hot = c.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for c in self.cards:
                if c.rect.collidepoint(event.pos):
                    return c.location_id
        return None

    def draw(self, surface: pygame.Surface) -> None:
        # Parchment background.
        bg = pygame.Surface(self.rect.size)
        _grad_fill(
            bg, (78, 60, 38), (96, 72, 46), pygame.Rect(0, 0, self.rect.width, self.rect.height)
        )
        # Subtle stippling for "parchment" texture.
        for i in range(0, self.rect.width, 14):
            for j in range(0, self.rect.height, 18):
                if (i + j) % 36 == 0:
                    pygame.draw.circle(bg, (110, 84, 56), (i, j), 1)
        surface.blit(bg, self.rect.topleft)

        # Title.
        title = self.title_font.render("Leaving the Goblet", True, (236, 222, 196))
        surface.blit(
            title,
            (self.rect.centerx - title.get_width() // 2, self.rect.top + 20),
        )
        sub = self.body_font.render(
            "Choose a place to head out to.",
            True,
            (210, 188, 150),
        )
        surface.blit(sub, (self.rect.centerx - sub.get_width() // 2, self.rect.top + 60))

        # Cards.
        pulse = (math.sin((time.monotonic() - self._t0) * 3.0) + 1.0) / 2.0
        for c in self.cards:
            loc = LOCATIONS[c.location_id]
            card_bg = (54, 40, 28) if not c.hot else (74, 56, 38)
            border = (180, 140, 70) if c.glowing else (110, 84, 56)
            border_w = 4 if c.glowing else 2
            pygame.draw.rect(surface, card_bg, c.rect, border_radius=8)
            pygame.draw.rect(surface, border, c.rect, border_w, border_radius=8)

            # Glow ring if active.
            if c.glowing:
                glow_alpha = int(80 + 80 * pulse)
                glow = pygame.Surface(
                    (c.rect.width + 16, c.rect.height + 16), pygame.SRCALPHA
                )
                pygame.draw.rect(
                    glow,
                    (180, 140, 70, glow_alpha),
                    glow.get_rect(),
                    6,
                    border_radius=10,
                )
                surface.blit(glow, (c.rect.left - 8, c.rect.top - 8))

            # Icon (procedural glyph in top-left).
            self._draw_card_icon(surface, c, loc)

            # Title & blurb.
            title_surf = self.card_title_font.render(loc["name"], True, (236, 222, 196))
            surface.blit(title_surf, (c.rect.left + 80, c.rect.top + 16))
            blurb_surf = self.body_font.render(loc["blurb"], True, (210, 188, 150))
            surface.blit(blurb_surf, (c.rect.left + 80, c.rect.top + 50))

            # Active-quest hint.
            if c.glowing:
                hint = self.small_font.render(
                    "Active quest here", True, (220, 180, 90)
                )
            else:
                hint = self.small_font.render(
                    "Free exploration",
                    True,
                    (160, 130, 90),
                )
            surface.blit(hint, (c.rect.left + 16, c.rect.bottom - 26))

    def _draw_card_icon(
        self, surface: pygame.Surface, card: _MapCard, loc: dict[str, Any]
    ) -> None:
        cx = card.rect.left + 40
        cy = card.rect.top + 36
        palette_id = loc["palette"]
        if palette_id == "stone":
            # Pickaxe.
            pygame.draw.line(surface, (220, 200, 180), (cx - 18, cy + 8), (cx + 18, cy - 8), 4)
            pygame.draw.line(surface, (160, 130, 90), (cx - 4, cy + 14), (cx + 12, cy - 10), 5)
        elif palette_id == "warm":
            # House.
            pygame.draw.rect(surface, (220, 180, 110), (cx - 18, cy - 4, 36, 22))
            pygame.draw.polygon(
                surface,
                (200, 150, 80),
                [(cx - 22, cy - 4), (cx + 22, cy - 4), (cx, cy - 22)],
            )
        elif palette_id == "forest":
            # Tree.
            pygame.draw.polygon(
                surface,
                (90, 150, 80),
                [(cx, cy - 22), (cx - 18, cy + 14), (cx + 18, cy + 14)],
            )
            pygame.draw.rect(surface, (110, 80, 60), (cx - 3, cy + 14, 6, 8))
        elif palette_id == "cold":
            # Castle flag.
            pygame.draw.line(surface, (220, 200, 180), (cx - 4, cy - 22), (cx - 4, cy + 22), 3)
            pygame.draw.polygon(
                surface,
                (180, 60, 70),
                [(cx - 4, cy - 22), (cx + 18, cy - 14), (cx - 4, cy - 6)],
            )


# ---------------------------------------------------------------------------
# LocationScene — full-screen view of one location
# ---------------------------------------------------------------------------
@dataclass
class _Hotspot:
    id: str
    name: str
    cx: int
    cy: int


class LocationScene:
    """One location with clickable hotspots and an active-quest panel."""

    HOTSPOT_RADIUS = 26

    def __init__(self, canvas_rect: pygame.Rect) -> None:
        self.rect = canvas_rect
        self.title_font = load_font(28, bold=True)
        self.label_font = load_font(16, bold=True)
        self.body_font = load_font(16)
        self.small_font = load_font(14)
        self._t0 = time.monotonic()
        self._background: pygame.Surface | None = None
        self._location_id: str | None = None
        self._hotspots: list[_Hotspot] = []
        self._hover_id: str | None = None
        self._quests: list[dict[str, Any]] = []
        self._note: tuple[str, float] | None = None  # (text, born_at)

    def set_location(self, location_id: str) -> None:
        self._location_id = location_id
        loc = get_location(location_id)
        self._background = render_location_background(loc["palette"], self.rect.size)
        self._hotspots = []
        for h in loc["hotspots"]:
            cx = self.rect.left + int(self.rect.width * h["pos"][0])
            cy = self.rect.top + int(self.rect.height * h["pos"][1])
            self._hotspots.append(_Hotspot(id=h["id"], name=h["name"], cx=cx, cy=cy))

    def set_quests(self, quests: list[dict[str, Any]]) -> None:
        """Quests active *at this location*; shown in the side panel."""
        self._quests = list(quests)

    def show_note(self, text: str) -> None:
        self._note = (text, time.monotonic())

    def hit_test(self, pos: tuple[int, int]) -> str | None:
        """Return hotspot id under ``pos`` (within HOTSPOT_RADIUS) or None."""
        x, y = pos
        for h in self._hotspots:
            dx, dy = x - h.cx, y - h.cy
            if dx * dx + dy * dy <= self.HOTSPOT_RADIUS * self.HOTSPOT_RADIUS:
                return h.id
        return None

    def handle_event(self, event: pygame.event.Event) -> str | None:
        if event.type == pygame.MOUSEMOTION:
            self._hover_id = self.hit_test(event.pos)
            return None
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return self.hit_test(event.pos)
        return None

    def draw(self, surface: pygame.Surface) -> None:
        if self._background is None or self._location_id is None:
            return
        surface.blit(self._background, self.rect.topleft)

        loc = get_location(self._location_id)
        # Location title bar.
        title_surf = self.title_font.render(loc["name"], True, (236, 222, 196))
        title_bg = pygame.Surface(
            (title_surf.get_width() + 32, title_surf.get_height() + 14),
            pygame.SRCALPHA,
        )
        title_bg.fill((20, 14, 8, 200))
        pygame.draw.rect(title_bg, (180, 140, 70), title_bg.get_rect(), 2)
        surface.blit(title_bg, (self.rect.left + 20, self.rect.top + 16))
        surface.blit(
            title_surf,
            (self.rect.left + 36, self.rect.top + 16 + 7),
        )

        # Quest side panel (top-right of canvas).
        self._draw_quest_panel(surface)

        # Hotspots.
        pulse = (math.sin((time.monotonic() - self._t0) * 3.2) + 1.0) / 2.0
        for h in self._hotspots:
            self._draw_hotspot(surface, h, pulse)

        # Transient note ("nothing here.").
        if self._note is not None:
            text, born = self._note
            elapsed = time.monotonic() - born
            if elapsed > 2.4:
                self._note = None
            else:
                alpha = max(0, int(255 * (1.0 - elapsed / 2.4)))
                note_surf = self.body_font.render(text, True, (236, 222, 196))
                note_bg = pygame.Surface(
                    (note_surf.get_width() + 24, note_surf.get_height() + 12),
                    pygame.SRCALPHA,
                )
                note_bg.fill((20, 14, 8, min(220, alpha + 40)))
                pygame.draw.rect(note_bg, (180, 140, 70, alpha), note_bg.get_rect(), 2)
                note_surf.set_alpha(alpha)
                x = self.rect.centerx - note_bg.get_width() // 2
                y = self.rect.bottom - 80
                surface.blit(note_bg, (x, y))
                surface.blit(note_surf, (x + 12, y + 6))

    def _draw_hotspot(
        self, surface: pygame.Surface, h: _Hotspot, pulse: float
    ) -> None:
        # Outer pulse ring.
        ring_r = int(self.HOTSPOT_RADIUS + 6 + pulse * 6)
        ring_alpha = int(120 - pulse * 60)
        ring_surf = pygame.Surface((ring_r * 2 + 4, ring_r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(
            ring_surf,
            (236, 200, 120, ring_alpha),
            (ring_r + 2, ring_r + 2),
            ring_r,
            3,
        )
        surface.blit(ring_surf, (h.cx - ring_r - 2, h.cy - ring_r - 2))

        # Solid dot.
        pygame.draw.circle(surface, (240, 210, 130), (h.cx, h.cy), self.HOTSPOT_RADIUS - 6)
        pygame.draw.circle(surface, (120, 84, 30), (h.cx, h.cy), self.HOTSPOT_RADIUS - 6, 3)
        pygame.draw.circle(surface, (255, 240, 200), (h.cx - 4, h.cy - 6), 4)

        # Name label, only on hover or always-visible compact label.
        is_hover = self._hover_id == h.id
        label_surf = self.label_font.render(h.name, True, (20, 14, 8))
        pad_x, pad_y = 10, 6
        label_bg = pygame.Surface(
            (label_surf.get_width() + pad_x * 2, label_surf.get_height() + pad_y * 2),
            pygame.SRCALPHA,
        )
        bg_alpha = 230 if is_hover else 130
        label_bg.fill((236, 222, 196, bg_alpha))
        pygame.draw.rect(label_bg, (120, 84, 30), label_bg.get_rect(), 2)
        lx = h.cx - label_bg.get_width() // 2
        ly = h.cy + self.HOTSPOT_RADIUS + 6
        surface.blit(label_bg, (lx, ly))
        surface.blit(label_surf, (lx + pad_x, ly + pad_y))

    def _draw_quest_panel(self, surface: pygame.Surface) -> None:
        if not self._quests:
            return
        panel_w = 320
        x = self.rect.right - panel_w - 20
        y = self.rect.top + 16
        # Title.
        title = self.label_font.render("Quests at this location", True, (236, 222, 196))
        # Compute panel height.
        line_h = self.body_font.get_height() + 6
        body_h = sum(line_h for _ in self._quests) + 12
        panel_h = title.get_height() + 12 + body_h + 12
        bg = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        bg.fill((20, 14, 8, 200))
        pygame.draw.rect(bg, (180, 140, 70), bg.get_rect(), 2)
        surface.blit(bg, (x, y))
        surface.blit(title, (x + 12, y + 8))
        line_y = y + title.get_height() + 16
        for q in self._quests:
            line = f"- {q.get('title', '???')}"
            line_surf = self.body_font.render(line, True, (220, 200, 160))
            surface.blit(line_surf, (x + 12, line_y))
            line_y += line_h
