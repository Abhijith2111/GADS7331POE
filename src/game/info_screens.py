"""Pre-play briefing and the visual Help guide.

These are deliberately self-contained blocking screens that draw straight
onto the active pygame display surface so they can be reused from three
places without dragging in any game state:

  * the main menu (``Help`` button),
  * the briefing shown right before a game starts (``Begin`` / ``Help``),
  * the in-game action panel / F1 (``_show_help``).

The "screenshots" are labelled diagrams drawn live with pygame primitives,
so they always match the real interface (no image files to keep in sync).
"""

from __future__ import annotations

import pygame

from .assets import load_font
from .ui import (
    GOOD,
    HIGHLIGHT,
    INK_SOFT,
    PANEL_BORDER,
    PARCHMENT,
    action_button_color,
    draw_arrow,
    shift_color,
    wrap_text,
)

_BACKDROP = (18, 12, 8)
_PANEL_BG = (32, 23, 14)
_CARD_BG = (44, 32, 22)
_CARD_REGION = (58, 42, 26)
_HINT = (180, 140, 70)


# Short pitch shown on the briefing screen.
GAME_BLURB = (
    "You are the Tavern Master. Patrons wander in from the road, each with "
    "their own mood, coin, and stories. Chat with them, pour and sell drinks, "
    "and haggle for the best price you can get. Keep your ears open: the "
    "rumours you overhear can be remembered and sold, and some customers will "
    "hand you a quest. Earn gold and reputation, stock your cellar, and travel "
    "the region to become the most talked-about tavern in the land."
)

# Step-by-step loop, reused on the briefing screen and help page 1.
GAME_STEPS = (
    "Greet the seated customer by typing in the box and pressing Enter.",
    "Use the action buttons to show stock, sell a drink, or ask for work.",
    "Overhear rumours, Remember the good ones, then sell or spread them.",
    "Spend gold on supplies and leave the bar to explore and finish quests.",
)

# (label, description, arrow) rows mirroring the in-game action panel.
# Similar actions are folded into one "main" button (drawn with a small
# arrow); clicking it expands its members with a Back button.
BUTTON_GUIDE = (
    ("Trade", "Show the drink menu, or sell a drink and haggle the price.", "right"),
    ("Quests", "Ask the patron for work and review your active quests.", "right"),
    ("View gossip", "Read overheard rumours; Remember, Offer, or Spread them.", None),
    ("Next customer", "Send this patron away and bring in the next one.", None),
    ("Leave the bar", "Open the world map to travel and buy bulk supplies.", None),
    ("Menu", "Save your game, open this help guide (F1), or quit.", "right"),
)


