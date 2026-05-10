"""Pygame UI primitives for the tavern.

Two big chunks live here:

* ``DialogueBox`` — renders the streaming NPC reply as it arrives, plus a
  scrollable transcript of the chat so far.
* ``TextInput`` — a single-line input field with a blinking caret and
  basic editing (backspace, delete, home/end).

Plus a few small widgets (status bar, button, modal panel) used by the
haggle prompt and the settings menu.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

import pygame

from .assets import load_font


# ---------------------------------------------------------------------------
# Colours / spacing constants. Kept in one place so the look is consistent.
# ---------------------------------------------------------------------------
PARCHMENT = (236, 222, 196)
INK = (30, 22, 14)
INK_SOFT = (90, 70, 50)
HIGHLIGHT = (180, 140, 70)
PANEL_BG = (40, 28, 18, 230)
PANEL_BORDER = (120, 90, 50)
WARN = (180, 60, 50)
GOOD = (90, 140, 70)


# ---------------------------------------------------------------------------
# Word-wrapping helper
# ---------------------------------------------------------------------------
def wrap_text(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
    """Greedy word-wrap; returns a list of rendered lines."""
    if not text:
        return [""]
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        words = paragraph.split(" ")
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if font.size(candidate)[0] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines


# ---------------------------------------------------------------------------
# Dialogue box
# ---------------------------------------------------------------------------
@dataclass
class DialogueLine:
    speaker: str  # "You" | persona name | "system"
    text: str
    is_streaming: bool = False


class DialogueBox:
    """Scrolling chat panel with a streaming current reply."""

    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect
        self.body_font = load_font(20)
        self.speaker_font = load_font(22, bold=True)
        self.lines: list[DialogueLine] = []
        self.scroll_px = 0  # 0 = pinned to bottom; positive scrolls up

    def add(self, speaker: str, text: str, *, streaming: bool = False) -> None:
        self.lines.append(DialogueLine(speaker=speaker, text=text, is_streaming=streaming))
        self.scroll_px = 0

    def append_to_last(self, chunk: str) -> None:
        if not self.lines:
            self.lines.append(DialogueLine(speaker="...", text=chunk, is_streaming=True))
            return
        self.lines[-1].text += chunk

    def finalize_streaming(self) -> None:
        if self.lines and self.lines[-1].is_streaming:
            self.lines[-1].is_streaming = False

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEWHEEL and self.rect.collidepoint(pygame.mouse.get_pos()):
            self.scroll_px = max(0, self.scroll_px + event.y * 28)

    def draw(self, surface: pygame.Surface) -> None:
        panel = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        panel.fill(PANEL_BG)
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), 2)
        surface.blit(panel, self.rect.topleft)

        padding = 14
        max_width = self.rect.width - padding * 2

        rendered: list[tuple[pygame.Surface, int]] = []
        for line in self.lines:
            speaker_surf = self.speaker_font.render(line.speaker, True, HIGHLIGHT)
            rendered.append((speaker_surf, speaker_surf.get_height()))
            wrapped = wrap_text(line.text + ("_" if line.is_streaming else ""), self.body_font, max_width)
            for w_line in wrapped:
                line_surf = self.body_font.render(w_line, True, PARCHMENT)
                rendered.append((line_surf, line_surf.get_height()))
            spacer = pygame.Surface((1, 8), pygame.SRCALPHA)
            rendered.append((spacer, 8))

        total_height = sum(h for _, h in rendered)
        y_start = self.rect.bottom - padding - total_height + self.scroll_px
        clip = surface.get_clip()
        surface.set_clip(self.rect)
        y = y_start
        for surf, h in rendered:
            if y + h > self.rect.top + padding and y < self.rect.bottom - padding:
                surface.blit(surf, (self.rect.left + padding, y))
            y += h
        surface.set_clip(clip)


# ---------------------------------------------------------------------------
# Text input
# ---------------------------------------------------------------------------
class TextInput:
    """Single-line input with blinking caret. ``submit_cb`` fires on Enter."""

    def __init__(self, rect: pygame.Rect, submit_cb: Callable[[str], None]) -> None:
        self.rect = rect
        self.font = load_font(22)
        self.text = ""
        self.cursor = 0
        self.active = True
        self.submit_cb = submit_cb
        self.placeholder = "Speak to the customer..."
        self._caret_t = 0.0

    def set_active(self, active: bool) -> None:
        self.active = active

    def set_placeholder(self, text: str) -> None:
        self.placeholder = text

    def handle_event(self, event: pygame.event.Event) -> None:
        if not self.active:
            return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                if self.text.strip():
                    text = self.text
                    self.text = ""
                    self.cursor = 0
                    self.submit_cb(text)
            elif event.key == pygame.K_BACKSPACE:
                if self.cursor > 0:
                    self.text = self.text[: self.cursor - 1] + self.text[self.cursor:]
                    self.cursor -= 1
            elif event.key == pygame.K_DELETE:
                if self.cursor < len(self.text):
                    self.text = self.text[: self.cursor] + self.text[self.cursor + 1:]
            elif event.key == pygame.K_LEFT:
                self.cursor = max(0, self.cursor - 1)
            elif event.key == pygame.K_RIGHT:
                self.cursor = min(len(self.text), self.cursor + 1)
            elif event.key == pygame.K_HOME:
                self.cursor = 0
            elif event.key == pygame.K_END:
                self.cursor = len(self.text)
            elif event.unicode and event.unicode.isprintable():
                self.text = self.text[: self.cursor] + event.unicode + self.text[self.cursor:]
                self.cursor += len(event.unicode)

    def update(self, dt: float) -> None:
        self._caret_t += dt

    def draw(self, surface: pygame.Surface) -> None:
        bg = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        bg.fill((20, 12, 6, 220) if self.active else (20, 12, 6, 140))
        pygame.draw.rect(bg, HIGHLIGHT if self.active else PANEL_BORDER, bg.get_rect(), 2)
        surface.blit(bg, self.rect.topleft)

        padding = 12
        if self.text:
            text_surf = self.font.render(self.text, True, PARCHMENT)
        else:
            text_surf = self.font.render(self.placeholder, True, INK_SOFT)
        surface.blit(
            text_surf,
            (self.rect.left + padding, self.rect.centery - text_surf.get_height() // 2),
        )

        if self.active and int(self._caret_t * 2) % 2 == 0:
            prefix = self.text[: self.cursor]
            caret_x = self.rect.left + padding + self.font.size(prefix)[0]
            pygame.draw.line(
                surface,
                PARCHMENT,
                (caret_x, self.rect.top + 8),
                (caret_x, self.rect.bottom - 8),
                2,
            )


# ---------------------------------------------------------------------------
# Status bar (gold, reputation, active quest count)
# ---------------------------------------------------------------------------
class StatusBar:
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect
        self.font = load_font(20, bold=True)
        self.small_font = load_font(16)

    def draw(
        self,
        surface: pygame.Surface,
        *,
        gold: int,
        reputation: dict[str, int],
        active_quests: int,
        gossip_count: int,
        model_name: str,
    ) -> None:
        bg = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        bg.fill((20, 14, 8, 220))
        pygame.draw.rect(bg, PANEL_BORDER, bg.get_rect(), 2)
        surface.blit(bg, self.rect.topleft)

        x = self.rect.left + 16
        y = self.rect.top + 10

        gold_surf = self.font.render(f"Gold: {gold}", True, HIGHLIGHT)
        surface.blit(gold_surf, (x, y))

        rep_str = "  ".join(f"{k}:{v:+d}" for k, v in reputation.items())
        rep_surf = self.small_font.render(rep_str, True, PARCHMENT)
        surface.blit(rep_surf, (x, y + gold_surf.get_height() + 2))

        right_x = self.rect.right - 16
        meta = self.small_font.render(
            f"Quests: {active_quests}   Gossip: {gossip_count}   Model: {model_name}",
            True,
            INK_SOFT,
        )
        surface.blit(meta, (right_x - meta.get_width(), y + 6))


# ---------------------------------------------------------------------------
# Modal panel (haggle / settings)
# ---------------------------------------------------------------------------
@dataclass
class Button:
    label: str
    rect: pygame.Rect
    on_click: Callable[[], None]
    hot: bool = False
    enabled: bool = True


class ModalPanel:
    """Re-usable centred panel with a title, body lines, and buttons."""

    def __init__(self, screen_size: tuple[int, int], size: tuple[int, int]) -> None:
        sw, sh = screen_size
        w, h = size
        self.rect = pygame.Rect((sw - w) // 2, (sh - h) // 2, w, h)
        self.title_font = load_font(28, bold=True)
        self.body_font = load_font(20)
        self.button_font = load_font(20, bold=True)
        self.title = ""
        self.body_lines: list[str] = []
        self.buttons: list[Button] = []
        self.visible = False

    def show(self, title: str, body: str, buttons: list[Button]) -> None:
        self.title = title
        self.body_lines = wrap_text(body, self.body_font, self.rect.width - 40)
        self.buttons = buttons
        self.visible = True

    def hide(self) -> None:
        self.visible = False
        self.buttons = []

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible:
            return False
        if event.type == pygame.MOUSEMOTION:
            for b in self.buttons:
                b.hot = b.rect.collidepoint(event.pos) and b.enabled
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for b in self.buttons:
                if b.enabled and b.rect.collidepoint(event.pos):
                    b.on_click()
                    return True
        return self.rect.collidepoint(pygame.mouse.get_pos())

    def draw(self, surface: pygame.Surface) -> None:
        if not self.visible:
            return
        # Dim background.
        dim = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 160))
        surface.blit(dim, (0, 0))

        panel = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        panel.fill((40, 28, 18, 245))
        pygame.draw.rect(panel, HIGHLIGHT, panel.get_rect(), 3)
        surface.blit(panel, self.rect.topleft)

        title_surf = self.title_font.render(self.title, True, HIGHLIGHT)
        surface.blit(
            title_surf,
            (self.rect.centerx - title_surf.get_width() // 2, self.rect.top + 18),
        )

        y = self.rect.top + 18 + title_surf.get_height() + 14
        for line in self.body_lines:
            line_surf = self.body_font.render(line, True, PARCHMENT)
            surface.blit(line_surf, (self.rect.left + 20, y))
            y += line_surf.get_height() + 4

        for b in self.buttons:
            base = (90, 60, 30) if b.enabled else (50, 40, 30)
            if b.hot:
                base = (130, 90, 40)
            pygame.draw.rect(surface, base, b.rect, border_radius=6)
            pygame.draw.rect(surface, HIGHLIGHT if b.enabled else INK_SOFT, b.rect, 2, border_radius=6)
            label = self.button_font.render(b.label, True, PARCHMENT)
            surface.blit(
                label,
                (
                    b.rect.centerx - label.get_width() // 2,
                    b.rect.centery - label.get_height() // 2,
                ),
            )


# ---------------------------------------------------------------------------
# Toast (transient bottom-right notification)
# ---------------------------------------------------------------------------
@dataclass
class Toast:
    text: str
    born_at: float = field(default_factory=time.monotonic)
    ttl: float = 3.0
    color: tuple[int, int, int] = HIGHLIGHT

    def alive(self) -> bool:
        return time.monotonic() - self.born_at < self.ttl


class ToastStack:
    def __init__(self, anchor: tuple[int, int]) -> None:
        self.anchor = anchor
        self.font = load_font(18, bold=True)
        self.toasts: list[Toast] = []

    def push(self, text: str, color: tuple[int, int, int] = HIGHLIGHT) -> None:
        self.toasts.append(Toast(text=text, color=color))

    def draw(self, surface: pygame.Surface) -> None:
        self.toasts = [t for t in self.toasts if t.alive()]
        x, y = self.anchor
        for t in reversed(self.toasts[-5:]):
            text_surf = self.font.render(t.text, True, t.color)
            pad = 10
            rect = pygame.Rect(
                x - text_surf.get_width() - pad * 2,
                y - text_surf.get_height() - pad,
                text_surf.get_width() + pad * 2,
                text_surf.get_height() + pad,
            )
            bg = pygame.Surface(rect.size, pygame.SRCALPHA)
            bg.fill((20, 14, 8, 220))
            pygame.draw.rect(bg, t.color, bg.get_rect(), 2)
            surface.blit(bg, rect.topleft)
            surface.blit(
                text_surf,
                (rect.left + pad, rect.top + pad // 2),
            )
            y -= rect.height + 6


# ---------------------------------------------------------------------------
# Transparency banner — required for ethical disclosure (LLM in use)
# ---------------------------------------------------------------------------
class TransparencyBanner:
    """A tiny strip across the top reminding the player that NPC dialogue
    is generated locally by an LLM. The player can hide it but it is on
    by default, per the ethics section of the integration report.
    """

    def __init__(self, screen_width: int) -> None:
        self.font = load_font(15, bold=True)
        self.rect = pygame.Rect(0, 0, screen_width, 24)
        self.visible = True

    def toggle(self) -> None:
        self.visible = not self.visible

    def draw(self, surface: pygame.Surface, model_name: str) -> None:
        if not self.visible:
            return
        bg = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        bg.fill((20, 14, 8, 230))
        pygame.draw.line(bg, HIGHLIGHT, (0, self.rect.height - 1), (self.rect.width, self.rect.height - 1), 1)
        surface.blit(bg, self.rect.topleft)
        text = self.font.render(
            f"  AI NOTICE  Customer dialogue is generated locally by Ollama ({model_name}). "
            "Press T to hide.",
            True,
            HIGHLIGHT,
        )
        surface.blit(text, (10, 4))
