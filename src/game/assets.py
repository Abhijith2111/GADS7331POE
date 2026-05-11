"""Sprite + font loading with graceful fallbacks.

The game ships *without* bundled art so the marker can run it on a clean
clone without copyright concerns. Every asset has a generated fallback
that is procedurally drawn at startup, so the game looks deliberate even
when ``assets/sprites/`` is empty.

If real PNGs are dropped into ``assets/sprites/`` matching the persona's
``sprite`` field, they are used automatically.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any  # noqa: F401 — used by SoundLibrary cache type hint

import pygame


SPRITE_DIR = Path("assets") / "sprites"
FONT_DIR = Path("assets") / "fonts"
SFX_DIR = Path("assets") / "sfx"

NPC_SIZE = (220, 320)


# ---------------------------------------------------------------------------
# Sound effects (optional; missing files are silently ignored)
# ---------------------------------------------------------------------------
class SoundLibrary:
    """Lazy-loaded SFX. Looks in ``assets/sfx/``; missing files are no-ops.

    The game ships without bundled audio; if the player wants ambience, they
    can drop ``door.wav``, ``coin.wav`` and ``quest.wav`` into ``assets/sfx/``.
    """

    def __init__(self) -> None:
        self.enabled = False
        self._cache: dict[str, Any] = {}
        try:
            pygame.mixer.init()
            self.enabled = True
        except pygame.error:
            self.enabled = False

    def play(self, name: str) -> None:
        if not self.enabled:
            return
        if name not in self._cache:
            path = SFX_DIR / f"{name}.wav"
            if not path.exists():
                self._cache[name] = None
            else:
                try:
                    self._cache[name] = pygame.mixer.Sound(str(path))
                except pygame.error:
                    self._cache[name] = None
        sound = self._cache.get(name)
        if sound is not None:
            sound.play()


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------
def load_font(size: int, *, bold: bool = False) -> pygame.font.Font:
    """Load a bundled font if present, else the system default."""
    candidate = FONT_DIR / "main.ttf"
    if candidate.exists():
        font = pygame.font.Font(str(candidate), size)
    else:
        font = pygame.font.SysFont("georgia,serif", size, bold=bold)
    return font


# ---------------------------------------------------------------------------
# Sprite loading
# ---------------------------------------------------------------------------
def load_npc_sprite(persona: dict[str, Any]) -> pygame.Surface:
    """Return a sprite surface for ``persona``.

    Looks in ``assets/sprites/<persona['sprite']>`` first; if missing,
    builds a stylised silhouette from the persona's ``color_accent``.
    """
    name = persona.get("sprite", "")
    if name:
        path = SPRITE_DIR / name
        if path.exists():
            try:
                surf = pygame.image.load(str(path)).convert_alpha()
                return pygame.transform.smoothscale(surf, NPC_SIZE)
            except pygame.error:
                pass
    return _generate_silhouette(persona)


def _generate_silhouette(persona: dict[str, Any]) -> pygame.Surface:
    """Procedural fallback: a hooded figure tinted by the persona accent."""
    accent = tuple(persona.get("color_accent", [120, 90, 70]))
    surf = pygame.Surface(NPC_SIZE, pygame.SRCALPHA)
    w, h = NPC_SIZE

    body_color = (*accent, 255)
    shadow = (max(0, accent[0] - 40), max(0, accent[1] - 40), max(0, accent[2] - 40), 255)
    skin = (220, 195, 170, 255)

    # Shadow on the floor.
    pygame.draw.ellipse(surf, (0, 0, 0, 80), (w * 0.15, h * 0.92, w * 0.7, h * 0.06))

    # Cloak / body.
    body_pts = [
        (w * 0.5, h * 0.20),
        (w * 0.85, h * 0.55),
        (w * 0.92, h * 0.95),
        (w * 0.08, h * 0.95),
        (w * 0.15, h * 0.55),
    ]
    pygame.draw.polygon(surf, body_color, body_pts)
    pygame.draw.polygon(surf, shadow, body_pts, 4)

    # Hood opening.
    pygame.draw.ellipse(
        surf,
        shadow,
        (w * 0.28, h * 0.10, w * 0.44, h * 0.30),
    )
    pygame.draw.ellipse(
        surf,
        skin,
        (w * 0.34, h * 0.18, w * 0.32, h * 0.22),
    )

    # Subtle highlight strip down the cloak. Starts below the chin so
    # it never crosses the face.
    highlight = (
        min(255, accent[0] + 30),
        min(255, accent[1] + 30),
        min(255, accent[2] + 30),
        180,
    )
    pygame.draw.line(surf, highlight, (w * 0.5, h * 0.44), (w * 0.5, h * 0.92), 6)

    return surf


# ---------------------------------------------------------------------------
# Tavern background
# ---------------------------------------------------------------------------
def render_tavern_background(size: tuple[int, int]) -> pygame.Surface:
    """Procedural tavern interior — warm wood, hearth glow, subtle vignette."""
    surf = pygame.Surface(size)
    w, h = size

    # Vertical gradient floor-to-ceiling: warm wood lower, smoky upper.
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(40 + 35 * (1 - t))
        g = int(28 + 22 * (1 - t))
        b = int(22 + 18 * (1 - t))
        pygame.draw.line(surf, (r, g, b), (0, y), (w, y))

    # Wooden floorboards across the lower third.
    floor_top = int(h * 0.7)
    for y in range(floor_top, h, 18):
        pygame.draw.line(surf, (24, 16, 10), (0, y), (w, y), 2)
    for x in range(0, w, 90):
        pygame.draw.line(surf, (24, 16, 10), (x, floor_top), (x, h), 1)

    # Hearth glow on the right side.
    glow = pygame.Surface((w, h), pygame.SRCALPHA)
    for r in range(260, 0, -20):
        alpha = max(0, 60 - r // 6)
        pygame.draw.circle(
            glow,
            (255, 160, 80, alpha),
            (int(w * 0.85), int(h * 0.6)),
            r,
        )
    surf.blit(glow, (0, 0))

    # Counter line across the foreground.
    counter_y = int(h * 0.75)
    pygame.draw.rect(surf, (60, 38, 24), (0, counter_y, w, 14))
    pygame.draw.line(surf, (90, 60, 36), (0, counter_y), (w, counter_y), 2)

    # Vignette.
    vignette = pygame.Surface((w, h), pygame.SRCALPHA)
    for i in range(60):
        alpha = i * 2
        pygame.draw.rect(
            vignette,
            (0, 0, 0, alpha),
            (i, i, w - 2 * i, h - 2 * i),
            1,
        )
    surf.blit(vignette, (0, 0))

    return surf


# ---------------------------------------------------------------------------
# Subtle idle animation (a sine bob applied at draw time)
# ---------------------------------------------------------------------------
def idle_offset(time_s: float, amplitude: int = 4, period: float = 2.4) -> int:
    return int(math.sin(time_s * (2 * math.pi / period)) * amplitude)
