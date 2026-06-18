"""Pre-game launcher: save slots, music volume, window size, new/continue."""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from .assets import MusicPlayer, load_font
from .info_screens import show_help_screen
from .save_slots import SAVE_SLOT_COUNT, SaveSlotSummary, all_slot_summaries, slot_has_save
from .settings import GameSettings
from .ui import HIGHLIGHT, INK_SOFT, PARCHMENT, WARN

MENU_WINDOW_SIZE = (960, 720)
MENU_DISPLAY_FLAGS = pygame.RESIZABLE

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
    AspectOption("Full HD 1920×1080", 1920, 1080),
    AspectOption("Balanced 1280×880", 1280, _BASE_H),
    AspectOption("16:9 widescreen", _even_w(int(round(_BASE_H * 16 / 9))), _BASE_H),
    AspectOption("16:10", _even_w(int(round(_BASE_H * 16 / 10))), _BASE_H),
    AspectOption("4:3", _even_w(int(round(_BASE_H * 4 / 3))), _BASE_H),
    AspectOption("21:9 ultrawide", _even_w(int(round(_BASE_H * 21 / 9))), _BASE_H),
)


@dataclass
class MenuResult:
    screen_size: tuple[int, int]
    save_slot: int
    new_game: bool
    music_volume: float


class MainMenu:
    """Block until the player picks a slot and starts or quits."""

    def __init__(self, clock: pygame.time.Clock, title: str) -> None:
        self.clock = clock
        self.title = title
        self.title_font = load_font(38, bold=True)
        self.heading_font = load_font(20, bold=True)
        self.body_font = load_font(17)
        self.small_font = load_font(14)
        self.settings = GameSettings.load()
        self._selected_slot = self.settings.last_slot
        self._aspect_index = 0
        for i, opt in enumerate(ASPECT_OPTIONS):
            if opt.width == self.settings.window_width and opt.height == self.settings.window_height:
                self._aspect_index = i
                break
        self._volume = self.settings.music_volume
        self._music = MusicPlayer()
        self._music.set_volume(self._volume)
        self._music.start()
        self._slot_rects: list[tuple[pygame.Rect, int]] = []
        self._aspect_rect = pygame.Rect(0, 0, 1, 1)
        self._vol_track_rect = pygame.Rect(0, 0, 1, 1)
        self._vol_minus_rect = pygame.Rect(0, 0, 1, 1)
        self._vol_plus_rect = pygame.Rect(0, 0, 1, 1)
        self._new_rect = pygame.Rect(0, 0, 1, 1)
        self._continue_rect = pygame.Rect(0, 0, 1, 1)
        self._help_rect = pygame.Rect(0, 0, 1, 1)
        self._quit_rect = pygame.Rect(0, 0, 1, 1)
        self._confirm_yes_rect = pygame.Rect(0, 0, 1, 1)
        self._confirm_no_rect = pygame.Rect(0, 0, 1, 1)
        self._dragging_volume = False
        self._pending_overwrite_slot: int | None = None

    def _layout(self, sw: int, sh: int) -> None:
        cx = sw // 2
        bw = min(520, sw - 80)
        x0 = cx - bw // 2
        y = 108
        self._slot_rects.clear()
        slot_h = 52
        for i in range(SAVE_SLOT_COUNT):
            r = pygame.Rect(x0, y + i * (slot_h + 8), bw, slot_h)
            self._slot_rects.append((r, i + 1))
        y += SAVE_SLOT_COUNT * (slot_h + 8) + 20

        self._vol_minus_rect = pygame.Rect(x0, y, 36, 32)
        self._vol_track_rect = pygame.Rect(x0 + 44, y + 10, bw - 88, 12)
        self._vol_plus_rect = pygame.Rect(x0 + bw - 36, y, 36, 32)
        y += 44

        self._aspect_rect = pygame.Rect(x0, y, bw, 34)
        y += 50

        btn_w = (bw - 12) // 2
        self._new_rect = pygame.Rect(x0, y, btn_w, 42)
        self._continue_rect = pygame.Rect(x0 + btn_w + 12, y, btn_w, 42)
        y += 52
        self._help_rect = pygame.Rect(x0, y, btn_w, 40)
        self._quit_rect = pygame.Rect(x0 + btn_w + 12, y, btn_w, 40)

        cy = sh // 2
        self._confirm_yes_rect = pygame.Rect(cx - 210, cy + 40, 180, 40)
        self._confirm_no_rect = pygame.Rect(cx + 30, cy + 40, 180, 40)

    def _slot_label(self, summary: SaveSlotSummary) -> str:
        if not summary.exists:
            return "Empty — New Game available"
        return (
            f"Gold: {summary.gold}  |  Quests: {summary.active_quests}  |  "
            f"Memory: {summary.rumour_memory}  |  Patrons served: {summary.served_count}"
        )

    def _volume_from_x(self, mx: int) -> float:
        tr = self._vol_track_rect
        if tr.width <= 0:
            return self._volume
        t = (mx - tr.left) / tr.width
        return max(0.0, min(1.0, t))

    def _set_volume(self, vol: float) -> None:
        self._volume = max(0.0, min(1.0, vol))
        self._music.set_volume(self._volume)

    def _finish(self, *, new_game: bool) -> MenuResult:
        opt = ASPECT_OPTIONS[self._aspect_index]
        self.settings.music_volume = self._volume
        self.settings.window_width = opt.width
        self.settings.window_height = opt.height
        self.settings.last_slot = self._selected_slot
        self.settings.save()
        self._music.dispose()
        return MenuResult(
            screen_size=(opt.width, opt.height),
            save_slot=self._selected_slot,
            new_game=new_game,
            music_volume=self._volume,
        )

    def _try_new_game(self) -> MenuResult | None:
        if slot_has_save(self._selected_slot):
            self._pending_overwrite_slot = self._selected_slot
            return None
        return self._finish(new_game=True)

    def run(self) -> MenuResult | None:
        sw, sh = MENU_WINDOW_SIZE
        screen = pygame.display.set_mode(MENU_WINDOW_SIZE, MENU_DISPLAY_FLAGS)
        self._layout(sw, sh)
        summaries = all_slot_summaries()

        running = True
        result: MenuResult | None = None

        while running:
            _dt = self.clock.tick(60) / 1000.0
            summaries = all_slot_summaries()
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

                if self._pending_overwrite_slot is not None:
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            self._pending_overwrite_slot = None
                        elif event.key in (pygame.K_RETURN, pygame.K_y):
                            result = self._finish(new_game=True)
                            running = False
                        elif event.key == pygame.K_n:
                            self._pending_overwrite_slot = None
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        mx, my = event.pos
                        if self._confirm_yes_rect.collidepoint(mx, my):
                            result = self._finish(new_game=True)
                            running = False
                        elif self._confirm_no_rect.collidepoint(mx, my):
                            self._pending_overwrite_slot = None
                    continue

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                        break
                    if event.key in (pygame.K_F1, pygame.K_h):
                        if show_help_screen(self.clock) == "quit":
                            running = False
                            break
                        surf = pygame.display.get_surface()
                        sw, sh = surf.get_size()
                        screen = pygame.display.set_mode((sw, sh), MENU_DISPLAY_FLAGS)
                        self._layout(sw, sh)
                        continue
                    if event.key == pygame.K_UP:
                        self._aspect_index = (self._aspect_index - 1) % len(ASPECT_OPTIONS)
                    if event.key == pygame.K_DOWN:
                        self._aspect_index = (self._aspect_index + 1) % len(ASPECT_OPTIONS)
                    if event.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                        self._selected_slot = event.key - pygame.K_0
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = event.pos
                    for rect, slot in self._slot_rects:
                        if rect.collidepoint(mx, my):
                            self._selected_slot = slot
                            break
                    if self._vol_minus_rect.collidepoint(mx, my):
                        self._set_volume(self._volume - 0.05)
                    elif self._vol_plus_rect.collidepoint(mx, my):
                        self._set_volume(self._volume + 0.05)
                    elif self._vol_track_rect.collidepoint(mx, my):
                        self._dragging_volume = True
                        self._set_volume(self._volume_from_x(mx))
                    elif self._aspect_rect.collidepoint(mx, my):
                        self._aspect_index = (self._aspect_index + 1) % len(ASPECT_OPTIONS)
                    elif self._new_rect.collidepoint(mx, my):
                        picked = self._try_new_game()
                        if picked is not None:
                            result = picked
                            running = False
                    elif self._continue_rect.collidepoint(mx, my):
                        if slot_has_save(self._selected_slot):
                            result = self._finish(new_game=False)
                            running = False
                    elif self._help_rect.collidepoint(mx, my):
                        if show_help_screen(self.clock) == "quit":
                            running = False
                        else:
                            surf = pygame.display.get_surface()
                            sw, sh = surf.get_size()
                            screen = pygame.display.set_mode((sw, sh), MENU_DISPLAY_FLAGS)
                            self._layout(sw, sh)
                    elif self._quit_rect.collidepoint(mx, my):
                        running = False
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    self._dragging_volume = False
                elif event.type == pygame.MOUSEMOTION and self._dragging_volume:
                    self._set_volume(self._volume_from_x(event.pos[0]))

            screen.fill((18, 12, 8))
            tit = self.title_font.render(self.title, True, HIGHLIGHT)
            screen.blit(tit, (sw // 2 - tit.get_width() // 2, 28))
            sub = self.body_font.render("Select a save slot", True, PARCHMENT)
            screen.blit(sub, (sw // 2 - sub.get_width() // 2, 78))

            mouse = pygame.mouse.get_pos()
            for rect, slot in self._slot_rects:
                summary = summaries[slot - 1]
                picked = slot == self._selected_slot
                hot = rect.collidepoint(mouse)
                bg = (72, 52, 32) if picked else ((58, 42, 26) if hot else (44, 32, 22))
                pygame.draw.rect(screen, bg, rect, border_radius=6)
                border_col = HIGHLIGHT if picked else (120, 90, 50)
                pygame.draw.rect(screen, border_col, rect, 2, border_radius=6)
                head = self.heading_font.render(f"Slot {slot}", True, PARCHMENT)
                screen.blit(head, (rect.left + 12, rect.top + 6))
                detail = self.small_font.render(self._slot_label(summary), True, INK_SOFT)
                screen.blit(detail, (rect.left + 12, rect.top + 28))

            vol_lbl = self.body_font.render(
                f"Music volume: {int(round(self._volume * 100))}%",
                True,
                PARCHMENT,
            )
            screen.blit(vol_lbl, (self._vol_minus_rect.left, self._vol_minus_rect.top - 22))
            for rect, label in (
                (self._vol_minus_rect, "-"),
                (self._vol_plus_rect, "+"),
            ):
                hot = rect.collidepoint(mouse)
                bg = (58, 42, 26) if hot else (44, 32, 22)
                pygame.draw.rect(screen, bg, rect, border_radius=4)
                surf = self.heading_font.render(label, True, PARCHMENT)
                screen.blit(
                    surf,
                    (rect.centerx - surf.get_width() // 2, rect.centery - surf.get_height() // 2),
                )
            tr = self._vol_track_rect
            pygame.draw.rect(screen, (40, 30, 20), tr, border_radius=4)
            fill_w = max(4, int(tr.width * self._volume))
            pygame.draw.rect(
                screen,
                HIGHLIGHT,
                pygame.Rect(tr.left, tr.top, fill_w, tr.height),
                border_radius=4,
            )

            ar = self._aspect_rect
            hot = ar.collidepoint(mouse)
            pygame.draw.rect(screen, (58, 42, 26) if hot else (44, 32, 22), ar, border_radius=6)
            pygame.draw.rect(screen, (120, 90, 50), ar, 2, border_radius=6)
            asp = ASPECT_OPTIONS[self._aspect_index]
            asp_txt = self.body_font.render(
                f"Window: {asp.label} ({asp.width}×{asp.height}) — click to cycle",
                True,
                PARCHMENT,
            )
            screen.blit(asp_txt, (ar.left + 12, ar.centery - asp_txt.get_height() // 2))

            can_continue = slot_has_save(self._selected_slot)
            for rect, label, enabled, primary in (
                (self._new_rect, "New Game", True, True),
                (self._continue_rect, "Continue", can_continue, False),
            ):
                hot = rect.collidepoint(mouse) and enabled
                if not enabled:
                    bg = (36, 28, 22)
                    col = INK_SOFT
                else:
                    bg = (100, 70, 36) if primary else (58, 42, 26)
                    if hot:
                        bg = tuple(min(255, c + 25) for c in bg)
                    col = PARCHMENT
                pygame.draw.rect(screen, bg, rect, border_radius=8)
                if enabled:
                    pygame.draw.rect(screen, HIGHLIGHT, rect, 2, border_radius=8)
                surf = self.heading_font.render(label, True, col)
                screen.blit(
                    surf,
                    (rect.centerx - surf.get_width() // 2, rect.centery - surf.get_height() // 2),
                )

            for rect, label in (
                (self._help_rect, "Help"),
                (self._quit_rect, "Quit"),
            ):
                hot = rect.collidepoint(mouse)
                bg = (50, 40, 30)
                if hot:
                    bg = tuple(min(255, c + 25) for c in bg)
                pygame.draw.rect(screen, bg, rect, border_radius=8)
                pygame.draw.rect(screen, HIGHLIGHT, rect, 2, border_radius=8)
                surf = self.heading_font.render(label, True, PARCHMENT)
                screen.blit(
                    surf,
                    (
                        rect.centerx - surf.get_width() // 2,
                        rect.centery - surf.get_height() // 2,
                    ),
                )

            if self._pending_overwrite_slot is not None:
                overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 160))
                screen.blit(overlay, (0, 0))
                msg = (
                    f"Overwrite slot {self._pending_overwrite_slot}? "
                    "This cannot be undone."
                )
                warn = self.heading_font.render(msg, True, WARN)
                screen.blit(warn, (sw // 2 - warn.get_width() // 2, sh // 2 - 20))
                for rect, label in (
                    (self._confirm_yes_rect, "Yes, overwrite"),
                    (self._confirm_no_rect, "Cancel"),
                ):
                    hot = rect.collidepoint(mouse)
                    bg = (100, 70, 36) if hot else (58, 42, 26)
                    pygame.draw.rect(screen, bg, rect, border_radius=6)
                    surf = self.body_font.render(label, True, PARCHMENT)
                    screen.blit(
                        surf,
                        (rect.centerx - surf.get_width() // 2, rect.centery - surf.get_height() // 2),
                    )

            hint = self.small_font.render(
                "1/2/3 select slot   New Game / Continue   F1 help   Esc quit",
                True,
                INK_SOFT,
            )
            screen.blit(hint, (sw // 2 - hint.get_width() // 2, sh - 28))

            pygame.display.flip()

        if result is None:
            self._music.dispose()
        return result
