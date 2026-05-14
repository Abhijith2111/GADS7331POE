"""Pre-game menu: title, aspect ratio presets, play or quit."""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from .assets import load_font
from .ui import HIGHLIGHT, INK_SOFT, PARCHMENT

MENU_WINDOW_SIZE = (960, 640)
MENU_DISPLAY_FLAGS = pygame.RESIZABLE

# Shared vertical resolution for compact presets (taller screens use explicit WxH).
_BASE_H = 880


def _even_w(w: int) -> int:
    w = max(704, w)
    return w - (w % 2)


@dataclass(frozen=True)
class AspectOption:
    label: str
    width: int
    height: int


ASPECT_OPTIONS: tuple[AspectOption, ...] = (
    AspectOption("Full HD 1920×1080 (recommended)", 1920, 1080),
    AspectOption("Balanced 1280×880", 1280, _BASE_H),
    AspectOption("16:9 widescreen (1564×880)", _even_w(int(round(_BASE_H * 16 / 9))), _BASE_H),
    AspectOption("16:10", _even_w(int(round(_BASE_H * 16 / 10))), _BASE_H),
    AspectOption("4:3", _even_w(int(round(_BASE_H * 4 / 3))), _BASE_H),
    AspectOption("21:9 ultrawide", _even_w(int(round(_BASE_H * 21 / 9))), _BASE_H),
)


class MainMenu:
    """Block until the player picks a resolution and Play, or quits."""

    def __init__(self, clock: pygame.time.Clock, title: str) -> None:
        self.clock = clock
        self.title = title
        self.title_font = load_font(40, bold=True)
        self.heading_font = load_font(22, bold=True)
        self.body_font = load_font(18)
        self.small_font = load_font(16)
        self._selected = 0
        self._aspect_buttons: list[tuple[pygame.Rect, int]] = []
        self._play_rect = pygame.Rect(0, 0, 200, 44)
        self._quit_rect = pygame.Rect(0, 0, 200, 44)

    def _layout(self, sw: int, sh: int) -> None:
        cx = sw // 2
        y = 140
        self._aspect_buttons.clear()
        bw, bh = 420, 36
        for i, _opt in enumerate(ASPECT_OPTIONS):
            r = pygame.Rect(cx - bw // 2, y + i * (bh + 8), bw, bh)
            self._aspect_buttons.append((r, i))
        y0 = y + len(ASPECT_OPTIONS) * (bh + 8) + 36
        self._play_rect = pygame.Rect(cx - 210, y0, 200, 44)
        self._quit_rect = pygame.Rect(cx + 10, y0, 200, 44)

    def run(self) -> tuple[int, int] | None:
        """Return ``(width, height)`` for the game, or ``None`` if the user quits."""
        sw, sh = MENU_WINDOW_SIZE
        screen = pygame.display.set_mode(MENU_WINDOW_SIZE, MENU_DISPLAY_FLAGS)
        self._layout(sw, sh)

        running = True
        result: tuple[int, int] | None = None

        while running:
            _dt = self.clock.tick(60) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    break
                if event.type == pygame.VIDEORESIZE:
                    if event.w < 320 or event.h < 240:
                        continue
                    sw = max(640, min(event.w, 7680))
                    sh = max(480, min(event.h, 4320))
                    screen = pygame.display.set_mode((sw, sh), MENU_DISPLAY_FLAGS)
                    self._layout(sw, sh)
                    continue
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                        break
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        opt = ASPECT_OPTIONS[self._selected]
                        result = (opt.width, opt.height)
                        running = False
                        break
                    if event.key == pygame.K_UP:
                        self._selected = (self._selected - 1) % len(ASPECT_OPTIONS)
                    if event.key == pygame.K_DOWN:
                        self._selected = (self._selected + 1) % len(ASPECT_OPTIONS)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = event.pos
                    for rect, idx in self._aspect_buttons:
                        if rect.collidepoint(mx, my):
                            self._selected = idx
                            break
                    if self._play_rect.collidepoint(mx, my):
                        opt = ASPECT_OPTIONS[self._selected]
                        result = (opt.width, opt.height)
                        running = False
                    elif self._quit_rect.collidepoint(mx, my):
                        running = False

            screen.fill((18, 12, 8))
            tit = self.title_font.render(self.title, True, HIGHLIGHT)
            screen.blit(tit, (sw // 2 - tit.get_width() // 2, 36))
            sub = self.body_font.render(
                "Choose window aspect ratio, then Play.",
                True,
                PARCHMENT,
            )
            screen.blit(sub, (sw // 2 - sub.get_width() // 2, 92))

            cur = ASPECT_OPTIONS[self._selected]
            res_line = f"Game window: {cur.width} × {cur.height}"
            res_surf = self.small_font.render(res_line, True, INK_SOFT)
            screen.blit(res_surf, (sw // 2 - res_surf.get_width() // 2, 118))

            mouse = pygame.mouse.get_pos()
            for rect, idx in self._aspect_buttons:
                opt = ASPECT_OPTIONS[idx]
                picked = idx == self._selected
                hot = rect.collidepoint(mouse)
                bg = (72, 52, 32) if picked else ((58, 42, 26) if hot else (44, 32, 22))
                pygame.draw.rect(screen, bg, rect, border_radius=6)
                border_col = HIGHLIGHT if picked else (120, 90, 50)
                pygame.draw.rect(screen, border_col, rect, 2, border_radius=6)
                lbl = self.body_font.render(opt.label, True, PARCHMENT)
                screen.blit(lbl, (rect.left + 14, rect.centery - lbl.get_height() // 2))

            for label, rect, primary in (
                ("Play", self._play_rect, True),
                ("Quit", self._quit_rect, False),
            ):
                hot = rect.collidepoint(mouse)
                bg = (100, 70, 36) if primary else (50, 40, 30)
                if hot:
                    bg = tuple(min(255, c + 25) for c in bg)
                pygame.draw.rect(screen, bg, rect, border_radius=8)
                pygame.draw.rect(screen, HIGHLIGHT, rect, 2, border_radius=8)
                surf = self.heading_font.render(label, True, PARCHMENT)
                screen.blit(
                    surf,
                    (rect.centerx - surf.get_width() // 2, rect.centery - surf.get_height() // 2),
                )

            hint = self.small_font.render(
                "↑/↓ or click to select   Enter/Play to start   Esc/Quit to exit",
                True,
                INK_SOFT,
            )
            screen.blit(hint, (sw // 2 - hint.get_width() // 2, sh - 32))

            pygame.display.flip()

        return result
