"""In-game pause overlay: resume, music volume, window size, main menu, quit.

Leaving the game (main menu or quit) always asks the player whether to save
first via a small confirmation overlay, so progress is never lost silently.
Buttons are ordered the way a normal game's pause screen reads: Resume first,
then the settings (volume + window size), then Main Menu, then Quit.
"""

from __future__ import annotations

from typing import Callable

import pygame

from .assets import load_font
from .main_menu import ASPECT_OPTIONS
from .ui import HIGHLIGHT, INK_SOFT, PARCHMENT, WARN


class PauseMenu:
    """Fullscreen dim + centred panel. Call ``layout`` each time ``paused`` becomes true."""

    def __init__(self) -> None:
        self.title_font = load_font(32, bold=True)
        self.heading_font = load_font(19, bold=True)
        self.body_font = load_font(17)
        self.small_font = load_font(14)
        self._selected = 0
        self._panel_rect = pygame.Rect(0, 0, 560, 560)
        self._aspect_rects: list[tuple[pygame.Rect, int]] = []
        self._resume_rect = pygame.Rect(0, 0, 1, 1)
        self._apply_rect = pygame.Rect(0, 0, 1, 1)
        self._menu_rect = pygame.Rect(0, 0, 1, 1)
        self._quit_rect = pygame.Rect(0, 0, 1, 1)

        # Music volume control.
        self.volume = 0.5
        self._volume_cb: Callable[[float, bool], None] | None = None
        self._dragging_volume = False
        self._vol_minus_rect = pygame.Rect(0, 0, 1, 1)
        self._vol_track_rect = pygame.Rect(0, 0, 1, 1)
        self._vol_plus_rect = pygame.Rect(0, 0, 1, 1)

        # Confirmation overlay state: None, "quit", or "menu".
        self._confirm: str | None = None
        self._confirm_panel_rect = pygame.Rect(0, 0, 1, 1)
        self._confirm_save_rect = pygame.Rect(0, 0, 1, 1)
        self._confirm_nosave_rect = pygame.Rect(0, 0, 1, 1)
        self._confirm_cancel_rect = pygame.Rect(0, 0, 1, 1)

    def reset(self) -> None:
        """Clear any in-progress confirmation. Call when (re)opening the menu."""
        self._confirm = None
        self._dragging_volume = False

    def open_confirm(self, kind: str) -> None:
        """Jump straight into the save-or-discard prompt (used by in-game Quit)."""
        self._confirm = kind

    def set_volume_controls(
        self, volume: float, callback: Callable[[float, bool], None]
    ) -> None:
        """Seed the slider with the live volume and a sink for changes.

        ``callback(volume, commit)`` is called live while adjusting; ``commit``
        is True only when the change should be persisted (click / drag-release).
        """
        self.volume = max(0.0, min(1.0, float(volume)))
        self._volume_cb = callback

    def sync_selection_to_current(self, w: int, h: int) -> None:
        for i, opt in enumerate(ASPECT_OPTIONS):
            if opt.width == w and opt.height == h:
                self._selected = i
                return
        self._selected = 0

    def layout(self, sw: int, sh: int) -> None:
        pw = min(560, sw - 40)
        ph = min(560, sh - 40)
        px = (sw - pw) // 2
        py = (sh - ph) // 2
        self._panel_rect = pygame.Rect(px, py, pw, ph)

        bx = px + 20
        bw = pw - 40

        # Volume row near the top.
        vy = py + 84
        self._vol_minus_rect = pygame.Rect(bx, vy, 36, 30)
        self._vol_track_rect = pygame.Rect(bx + 44, vy + 8, bw - 88, 14)
        self._vol_plus_rect = pygame.Rect(px + pw - 20 - 36, vy, 36, 30)

        # Window-size presets below the volume row.
        self._aspect_rects.clear()
        bh = 32
        y0 = py + 168
        for i, _opt in enumerate(ASPECT_OPTIONS):
            if y0 + i * (bh + 6) > py + ph - 120:
                break
            r = pygame.Rect(bx, y0 + i * (bh + 6), bw, bh)
            self._aspect_rects.append((r, i))

        # Footer row, ordered Resume -> Apply size -> Main Menu -> Quit.
        foot_y = py + ph - 58
        gap = 10
        inner = pw - 40
        btn_w = (inner - 3 * gap) // 4
        x = px + 20
        self._resume_rect = pygame.Rect(x, foot_y, btn_w, 42)
        x += btn_w + gap
        self._apply_rect = pygame.Rect(x, foot_y, btn_w, 42)
        x += btn_w + gap
        self._menu_rect = pygame.Rect(x, foot_y, btn_w, 42)
        x += btn_w + gap
        self._quit_rect = pygame.Rect(x, foot_y, btn_w, 42)

        # Confirmation overlay (centred independently of the main panel).
        cw = min(480, sw - 40)
        ch = 232
        cxp = (sw - cw) // 2
        cyp = (sh - ch) // 2
        self._confirm_panel_rect = pygame.Rect(cxp, cyp, cw, ch)
        cbw = cw - 40
        cbx = cxp + 20
        self._confirm_save_rect = pygame.Rect(cbx, cyp + 78, cbw, 42)
        self._confirm_nosave_rect = pygame.Rect(cbx, cyp + 128, cbw, 42)
        self._confirm_cancel_rect = pygame.Rect(cbx, cyp + 178, cbw, 42)

    def _volume_from_x(self, mx: int) -> float:
        tr = self._vol_track_rect
        if tr.width <= 0:
            return self.volume
        return max(0.0, min(1.0, (mx - tr.left) / tr.width))

    def _set_volume(self, vol: float, *, commit: bool) -> None:
        self.volume = max(0.0, min(1.0, vol))
        if self._volume_cb is not None:
            self._volume_cb(self.volume, commit)

    def handle_event(self, event: pygame.event.Event) -> str | None:
        if self._confirm is not None:
            return self._handle_confirm_event(event)

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return "resume"
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return "apply"
            if event.key == pygame.K_UP:
                self._selected = (self._selected - 1) % len(ASPECT_OPTIONS)
            elif event.key == pygame.K_DOWN:
                self._selected = (self._selected + 1) % len(ASPECT_OPTIONS)
            elif event.key == pygame.K_LEFT:
                self._set_volume(self.volume - 0.05, commit=True)
            elif event.key == pygame.K_RIGHT:
                self._set_volume(self.volume + 0.05, commit=True)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if not self._panel_rect.collidepoint(mx, my):
                return "resume"
            if self._vol_minus_rect.collidepoint(mx, my):
                self._set_volume(self.volume - 0.05, commit=True)
                return None
            if self._vol_plus_rect.collidepoint(mx, my):
                self._set_volume(self.volume + 0.05, commit=True)
                return None
            if self._vol_track_rect.collidepoint(mx, my):
                self._dragging_volume = True
                self._set_volume(self._volume_from_x(mx), commit=False)
                return None
            for rect, idx in self._aspect_rects:
                if rect.collidepoint(mx, my):
                    self._selected = idx
                    break
            if self._resume_rect.collidepoint(mx, my):
                return "resume"
            if self._apply_rect.collidepoint(mx, my):
                return "apply"
            if self._menu_rect.collidepoint(mx, my):
                self._confirm = "menu"
                return None
            if self._quit_rect.collidepoint(mx, my):
                self._confirm = "quit"
                return None
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._dragging_volume:
                self._dragging_volume = False
                self._set_volume(self.volume, commit=True)
        elif event.type == pygame.MOUSEMOTION and self._dragging_volume:
            self._set_volume(self._volume_from_x(event.pos[0]), commit=False)
        return None

    def _handle_confirm_event(self, event: pygame.event.Event) -> str | None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._confirm = None
            return None
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            leaving = self._confirm
            if self._confirm_save_rect.collidepoint(mx, my):
                self._confirm = None
                return "save_quit" if leaving == "quit" else "save_menu"
            if self._confirm_nosave_rect.collidepoint(mx, my):
                self._confirm = None
                return "quit_nosave" if leaving == "quit" else "menu_nosave"
            if self._confirm_cancel_rect.collidepoint(mx, my):
                self._confirm = None
                return None
            if not self._confirm_panel_rect.collidepoint(mx, my):
                self._confirm = None
                return None
        return None

    def selected_size(self) -> tuple[int, int]:
        opt = ASPECT_OPTIONS[self._selected]
        return (opt.width, opt.height)

    def draw(self, surface: pygame.Surface) -> None:
        sw, sh = surface.get_size()
        veil = pygame.Surface((sw, sh), pygame.SRCALPHA)
        veil.fill((0, 0, 0, 165))
        surface.blit(veil, (0, 0))

        if self._confirm is not None:
            self._draw_confirm(surface)
            return

        pr = self._panel_rect
        pygame.draw.rect(surface, (38, 26, 18), pr, border_radius=12)
        pygame.draw.rect(surface, HIGHLIGHT, pr, 3, border_radius=12)

        title = self.title_font.render("Paused", True, HIGHLIGHT)
        surface.blit(title, (pr.centerx - title.get_width() // 2, pr.top + 16))

        mouse = pygame.mouse.get_pos()

        # --- Music volume ---------------------------------------------
        vol_lbl = self.body_font.render(
            f"Music volume: {int(round(self.volume * 100))}%", True, PARCHMENT
        )
        surface.blit(vol_lbl, (pr.left + 20, self._vol_minus_rect.top - 24))
        for rect, label in (
            (self._vol_minus_rect, "-"),
            (self._vol_plus_rect, "+"),
        ):
            hot = rect.collidepoint(mouse)
            bg = (54, 40, 28) if hot else (42, 30, 22)
            pygame.draw.rect(surface, bg, rect, border_radius=4)
            pygame.draw.rect(surface, (110, 82, 48), rect, 2, border_radius=4)
            surf = self.heading_font.render(label, True, PARCHMENT)
            surface.blit(
                surf,
                (rect.centerx - surf.get_width() // 2, rect.centery - surf.get_height() // 2),
            )
        tr = self._vol_track_rect
        pygame.draw.rect(surface, (40, 30, 20), tr, border_radius=4)
        fill_w = max(4, int(tr.width * self.volume))
        pygame.draw.rect(
            surface,
            HIGHLIGHT,
            pygame.Rect(tr.left, tr.top, fill_w, tr.height),
            border_radius=4,
        )

        # --- Window size ----------------------------------------------
        sub = self.small_font.render(
            "Window size (default Full HD; pick what fits your monitor):",
            True,
            PARCHMENT,
        )
        surface.blit(sub, (pr.left + 20, pr.top + 142))

        for rect, idx in self._aspect_rects:
            opt = ASPECT_OPTIONS[idx]
            picked = idx == self._selected
            hot = rect.collidepoint(mouse)
            bg = (68, 48, 32) if picked else ((54, 40, 28) if hot else (42, 30, 22))
            pygame.draw.rect(surface, bg, rect, border_radius=6)
            br = HIGHLIGHT if picked else (110, 82, 48)
            pygame.draw.rect(surface, br, rect, 2, border_radius=6)
            lbl = self.body_font.render(
                f"{opt.label}  ({opt.width}\u00d7{opt.height})", True, PARCHMENT
            )
            surface.blit(lbl, (rect.left + 10, rect.centery - lbl.get_height() // 2))

        # --- Footer buttons (Resume / Apply / Main Menu / Quit) -------
        for label, rect, primary in (
            ("Resume", self._resume_rect, True),
            ("Apply size", self._apply_rect, True),
            ("Main Menu", self._menu_rect, False),
            ("Quit", self._quit_rect, False),
        ):
            hot = rect.collidepoint(mouse)
            bg = (92, 64, 34) if primary else (52, 42, 32)
            if hot:
                bg = tuple(min(255, c + 20) for c in bg)
            pygame.draw.rect(surface, bg, rect, border_radius=8)
            pygame.draw.rect(surface, HIGHLIGHT, rect, 2, border_radius=8)
            surf = self.body_font.render(label, True, PARCHMENT)
            surface.blit(
                surf,
                (
                    rect.centerx - surf.get_width() // 2,
                    rect.centery - surf.get_height() // 2,
                ),
            )

        hint = self.small_font.render(
            "Esc / click outside \u2014 resume   Enter \u2014 apply size   "
            "\u2191\u2193 size   \u2190\u2192 volume",
            True,
            INK_SOFT,
        )
        surface.blit(hint, (pr.centerx - hint.get_width() // 2, pr.bottom - 86))

    def _draw_confirm(self, surface: pygame.Surface) -> None:
        leaving = self._confirm
        pr = self._confirm_panel_rect
        pygame.draw.rect(surface, (38, 26, 18), pr, border_radius=12)
        pygame.draw.rect(surface, HIGHLIGHT, pr, 3, border_radius=12)

        title = self.heading_font.render("Save before leaving?", True, HIGHLIGHT)
        surface.blit(title, (pr.centerx - title.get_width() // 2, pr.top + 18))

        where = "the main menu" if leaving == "menu" else "desktop"
        msg = self.small_font.render(
            f"You are about to leave to {where}.",
            True,
            PARCHMENT,
        )
        surface.blit(msg, (pr.centerx - msg.get_width() // 2, pr.top + 48))

        if leaving == "quit":
            save_label = "Save & quit"
            nosave_label = "Quit without saving"
        else:
            save_label = "Save & exit to menu"
            nosave_label = "Exit without saving"

        mouse = pygame.mouse.get_pos()
        for label, rect, kind in (
            (save_label, self._confirm_save_rect, "primary"),
            (nosave_label, self._confirm_nosave_rect, "danger"),
            ("Cancel", self._confirm_cancel_rect, "neutral"),
        ):
            hot = rect.collidepoint(mouse)
            if kind == "primary":
                bg = (92, 64, 34)
            elif kind == "danger":
                bg = (96, 44, 32)
            else:
                bg = (52, 42, 32)
            if hot:
                bg = tuple(min(255, c + 20) for c in bg)
            pygame.draw.rect(surface, bg, rect, border_radius=8)
            border = WARN if kind == "danger" else HIGHLIGHT
            pygame.draw.rect(surface, border, rect, 2, border_radius=8)
            surf = self.body_font.render(label, True, PARCHMENT)
            surface.blit(
                surf,
                (
                    rect.centerx - surf.get_width() // 2,
                    rect.centery - surf.get_height() // 2,
                ),
            )
