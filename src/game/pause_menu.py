"""In-game pause overlay: resume, quit, apply aspect ratio (same presets as main menu)."""

from __future__ import annotations

import pygame

from .assets import load_font
from .main_menu import ASPECT_OPTIONS
from .ui import HIGHLIGHT, INK_SOFT, PARCHMENT


class PauseMenu:
    """Fullscreen dim + centred panel. Call ``layout`` each time ``paused`` becomes true."""

    def __init__(self) -> None:
        self.title_font = load_font(32, bold=True)
        self.heading_font = load_font(19, bold=True)
        self.body_font = load_font(17)
        self.small_font = load_font(14)
        self._selected = 0
        self._panel_rect = pygame.Rect(0, 0, 560, 440)
        self._aspect_rects: list[tuple[pygame.Rect, int]] = []
        self._resume_rect = pygame.Rect(0, 0, 1, 1)
        self._quit_rect = pygame.Rect(0, 0, 1, 1)
        self._apply_rect = pygame.Rect(0, 0, 1, 1)

    def sync_selection_to_current(self, w: int, h: int) -> None:
        for i, opt in enumerate(ASPECT_OPTIONS):
            if opt.width == w and opt.height == h:
                self._selected = i
                return
        self._selected = 0

    def layout(self, sw: int, sh: int) -> None:
        pw = min(560, sw - 40)
        ph = min(460, sh - 40)
        px = (sw - pw) // 2
        py = (sh - ph) // 2
        self._panel_rect = pygame.Rect(px, py, pw, ph)

        self._aspect_rects.clear()
        bx = px + 20
        bw = pw - 40
        bh = 34
        y0 = py + 100
        for i, _opt in enumerate(ASPECT_OPTIONS):
            if y0 + i * (bh + 6) > py + ph - 120:
                break
            r = pygame.Rect(bx, y0 + i * (bh + 6), bw, bh)
            self._aspect_rects.append((r, i))

        foot_y = min(py + ph - 56, y0 + len(ASPECT_OPTIONS) * (bh + 6) + 16)
        foot_y = max(foot_y, py + ph - 56)
        cx = px + pw // 2
        self._resume_rect = pygame.Rect(cx - 232, foot_y, 150, 40)
        self._apply_rect = pygame.Rect(cx - 75, foot_y, 150, 40)
        self._quit_rect = pygame.Rect(cx + 82, foot_y, 150, 40)

    def handle_event(self, event: pygame.event.Event) -> str | None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return "resume"
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return "apply"
            if event.key == pygame.K_UP:
                self._selected = (self._selected - 1) % len(ASPECT_OPTIONS)
            elif event.key == pygame.K_DOWN:
                self._selected = (self._selected + 1) % len(ASPECT_OPTIONS)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if not self._panel_rect.collidepoint(mx, my):
                return "resume"
            for rect, idx in self._aspect_rects:
                if rect.collidepoint(mx, my):
                    self._selected = idx
                    break
            if self._resume_rect.collidepoint(mx, my):
                return "resume"
            if self._apply_rect.collidepoint(mx, my):
                return "apply"
            if self._quit_rect.collidepoint(mx, my):
                return "quit"
        return None

    def selected_size(self) -> tuple[int, int]:
        opt = ASPECT_OPTIONS[self._selected]
        return (opt.width, opt.height)

    def draw(self, surface: pygame.Surface) -> None:
        sw, sh = surface.get_size()
        veil = pygame.Surface((sw, sh), pygame.SRCALPHA)
        veil.fill((0, 0, 0, 165))
        surface.blit(veil, (0, 0))

        pr = self._panel_rect
        pygame.draw.rect(surface, (38, 26, 18), pr, border_radius=12)
        pygame.draw.rect(surface, HIGHLIGHT, pr, 3, border_radius=12)

        title = self.title_font.render("Paused", True, HIGHLIGHT)
        surface.blit(title, (pr.centerx - title.get_width() // 2, pr.top + 18))

        sub = self.body_font.render(
            "Window size (default is Full HD; pick what fits your monitor):",
            True,
            PARCHMENT,
        )
        surface.blit(sub, (pr.left + 20, pr.top + 58))

        cur = ASPECT_OPTIONS[self._selected]
        res = self.small_font.render(f"→ {cur.width} × {cur.height}", True, INK_SOFT)
        surface.blit(res, (pr.left + 20, pr.top + 80))

        mouse = pygame.mouse.get_pos()
        for rect, idx in self._aspect_rects:
            opt = ASPECT_OPTIONS[idx]
            picked = idx == self._selected
            hot = rect.collidepoint(mouse)
            bg = (68, 48, 32) if picked else ((54, 40, 28) if hot else (42, 30, 22))
            pygame.draw.rect(surface, bg, rect, border_radius=6)
            br = HIGHLIGHT if picked else (110, 82, 48)
            pygame.draw.rect(surface, br, rect, 2, border_radius=6)
            lbl = self.body_font.render(opt.label, True, PARCHMENT)
            surface.blit(lbl, (rect.left + 10, rect.centery - lbl.get_height() // 2))

        for label, rect, primary in (
            ("Resume", self._resume_rect, True),
            ("Apply", self._apply_rect, True),
            ("Quit", self._quit_rect, False),
        ):
            hot = rect.collidepoint(mouse)
            bg = (92, 64, 34) if primary else (52, 42, 32)
            if hot:
                bg = tuple(min(255, c + 20) for c in bg)
            pygame.draw.rect(surface, bg, rect, border_radius=8)
            pygame.draw.rect(surface, HIGHLIGHT, rect, 2, border_radius=8)
            surf = self.heading_font.render(label, True, PARCHMENT)
            surface.blit(
                surf,
                (
                    rect.centerx - surf.get_width() // 2,
                    rect.centery - surf.get_height() // 2,
                ),
            )

        hint = self.small_font.render(
            "Esc / click outside — resume   Enter — apply size   ↑↓ — choose preset",
            True,
            INK_SOFT,
        )
        surface.blit(hint, (pr.centerx - hint.get_width() // 2, pr.bottom - 36))