def _draw_button(
    surface: pygame.Surface,
    rect: pygame.Rect,
    label: str,
    font: pygame.font.Font,
    *,
    hot: bool,
    primary: bool = False,
    accent: tuple[int, int, int] | None = None,
    arrow: str | None = None,
) -> None:
    if accent is not None:
        bg = shift_color(accent, 34) if hot else accent
        border = shift_color(accent, 70)
    elif primary:
        bg = (120, 84, 40) if hot else (100, 70, 36)
        border = HIGHLIGHT
    else:
        bg = (74, 54, 34) if hot else (58, 42, 26)
        border = HIGHLIGHT
    pygame.draw.rect(surface, bg, rect, border_radius=8)
    pygame.draw.rect(surface, border, rect, 2, border_radius=8)
    surf = font.render(label, True, PARCHMENT)
    surface.blit(
        surf,
        (rect.centerx - surf.get_width() // 2, rect.centery - surf.get_height() // 2),
    )
    if arrow:
        draw_arrow(surface, rect, arrow, PARCHMENT)


def _draw_card(surface: pygame.Surface, rect: pygame.Rect, title: str, font: pygame.font.Font) -> pygame.Rect:
    """Draw a titled "screenshot" card and return its inner content rect."""
    pygame.draw.rect(surface, _CARD_BG, rect, border_radius=10)
    pygame.draw.rect(surface, PANEL_BORDER, rect, 2, border_radius=10)
    tab = font.render(title, True, HIGHLIGHT)
    surface.blit(tab, (rect.left + 14, rect.top + 10))
    inner_top = rect.top + 14 + tab.get_height()
    return pygame.Rect(rect.left + 14, inner_top, rect.width - 28, rect.bottom - 14 - inner_top)


def _draw_gameplay_diagram(
    surface: pygame.Surface,
    rect: pygame.Rect,
    label_font: pygame.font.Font,
    body_font: pygame.font.Font,
) -> None:
    """A mock of the play screen with each region captioned."""
    gap = 8
    name_h = label_font.get_height()
    line_h = body_font.get_height()
    pad_top = 6
    pad_bottom = 8

    def region(r: pygame.Rect, name: str, caption: str) -> None:
        pygame.draw.rect(surface, _CARD_REGION, r, border_radius=6)
        pygame.draw.rect(surface, HIGHLIGHT, r, 2, border_radius=6)
        nm = label_font.render(name, True, HIGHLIGHT)
        surface.blit(nm, (r.left + 8, r.top + pad_top))
        cy = r.top + pad_top + name_h + 2
        for line in wrap_text(caption, body_font, r.width - 16):
            ls = body_font.render(line, True, PARCHMENT)
            surface.blit(ls, (r.left + 8, cy))
            cy += line_h

    # Height that comfortably holds the name plus a single caption line.
    strip_h = pad_top + name_h + 2 + line_h + pad_bottom

    # Top status strip.
    status = pygame.Rect(rect.left, rect.top, rect.width, strip_h)
    region(status, "STATUS BAR", "Your gold, reputation, quests and remembered rumours.")

    # Bottom conversation/input strip.
    conv = pygame.Rect(rect.left, rect.bottom - strip_h, rect.width, strip_h)
    region(
        conv,
        "CONVERSATION + TYPE HERE",
        "What you and the patron say. Type your message and press Enter to talk.",
    )

    # Middle row fills whatever is left between the two strips.
    body_top = status.bottom + gap
    body_bottom = conv.top - gap
    right_w = max(150, rect.width // 3)
    left = pygame.Rect(rect.left, body_top, rect.width - right_w - gap, body_bottom - body_top)
    right = pygame.Rect(left.right + gap, body_top, right_w, body_bottom - body_top)
    region(left, "THE CUSTOMER", "The patron you are serving right now appears here.")
    region(right, "ACTION BUTTONS", "Everything you can do — explained on the next page.")


def _draw_buttons_diagram(
    surface: pygame.Surface,
    rect: pygame.Rect,
    label_font: pygame.font.Font,
    body_font: pygame.font.Font,
) -> None:
    """A mock action panel beside one-line explanations of each button."""
    n = len(BUTTON_GUIDE)
    panel_w = max(150, rect.width // 3)
    panel = pygame.Rect(rect.left, rect.top, panel_w, rect.height)
    pygame.draw.rect(surface, (20, 14, 8), panel, border_radius=6)
    pygame.draw.rect(surface, PANEL_BORDER, panel, 2, border_radius=6)

    gap = 6
    btn_h = max(20, (rect.height - gap * (n - 1)) // n)
    desc_x = panel.right + 18
    desc_w = rect.right - desc_x
    for i, (label, desc, arrow) in enumerate(BUTTON_GUIDE):
        y = rect.top + i * (btn_h + gap)
        br = pygame.Rect(panel.left + 8, y, panel.width - 16, btn_h)
        _draw_button(
            surface,
            br,
            label,
            body_font,
            hot=False,
            accent=action_button_color(label),
            arrow=arrow,
        )
        # Description aligned to the button row.
        lines = wrap_text(desc, body_font, desc_w)
        ty = br.centery - (len(lines) * body_font.get_height()) // 2
        # Connector arrow.
        pygame.draw.line(surface, INK_SOFT, (br.right + 4, br.centery), (desc_x - 6, br.centery), 2)
        for line in lines:
            ls = body_font.render(line, True, PARCHMENT)
            surface.blit(ls, (desc_x, ty))
            ty += body_font.get_height()


def _get_surface(size: tuple[int, int]) -> pygame.Surface:
    surf = pygame.display.get_surface()
    if surf is None:
        surf = pygame.display.set_mode(size, pygame.RESIZABLE)
    return surf


def show_help_screen(clock: pygame.time.Clock) -> str:
    """Blocking, paged help guide. Returns 'close' or 'quit'.

    Draws over the whole active display. Two pages: the gameplay loop and
    the action-button reference. Esc/Enter or the Close button exit.
    """
    screen = _get_surface((960, 720))
    title_font = load_font(30, bold=True)
    head_font = load_font(20, bold=True)
    label_font = load_font(15, bold=True)
    body_font = load_font(15)
    small_font = load_font(14)

    page = 0
    pages = 2
    running = True
    result = "close"

    prev_rect = pygame.Rect(0, 0, 1, 1)
    next_rect = pygame.Rect(0, 0, 1, 1)
    close_rect = pygame.Rect(0, 0, 1, 1)

    while running:
        clock.tick(60)
        sw, sh = screen.get_size()
        pw = min(1060, sw - 60)
        ph = min(760, sh - 60)
        px = (sw - pw) // 2
        py = (sh - ph) // 2
        panel = pygame.Rect(px, py, pw, ph)
        foot_y = panel.bottom - 58
        btn_w = 150
        close_rect = pygame.Rect(panel.right - 20 - btn_w, foot_y, btn_w, 40)
        next_rect = pygame.Rect(close_rect.left - 12 - btn_w, foot_y, btn_w, 40)
        prev_rect = pygame.Rect(panel.left + 20, foot_y, btn_w, 40)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type == pygame.VIDEORESIZE:
                if event.w >= 320 and event.h >= 240:
                    screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                continue
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                    running = False
                elif event.key in (pygame.K_RIGHT, pygame.K_PAGEDOWN):
                    page = min(pages - 1, page + 1)
                elif event.key in (pygame.K_LEFT, pygame.K_PAGEUP):
                    page = max(0, page - 1)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if close_rect.collidepoint(event.pos):
                    running = False
                elif next_rect.collidepoint(event.pos) and page < pages - 1:
                    page += 1
                elif prev_rect.collidepoint(event.pos) and page > 0:
                    page -= 1

        mouse = pygame.mouse.get_pos()
        screen.fill(_BACKDROP)
        pygame.draw.rect(screen, _PANEL_BG, panel, border_radius=14)
        pygame.draw.rect(screen, PANEL_BORDER, panel, 3, border_radius=14)

        if page == 0:
            title = title_font.render("How to Play", True, HIGHLIGHT)
        else:
            title = title_font.render("What Each Button Does", True, HIGHLIGHT)
        screen.blit(title, (panel.left + 24, panel.top + 18))

        content = pygame.Rect(
            panel.left + 24,
            panel.top + 24 + title.get_height(),
            panel.width - 48,
            foot_y - (panel.top + 24 + title.get_height()) - 16,
        )

        if page == 0:
            y = content.top
            for line in wrap_text(GAME_BLURB, body_font, content.width):
                screen.blit(body_font.render(line, True, PARCHMENT), (content.left, y))
                y += body_font.get_height() + 2
            y += 6
            steps_head = head_font.render("Your loop each customer:", True, GOOD)
            screen.blit(steps_head, (content.left, y))
            y += steps_head.get_height() + 4
            for i, step in enumerate(GAME_STEPS, start=1):
                for j, line in enumerate(wrap_text(f"{i}. {step}", body_font, content.width - 12)):
                    screen.blit(body_font.render(line, True, PARCHMENT), (content.left + 12, y))
                    y += body_font.get_height()
                y += 4
            card = _draw_card(
                screen,
                pygame.Rect(content.left, y + 4, content.width, content.bottom - (y + 4)),
                "What your screen looks like",
                label_font,
            )
            _draw_gameplay_diagram(screen, card, label_font, small_font)
        else:
            intro = body_font.render(
                "The buttons on the right of the bar are your main tools:",
                True,
                PARCHMENT,
            )
            screen.blit(intro, (content.left, content.top))
            card = _draw_card(
                screen,
                pygame.Rect(
                    content.left,
                    content.top + intro.get_height() + 10,
                    content.width,
                    content.bottom - (content.top + intro.get_height() + 10),
                ),
                "Action panel reference",
                label_font,
            )
            _draw_buttons_diagram(screen, card, label_font, body_font)

        _draw_button(screen, close_rect, "Close", head_font, hot=close_rect.collidepoint(mouse), primary=True)
        if page < pages - 1:
            _draw_button(screen, next_rect, "Next \u25b6", head_font, hot=next_rect.collidepoint(mouse))
        if page > 0:
            _draw_button(screen, prev_rect, "\u25c0 Back", head_font, hot=prev_rect.collidepoint(mouse))

        ind = small_font.render(f"Page {page + 1} / {pages}   (\u2190/\u2192 to flip, Esc to close)", True, _HINT)
        screen.blit(ind, (panel.centerx - ind.get_width() // 2, foot_y + 12))

        pygame.display.flip()

    return result


def show_briefing(clock: pygame.time.Clock, title: str) -> str:
    """Blocking pre-play screen. Returns 'play', 'menu', or 'quit'.

    Shown after the player picks New Game / Continue and before the game
    actually starts, so they know what they are about to do.
    """
    screen = _get_surface((960, 720))
    title_font = load_font(40, bold=True)
    head_font = load_font(20, bold=True)
    body_font = load_font(18)
    small_font = load_font(14)

    running = True
    result = "menu"
    begin_rect = pygame.Rect(0, 0, 1, 1)
    help_rect = pygame.Rect(0, 0, 1, 1)
    back_rect = pygame.Rect(0, 0, 1, 1)

    while running:
        clock.tick(60)
        sw, sh = screen.get_size()
        pw = min(940, sw - 60)
        ph = min(760, sh - 60)
        px = (sw - pw) // 2
        py = (sh - ph) // 2
        panel = pygame.Rect(px, py, pw, ph)
        foot_y = panel.bottom - 64
        btn_w = min(240, (pw - 60) // 3)
        gap = (pw - 40 - btn_w * 3) // 2
        bx = panel.left + 20
        begin_rect = pygame.Rect(bx, foot_y, btn_w, 46)
        help_rect = pygame.Rect(bx + btn_w + gap, foot_y, btn_w, 46)
        back_rect = pygame.Rect(bx + 2 * (btn_w + gap), foot_y, btn_w, 46)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type == pygame.VIDEORESIZE:
                if event.w >= 320 and event.h >= 240:
                    screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                continue
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return "menu"
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return "play"
                if event.key in (pygame.K_F1, pygame.K_h):
                    if show_help_screen(clock) == "quit":
                        return "quit"
                    screen = _get_surface(screen.get_size())
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if begin_rect.collidepoint(event.pos):
                    return "play"
                if help_rect.collidepoint(event.pos):
                    if show_help_screen(clock) == "quit":
                        return "quit"
                    screen = _get_surface(screen.get_size())
                if back_rect.collidepoint(event.pos):
                    return "menu"

        mouse = pygame.mouse.get_pos()
        screen.fill(_BACKDROP)
        pygame.draw.rect(screen, _PANEL_BG, panel, border_radius=16)
        pygame.draw.rect(screen, PANEL_BORDER, panel, 3, border_radius=16)

        tit = title_font.render(title, True, HIGHLIGHT)
        screen.blit(tit, (panel.centerx - tit.get_width() // 2, panel.top + 26))
        sub = head_font.render("Your tavern awaits", True, GOOD)
        screen.blit(sub, (panel.centerx - sub.get_width() // 2, panel.top + 30 + tit.get_height()))

        y = panel.top + 44 + tit.get_height() + sub.get_height()
        text_w = panel.width - 64
        for line in wrap_text(GAME_BLURB, body_font, text_w):
            screen.blit(body_font.render(line, True, PARCHMENT), (panel.left + 32, y))
            y += body_font.get_height() + 3

        y += 14
        steps_head = head_font.render("What you'll be doing:", True, HIGHLIGHT)
        screen.blit(steps_head, (panel.left + 32, y))
        y += steps_head.get_height() + 8
        for i, step in enumerate(GAME_STEPS, start=1):
            for j, line in enumerate(wrap_text(f"{i}.  {step}", body_font, text_w - 16)):
                screen.blit(body_font.render(line, True, PARCHMENT), (panel.left + 44, y))
                y += body_font.get_height() + 1
            y += 6

        tip = small_font.render(
            "New here? Tap Help for a picture guide to the screen and every button.",
            True,
            _HINT,
        )
        screen.blit(tip, (panel.centerx - tip.get_width() // 2, foot_y - 30))

        _draw_button(screen, begin_rect, "Begin", head_font, hot=begin_rect.collidepoint(mouse), primary=True)
        _draw_button(screen, help_rect, "Help", head_font, hot=help_rect.collidepoint(mouse))
        _draw_button(screen, back_rect, "Back to menu", head_font, hot=back_rect.collidepoint(mouse))

        pygame.display.flip()

    return result
