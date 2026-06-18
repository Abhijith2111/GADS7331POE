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
        # Options overlay (music volume + window size live here now).
        self._showing_options = False
        self._options_rect = pygame.Rect(0, 0, 1, 1)
        self._options_panel_rect = pygame.Rect(0, 0, 1, 1)
        self._options_back_rect = pygame.Rect(0, 0, 1, 1)
        # Window-size picker overlay (opened from the Window size button).
        self._choosing_aspect = False
        self._aspect_panel_rect = pygame.Rect(0, 0, 1, 1)
        self._aspect_option_rects: list[tuple[pygame.Rect, int]] = []
        self._aspect_back_rect = pygame.Rect(0, 0, 1, 1)

    def _layout(self, sw: int, sh: int) -> None:
        cx = sw // 2
        bw = min(520, sw - 80)
        x0 = cx - bw // 2
        y = 104
        self._slot_rects.clear()
        slot_h = 50
        for i in range(SAVE_SLOT_COUNT):
            r = pygame.Rect(x0, y + i * (slot_h + 8), bw, slot_h)
            self._slot_rects.append((r, i + 1))
        y += SAVE_SLOT_COUNT * (slot_h + 8) + 16

        # Primary actions first, the way a normal game's menu reads.
        btn_w = (bw - 12) // 2
        self._new_rect = pygame.Rect(x0, y, btn_w, 44)
        self._continue_rect = pygame.Rect(x0 + btn_w + 12, y, btn_w, 44)
        y += 56

        # Options button (opens music volume + window size).
        self._options_rect = pygame.Rect(x0, y, bw, 42)
        y += 54

        # Help then Quit at the bottom.
        self._help_rect = pygame.Rect(x0, y, btn_w, 40)
        self._quit_rect = pygame.Rect(x0 + btn_w + 12, y, btn_w, 40)

        cy = sh // 2
        self._confirm_yes_rect = pygame.Rect(cx - 210, cy + 40, 180, 40)
        self._confirm_no_rect = pygame.Rect(cx + 30, cy + 40, 180, 40)

        # Options overlay panel (music volume slider + window-size button).
        opw = min(480, sw - 60)
        oph = min(300, sh - 60)
        opx = (sw - opw) // 2
        opy = (sh - oph) // 2
        self._options_panel_rect = pygame.Rect(opx, opy, opw, oph)
        self._vol_minus_rect = pygame.Rect(opx + 20, opy + 96, 36, 30)
        self._vol_track_rect = pygame.Rect(opx + 64, opy + 104, opw - 128, 14)
        self._vol_plus_rect = pygame.Rect(opx + opw - 20 - 36, opy + 96, 36, 30)
        self._aspect_rect = pygame.Rect(opx + 20, opy + 152, opw - 40, 40)
        self._options_back_rect = pygame.Rect(opx + opw - 140, opy + oph - 52, 120, 38)

        # Window-size picker overlay (centred, lists every preset).
        n = len(ASPECT_OPTIONS)
        opt_h = 40
        opt_gap = 6
        apw = min(560, sw - 60)
        aph = min(110 + n * (opt_h + opt_gap) + 16, sh - 40)
        apx = (sw - apw) // 2
        apy = (sh - aph) // 2
        self._aspect_panel_rect = pygame.Rect(apx, apy, apw, aph)
        self._aspect_option_rects = []
        oy = apy + 64
        for i in range(n):
            r = pygame.Rect(apx + 20, oy + i * (opt_h + opt_gap), apw - 40, opt_h)
            self._aspect_option_rects.append((r, i))
        self._aspect_back_rect = pygame.Rect(apx + apw - 140, apy + aph - 50, 120, 38)

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

    def _draw_options(self, screen: pygame.Surface, mouse: tuple[int, int]) -> None:
        sw, sh = screen.get_size()
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        screen.blit(overlay, (0, 0))

        pr = self._options_panel_rect
        pygame.draw.rect(screen, (38, 26, 18), pr, border_radius=12)
        pygame.draw.rect(screen, HIGHLIGHT, pr, 3, border_radius=12)

        title = self.heading_font.render("Options", True, HIGHLIGHT)
        screen.blit(title, (pr.centerx - title.get_width() // 2, pr.top + 18))

        # Music volume.
        vol_lbl = self.body_font.render(
            f"Music volume: {int(round(self._volume * 100))}%", True, PARCHMENT
        )
        screen.blit(vol_lbl, (pr.left + 20, self._vol_minus_rect.top - 26))
        for rect, label in ((self._vol_minus_rect, "-"), (self._vol_plus_rect, "+")):
            hot = rect.collidepoint(mouse)
            bg = (58, 42, 26) if hot else (44, 32, 22)
            pygame.draw.rect(screen, bg, rect, border_radius=4)
            pygame.draw.rect(screen, (110, 82, 48), rect, 2, border_radius=4)
            surf = self.heading_font.render(label, True, PARCHMENT)
            screen.blit(
                surf,
                (rect.centerx - surf.get_width() // 2, rect.centery - surf.get_height() // 2),
            )
        tr = self._vol_track_rect
        pygame.draw.rect(screen, (40, 30, 20), tr, border_radius=4)
        fill_w = max(4, int(tr.width * self._volume))
        pygame.draw.rect(
            screen, HIGHLIGHT, pygame.Rect(tr.left, tr.top, fill_w, tr.height), border_radius=4
        )

        # Window size button.
        ar = self._aspect_rect
        hot = ar.collidepoint(mouse)
        pygame.draw.rect(screen, (58, 42, 26) if hot else (44, 32, 22), ar, border_radius=6)
        pygame.draw.rect(screen, (120, 90, 50), ar, 2, border_radius=6)
        asp = ASPECT_OPTIONS[self._aspect_index]
        asp_txt = self.body_font.render(
            f"Window size: {asp.label} ({asp.width}\u00d7{asp.height})", True, PARCHMENT
        )
        screen.blit(asp_txt, (ar.left + 12, ar.centery - asp_txt.get_height() // 2))
        tap = self.small_font.render("change >", True, INK_SOFT)
        screen.blit(tap, (ar.right - tap.get_width() - 12, ar.centery - tap.get_height() // 2))

        # Back / close.
        hot = self._options_back_rect.collidepoint(mouse)
        bg = (100, 70, 36) if hot else (58, 42, 26)
        pygame.draw.rect(screen, bg, self._options_back_rect, border_radius=8)
        pygame.draw.rect(screen, HIGHLIGHT, self._options_back_rect, 2, border_radius=8)
        bsurf = self.body_font.render("Back", True, PARCHMENT)
        screen.blit(
            bsurf,
            (
                self._options_back_rect.centerx - bsurf.get_width() // 2,
                self._options_back_rect.centery - bsurf.get_height() // 2,
            ),
        )

    def _draw_aspect_picker(
        self, screen: pygame.Surface, sw: int, sh: int, mouse: tuple[int, int]
    ) -> None:
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        screen.blit(overlay, (0, 0))

        pr = self._aspect_panel_rect
        pygame.draw.rect(screen, (38, 26, 18), pr, border_radius=12)
        pygame.draw.rect(screen, HIGHLIGHT, pr, 3, border_radius=12)

        title = self.heading_font.render("Choose window size", True, HIGHLIGHT)
        screen.blit(title, (pr.centerx - title.get_width() // 2, pr.top + 18))

        for rect, idx in self._aspect_option_rects:
            opt = ASPECT_OPTIONS[idx]
            picked = idx == self._aspect_index
            hot = rect.collidepoint(mouse)
            bg = (72, 52, 32) if picked else ((58, 42, 26) if hot else (44, 32, 22))
            pygame.draw.rect(screen, bg, rect, border_radius=6)
            pygame.draw.rect(screen, HIGHLIGHT if picked else (120, 90, 50), rect, 2, border_radius=6)
            lbl = self.body_font.render(
                f"{opt.label}  ({opt.width}\u00d7{opt.height})", True, PARCHMENT
            )
            screen.blit(lbl, (rect.left + 12, rect.centery - lbl.get_height() // 2))

        hot = self._aspect_back_rect.collidepoint(mouse)
        bg = (100, 70, 36) if hot else (58, 42, 26)
        pygame.draw.rect(screen, bg, self._aspect_back_rect, border_radius=8)
        pygame.draw.rect(screen, HIGHLIGHT, self._aspect_back_rect, 2, border_radius=8)
        bsurf = self.body_font.render("Back", True, PARCHMENT)
        screen.blit(
            bsurf,
            (
                self._aspect_back_rect.centerx - bsurf.get_width() // 2,
                self._aspect_back_rect.centery - bsurf.get_height() // 2,
            ),
        )

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

                if self._choosing_aspect:
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        self._choosing_aspect = False
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        mx, my = event.pos
                        chosen = False
                        for rect, idx in self._aspect_option_rects:
                            if rect.collidepoint(mx, my):
                                self._aspect_index = idx
                                self._choosing_aspect = False
                                chosen = True
                                break
                        if not chosen and (
                            self._aspect_back_rect.collidepoint(mx, my)
                            or not self._aspect_panel_rect.collidepoint(mx, my)
                        ):
                            self._choosing_aspect = False
                    continue

                if self._showing_options:
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        self._showing_options = False
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        mx, my = event.pos
                        if self._vol_minus_rect.collidepoint(mx, my):
                            self._set_volume(self._volume - 0.05)
                        elif self._vol_plus_rect.collidepoint(mx, my):
                            self._set_volume(self._volume + 0.05)
                        elif self._vol_track_rect.collidepoint(mx, my):
                            self._dragging_volume = True
                            self._set_volume(self._volume_from_x(mx))
                        elif self._aspect_rect.collidepoint(mx, my):
                            self._choosing_aspect = True
                        elif self._options_back_rect.collidepoint(mx, my) or not self._options_panel_rect.collidepoint(mx, my):
                            self._showing_options = False
                    elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                        self._dragging_volume = False
                    elif event.type == pygame.MOUSEMOTION and self._dragging_volume:
                        self._set_volume(self._volume_from_x(event.pos[0]))
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
                    if event.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                        self._selected_slot = event.key - pygame.K_0
                    if event.key == pygame.K_o:
                        self._showing_options = True
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = event.pos
                    for rect, slot in self._slot_rects:
                        if rect.collidepoint(mx, my):
                            self._selected_slot = slot
                            break
                    if self._options_rect.collidepoint(mx, my):
                        self._showing_options = True
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

            orr = self._options_rect
            hot = orr.collidepoint(mouse)
            bg = (58, 42, 26) if hot else (44, 32, 22)
            pygame.draw.rect(screen, bg, orr, border_radius=8)
            pygame.draw.rect(screen, HIGHLIGHT, orr, 2, border_radius=8)
            osurf = self.heading_font.render("Options", True, PARCHMENT)
            screen.blit(
                osurf,
                (orr.centerx - osurf.get_width() // 2, orr.centery - osurf.get_height() // 2),
            )
            otip = self.small_font.render("music & screen size", True, INK_SOFT)
            screen.blit(otip, (orr.right - otip.get_width() - 14, orr.centery - otip.get_height() // 2))

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

            if self._showing_options:
                self._draw_options(screen, mouse)
            if self._choosing_aspect:
                self._draw_aspect_picker(screen, sw, sh, mouse)

            hint = self.small_font.render(
                "1/2/3 select slot   New Game / Continue   O options   F1 help   Esc quit",
                True,
                INK_SOFT,
            )
            screen.blit(hint, (sw // 2 - hint.get_width() // 2, sh - 28))

            pygame.display.flip()

        if result is None:
            self._music.dispose()
        return result
