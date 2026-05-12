"""The Wandering Goblet — entry point.

Wires together the Pygame scene, the world state, persona rotation, and
the Ollama client. LLM calls run on background threads and push events
back into the main loop via a queue, so the game never blocks.

Run normally:
    python -m src.main

Demo mode (scripted persona, fixed seed, prompt log to disk):
    python -m src.main --demo --persona broke_bard --turns 4
"""

from __future__ import annotations

import argparse
import json
import queue
import random
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pygame

from src.game.assets import MusicPlayer, SoundLibrary, load_font
from src.game.npc import NPC, CustomerQueue, load_persona_by_id, load_personas
from src.game.scene import TavernScene
from src.game.ui import (
    GOOD,
    HIGHLIGHT,
    PARCHMENT,
    WARN,
    ActionPanel,
    Button,
    DialogueBox,
    ModalPanel,
    StatusBar,
    TextInput,
    ToastStack,
    TransparencyBanner,
    wrap_text,
)
from src.game.world_map import LocationScene, WorldMapScene
from src.game.world_map_data import get_hotspot, get_location
from src.game.world_state import WorldState
from src.llm import prompts as P
from src.llm.ollama_client import OllamaClient, OllamaConfig, OllamaError
from src.llm.parsers import (
    DEGRADED_FOUND,
    DEGRADED_HAGGLE,
    DEGRADED_QUEST,
    FoundLine,
    HaggleDecision,
    Quest,
    call_with_retry,
    extract_item_phrase,
    parse_found_line,
    parse_haggle,
    parse_quest,
)

# Taller default window so the tavern scene + full-height action column
# fit comfortably; all buttons stay on-screen without scrolling.
SCREEN_SIZE = (1280, 880)
TITLE = "The Wandering Goblet"
ITEMS_PATH = Path("data") / "items.json"


# ---------------------------------------------------------------------------
# Worker -> main thread events
# ---------------------------------------------------------------------------
@dataclass
class TokenEvent:
    token: str


@dataclass
class StreamDoneEvent:
    full_text: str


@dataclass
class HaggleResultEvent:
    decision: HaggleDecision
    item_id: str
    offered_price: int
    ok: bool


@dataclass
class QuestResultEvent:
    quest: Quest
    ok: bool


@dataclass
class FoundResultEvent:
    quest_title: str
    found: FoundLine
    ok: bool


@dataclass
class GossipSellResultEvent:
    """Result of the 'sell rumour about you' micro-haggle."""

    decision: HaggleDecision
    rumour_text: str
    offered_price: int
    ok: bool


@dataclass
class ErrorEvent:
    message: str


@dataclass
class OllamaStatusEvent:
    """Status update from the auto-connect worker. Drives toasts only."""

    message: str
    kind: str = "info"  # info | good | warn


@dataclass
class _OllamaReadyMarker:
    """Sentinel pushed after the auto-connect worker finishes successfully."""


# ---------------------------------------------------------------------------
# Mode constants — TAVERN is the chat-and-haggle bar, WORLD_MAP shows the
# four-location selector, LOCATION is the in-world hotspot search.
# ---------------------------------------------------------------------------
MODE_TAVERN = "TAVERN"
MODE_WORLD_MAP = "WORLD_MAP"
MODE_LOCATION = "LOCATION"


# ---------------------------------------------------------------------------
# Wrong-click satire lines.
#
# Indexed by how many times the player has already clicked *this* specific
# hotspot in the current session. We escalate from neutral, to dry, to mild
# sass. The final bucket loops with a small variation pool so a stubborn
# player gets some variety instead of one fixed line forever.
# ---------------------------------------------------------------------------
WRONG_CLICK_LINES: dict[int, list[str]] = {
    0: [
        "Nothing useful here. (You searched the {name}.)",
    ],
    1: [
        "Still nothing at the {name}. Maybe somewhere else?",
        "The {name} is just as empty as it was a moment ago.",
    ],
    2: [
        "You just checked the {name}. Go away.",
        "The {name} hasn't grown new clues in the last five seconds.",
        "Yes, the {name}. We saw it. There is nothing there.",
    ],
    3: [
        "Are we okay? The {name} is still empty.",
        "If you keep clicking the {name}, the {name} is going to file a complaint.",
        "Bold strategy: searching the same {name} until it gives in.",
        "The {name} would like to be left alone now.",
    ],
}


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------
class Game:
    def __init__(self, args: argparse.Namespace) -> None:
        pygame.init()
        pygame.display.set_caption(TITLE)
        self.screen = pygame.display.set_mode(SCREEN_SIZE)
        self.clock = pygame.time.Clock()
        self.font = load_font(20)
        self.title_font = load_font(46, bold=True)
        self.demo_mode = args.demo
        self.demo_turns = args.turns
        self.demo_persona = args.persona

        self.world = WorldState.load()
        self.scene = TavernScene(SCREEN_SIZE)
        self.sfx = SoundLibrary()
        # Background music: procedural ambient pad by default, overridable
        # by any file in assets/music/. Off automatically in --demo mode
        # so the captured video doesn't fight the dialogue audio.
        self.music = MusicPlayer()
        if not self.demo_mode:
            self.music.start()

        self.client = OllamaClient(
            OllamaConfig(
                model=args.model,
                seed=args.seed if args.seed is not None else (1234 if args.demo else None),
            )
        )

        self.items = self._load_items()
        self.personas = load_personas()
        self.queue_pickers = CustomerQueue(self.personas)

        self.current_npc: NPC | None = None
        self.streaming = False
        self.event_q: "queue.Queue[Any]" = queue.Queue()

        # Mode state machine: TAVERN | WORLD_MAP | LOCATION. Each mode
        # owns which middle scene is drawn and which input flows fire.
        self.mode: str = MODE_TAVERN
        self.current_location_id: str | None = None
        # Set when a hotspot click triggers the found-it LLM call.
        self._pending_found_quest: dict[str, Any] | None = None
        # Schedule auto-return to tavern after a successful quest.
        self._return_to_tavern_at: float | None = None
        # Per-(location, hotspot) wrong-click counter, drives escalating
        # satire on repeat clicks. Reset on every fresh location entry.
        self._wrong_click_counts: dict[tuple[str, str], int] = {}
        # Set by the Ollama auto-connect worker once the daemon, model,
        # and warmup are all done. Mostly informational.
        self._ollama_ready: bool = False

        # UI layout.
        self._init_ui()

        # Pending haggle context (set when a haggle is in flight).
        self._pending_haggle_item: dict[str, Any] | None = None
        self._pending_haggle_offer: int | None = None

        # First customer.
        self._spawn_next_customer()
        self._refresh_action_buttons()

        # In demo mode we run a scripted set of player inputs and exit.
        self._demo_script: list[str] = []
        if self.demo_mode:
            self._demo_script = self._build_demo_script()
            self._demo_step_pending = False

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------
    def _load_items(self) -> list[dict[str, Any]]:
        with open(ITEMS_PATH, "r", encoding="utf-8") as fh:
            return list(json.load(fh)["items"])

    def _init_ui(self) -> None:
        sw, sh = SCREEN_SIZE
        margin = 20
        dialogue_h = 240
        input_h = 48
        status_h = 60
        side_panel_w = 220
        side_gap = 12

        self.status_bar = StatusBar(
            pygame.Rect(margin, margin + 26, sw - margin * 2, status_h)
        )

        chat_w = sw - margin * 2 - side_panel_w - side_gap
        self.dialogue = DialogueBox(
            pygame.Rect(
                margin,
                sh - margin - input_h - 12 - dialogue_h,
                chat_w,
                dialogue_h,
            )
        )
        self.text_input = TextInput(
            pygame.Rect(margin, sh - margin - input_h, chat_w, input_h),
            submit_cb=self._on_player_submit,
        )

        # Action column: full height from below the status band to the
        # bottom margin, so every mode's buttons fit without clipping.
        # (Previously the panel only matched the dialogue stack + input,
        # which was too short once we added journals/explore buttons.)
        scene_top = margin + 26 + status_h + 8
        action_x = margin + chat_w + side_gap
        action_y = scene_top
        action_h = sh - margin - action_y
        self.actions = ActionPanel(
            pygame.Rect(action_x, action_y, side_panel_w, action_h)
        )
        # Buttons are configured dynamically per mode by
        # ``_refresh_action_buttons`` so we don't seed any here.

        self.toasts = ToastStack(
            anchor=(action_x, action_y + 6)
        )
        self.banner = TransparencyBanner(sw)
        self.modal = ModalPanel(SCREEN_SIZE, (720, 520))
        self.help_visible = False

        # Sell flow state (active while the sell modal is open).
        self._sell_item: dict[str, Any] | None = None
        self._sell_offer: int = 0

        # Gossip-sell flow state (active while the gossip price modal is up).
        self._gossip_sell_text: str | None = None
        self._gossip_sell_offer: int = 5

        # Pin the NPC + name plate just above the dialogue box.
        self.scene.set_floor_y(self.dialogue.rect.top - 8)

        # World-map and location scenes share the same canvas the tavern
        # scene uses (full screen minus banner). They are built once and
        # re-shown when the mode changes.
        canvas_rect = pygame.Rect(
            margin,
            margin + 26 + status_h + 8,
            sw - margin * 2 - side_panel_w - side_gap,
            sh - margin - (margin + 26 + status_h + 8),
        )
        self.world_map_scene = WorldMapScene(canvas_rect)
        self.location_scene = LocationScene(canvas_rect)

    # ------------------------------------------------------------------
    # Health check + first persona
    # ------------------------------------------------------------------
    def _spawn_next_customer(self) -> None:
        if self.demo_mode and self.demo_persona:
            persona = load_persona_by_id(self.demo_persona)
            self.current_npc = NPC(persona=persona)
        else:
            self.current_npc = self.queue_pickers.next()
        self.scene.set_npc(self.current_npc.persona)
        self.dialogue.add(
            "system",
            f"{self.current_npc.name} steps up to the counter.",
        )
        self.sfx.play("door")

    def _check_ollama(self) -> None:
        """Kick off the auto-connect/auto-pull/warmup sequence.

        Runs entirely on a background thread so the UI keeps drawing
        while we wait for the daemon to come up or a fresh model to
        download. The worker funnels status updates back through the
        event queue, so all toast pushes happen on the main thread.
        """
        self._ollama_ready = False
        threading.Thread(target=self._ollama_bootstrap_worker, daemon=True).start()

    def _ollama_bootstrap_worker(self) -> None:
        def emit(message: str, kind: str = "info") -> None:
            self.event_q.put(OllamaStatusEvent(message=message, kind=kind))

        model = self.client.config.model
        emit("Checking Ollama...", "info")

        # 1. Make sure the daemon is reachable (start it if we can).
        if not self.client.ensure_daemon(on_status=lambda m: emit(m, "info")):
            emit(
                "Ollama is not available. The game will still run but "
                "customers won't be able to talk.",
                "warn",
            )
            return

        # 2. Make sure the configured model is on disk; pull it if not.
        if not self.client.has_model(model):
            emit(f"Downloading {model} (first launch only)...", "info")
            ok = self.client.pull_model(
                model, on_progress=lambda m: emit(m, "info")
            )
            if not ok:
                emit(
                    f"Could not pull {model}. Open a terminal and run "
                    f"'ollama pull {model}'.",
                    "warn",
                )
                return

        # 3. Warm the model so the first chat is snappy.
        emit(f"Warming up {model}...", "info")
        self.client.warmup()
        emit(f"Ollama ready ({model}).", "good")
        self.event_q.put(_OllamaReadyMarker())

    def _on_ollama_status(self, ev: "OllamaStatusEvent") -> None:
        color = {"good": GOOD, "warn": WARN}.get(ev.kind, HIGHLIGHT)
        self.toasts.push(ev.message, color)

    # ------------------------------------------------------------------
    # Player input
    # ------------------------------------------------------------------
    def _on_player_submit(self, text: str) -> None:
        if self.streaming or self.current_npc is None:
            return
        text = text.strip()
        if not text:
            return

        # Slash-commands: /sell <item> <price>, /haggle <item> <price>, /quest, /next, /help
        if text.startswith("/"):
            self._handle_command(text)
            return

        self.dialogue.add("You", text)
        self.current_npc.append_user(text)
        self._start_chat_stream(text)

    def _handle_command(self, text: str) -> None:
        parts = text.split()
        cmd = parts[0].lower()
        if cmd == "/help":
            self._show_help()
        elif cmd == "/next":
            self._next_customer()
        elif cmd == "/quest":
            self._request_quest()
        elif cmd in ("/sell", "/haggle"):
            if len(parts) < 3:
                self.toasts.push("Usage: /sell <item_id> <price>", WARN)
                return
            item_id = parts[1]
            try:
                price = int(parts[2])
            except ValueError:
                self.toasts.push("Price must be a whole number of gold.", WARN)
                return
            self._start_haggle(item_id, price)
        elif cmd == "/items":
            self._show_stock_modal()
        elif cmd == "/save":
            self._save_game()
        else:
            self.toasts.push(f"Unknown command: {cmd}. Try /help.", WARN)

    def _show_help(self) -> None:
        self.dialogue.add(
            "system",
            "How to play:\n"
            "  - Type a message and press Enter to talk to the customer.\n"
            "  - Use the buttons on the right for actions:\n"
            "      Show stock     - the bar's menu and prices\n"
            "      Sell item...   - pick an item, set a price, and haggle\n"
            "      Ask for work   - see if the customer has a quest\n"
            "      View quests    - your active and completed quests\n"
            "      View gossip    - rumours you've overheard. If the\n"
            "                       current customer is named in one,\n"
            "                       you can sell them the rumour for\n"
            "                       a price of your choosing.\n"
            "      Next customer  - send this one away, bring in the next\n"
            "      Save game      - persist the world state to disk\n"
            "  - Leaving the bar: once you have a quest, the side panel\n"
            "    shows 'Leave the bar'. Pick a location, then click the\n"
            "    glowing hotspot to find the item. Wrong clicks just\n"
            "    print 'Nothing useful here.' and cost you nothing.\n"
            "  - Hot-keys: F1 help, F2 settings, F5 next customer, T toggles\n"
            "    the AI banner, M mutes/unmutes background music, Esc quits.\n"
            "  - Power users can still type slash commands like\n"
            "    /sell strong_stout 5 directly into the input bar.",
        )

    # ------------------------------------------------------------------
    # Action-panel handlers
    # ------------------------------------------------------------------
    def _save_game(self) -> None:
        self.world.save()
        self.toasts.push("World state saved.", GOOD)

    def _show_stock_modal(self) -> None:
        """Read-only modal listing every item and its base price."""
        body_lines = ["The Wandering Goblet's catalogue:", ""]
        for item in self.items:
            body_lines.append(
                f"  {item['name']:<28} {item['base_price']:>3} gold"
            )
            body_lines.append(f"      {item['description']}")
            body_lines.append("")
        body = "\n".join(body_lines)

        modal_rect = self.modal.rect
        close_btn = Button(
            "Close",
            pygame.Rect(modal_rect.right - 140, modal_rect.bottom - 56, 120, 38),
            self.modal.hide,
        )
        self.modal.show("Stock", body, [close_btn])

    # ------------------------------------------------------------------
    # Journal modals: quests + gossip
    # ------------------------------------------------------------------
    def _show_quests_modal(self) -> None:
        """Read-only modal listing active + completed quests.

        Each active quest line shows the title, a clipped summary, the
        location where the item is hidden, and the reward. Completed
        quests are listed below with just the title and reward.
        """
        active = self.world.active_quests
        completed = self.world.completed_quests

        if not active and not completed:
            body = (
                "Your quest journal is empty.\n\n"
                "Use 'Ask for work' on a customer to pick up errands."
            )
            modal_rect = self.modal.rect
            close = Button(
                "Close",
                pygame.Rect(modal_rect.right - 140, modal_rect.bottom - 56, 120, 38),
                self.modal.hide,
            )
            self.modal.show("Quest Journal", body, [close])
            return

        lines: list[str] = []
        if active:
            lines.append(f"Active quests ({len(active)}):")
            lines.append("")
            for q in active:
                lines.append(f"- {q.get('title', '?')}")
                summary = q.get("summary", "")
                if summary:
                    lines.append(f"    \"{summary}\"")
                loc = get_location(q.get("location", ""))
                spot = q.get("hotspot", "")
                spot_name = next(
                    (h["name"] for h in loc["hotspots"] if h["id"] == spot),
                    spot or "?",
                )
                lines.append(
                    f"    where: {loc['name']} -> {spot_name}"
                )
                lines.append(
                    f"    reward: {q.get('reward_gold', 0)}g  danger: "
                    f"{q.get('danger', 'low')}"
                )
                lines.append("")
        if completed:
            lines.append(f"Completed ({len(completed)}):")
            lines.append("")
            for q in completed[-8:]:
                lines.append(
                    f"- {q.get('title', '?')}  (+{q.get('reward_gold', 0)}g)"
                )
            lines.append("")

        body = "\n".join(lines)
        modal_rect = self.modal.rect
        close = Button(
            "Close",
            pygame.Rect(modal_rect.right - 140, modal_rect.bottom - 56, 120, 38),
            self.modal.hide,
        )
        self.modal.show("Quest Journal", body, [close])

    def _show_gossip_modal(self) -> None:
        """Modal listing every rumour the keeper has overheard.

        If a rumour mentions the current customer by name, a "Sell to
        <first name>" button is drawn on its row -- clicking it starts
        the sell-the-rumour negotiation flow. Wrapping is done by hand
        (rather than via ``ModalPanel.show``) so we can pin each button
        to its rumour's own y-coordinate.
        """
        if not self.world.gossip_heard:
            body = (
                "No gossip has reached your ear yet.\n\n"
                "Keep chatting; customers drop rumours when they get talking."
            )
            modal_rect = self.modal.rect
            close = Button(
                "Close",
                pygame.Rect(modal_rect.right - 140, modal_rect.bottom - 56, 120, 38),
                self.modal.hide,
            )
            self.modal.show("Gossip Heard", body, [close])
            return

        # Show the most recent entries first; older ones are paginated out
        # but counted in the footer so the player knows they exist.
        recent = list(reversed(self.world.gossip_heard))
        max_visible = 8
        shown = recent[:max_visible]
        hidden = len(recent) - len(shown)

        modal = self.modal
        modal_rect = modal.rect
        npc = self.current_npc
        npc_first = (npc.name.split()[0] if npc else "").lower()
        npc_full = (npc.name if npc else "").lower()

        button_w = 170
        button_h = 30
        text_max_width = modal_rect.width - 40 - button_w - 20

        # Title block + body start y match ModalPanel.draw.
        body_top = (
            modal_rect.top
            + 18
            + modal.title_font.get_height()
            + 14
        )
        line_h = modal.body_font.get_height() + 4

        body_lines: list[str] = []
        buttons: list[Button] = []
        y = body_top
        for gossip in shown:
            wrapped = wrap_text(f"- {gossip}", modal.body_font, text_max_width)
            first_line_y = y
            for line in wrapped:
                body_lines.append(line)
                y += line_h
            mentions = npc is not None and (
                (npc_first and npc_first in gossip.lower())
                or (npc_full and npc_full in gossip.lower())
            )
            if mentions and npc is not None and not self.streaming:
                short_name = npc.name.split()[0]
                buttons.append(
                    Button(
                        f"Sell to {short_name}",
                        pygame.Rect(
                            modal_rect.right - 20 - button_w,
                            first_line_y,
                            button_w,
                            button_h,
                        ),
                        on_click=(
                            lambda g=gossip: self._open_gossip_sell_price(g)
                        ),
                    )
                )
            body_lines.append("")
            y += line_h
        if hidden > 0:
            body_lines.append(f"({hidden} older rumour(s) not shown.)")
        if npc is None:
            body_lines.append("")
            body_lines.append(
                "(Spawn a customer to sell rumours about them.)"
            )
        elif not any(
            (npc_first and npc_first in g.lower())
            or (npc_full and npc_full in g.lower())
            for g in shown
        ):
            body_lines.append("")
            body_lines.append(
                f"(No rumours about {npc.name} on this page.)"
            )

        buttons.append(
            Button(
                "Close",
                pygame.Rect(
                    modal_rect.right - 140, modal_rect.bottom - 56, 120, 38
                ),
                modal.hide,
            )
        )

        # Bypass modal.show so we can keep our hand-built body_lines AND
        # pin buttons to individual rumour rows.
        modal.title = "Gossip Heard"
        modal.body_lines = body_lines
        modal.buttons = buttons
        modal.visible = True

    # ------------------------------------------------------------------
    # Sell-a-rumour flow (gossip the keeper has overheard about the NPC)
    # ------------------------------------------------------------------
    def _open_gossip_sell_price(self, gossip_text: str) -> None:
        """Stage 2 of the gossip-sell flow: pick a price."""
        if self.streaming or self.current_npc is None:
            self.toasts.push("Wait for the customer's reply first.", WARN)
            return
        self._gossip_sell_text = gossip_text
        # Default opening price scales with how much the persona can
        # afford so the first offer isn't laughably high or low.
        budget = max(2, int(self.current_npc.persona.get("budget_gold", 12)))
        self._gossip_sell_offer = max(2, min(8, budget // 3))
        self._refresh_gossip_sell_modal()

    def _refresh_gossip_sell_modal(self) -> None:
        if self._gossip_sell_text is None or self.current_npc is None:
            return
        rumour = self._gossip_sell_text
        offer = max(1, self._gossip_sell_offer)
        modal_rect = self.modal.rect
        body = (
            f"You hint to {self.current_npc.name} that you've heard a "
            "rumour about them, and offer to share it for a price.\n\n"
            f"Rumour: \"{rumour}\"\n\n"
            f"Your asking price: {offer} gold"
        )

        step_y = modal_rect.bottom - 130
        step_specs = [
            ("-5", lambda: self._adjust_gossip_offer(-5)),
            ("-1", lambda: self._adjust_gossip_offer(-1)),
            ("+1", lambda: self._adjust_gossip_offer(+1)),
            ("+5", lambda: self._adjust_gossip_offer(+5)),
        ]
        sw_btn = 60
        gap = 12
        total_w = len(step_specs) * sw_btn + (len(step_specs) - 1) * gap
        sx = modal_rect.centerx - total_w // 2
        step_buttons: list[Button] = []
        for i, (label, cb) in enumerate(step_specs):
            step_buttons.append(
                Button(
                    label=label,
                    rect=pygame.Rect(sx + i * (sw_btn + gap), step_y, sw_btn, 38),
                    on_click=cb,
                )
            )
        offer_btn = Button(
            f"Sell for {offer} gold",
            pygame.Rect(modal_rect.left + 20, modal_rect.bottom - 70, 240, 44),
            self._confirm_gossip_offer,
        )
        back_btn = Button(
            "Back",
            pygame.Rect(modal_rect.left + 280, modal_rect.bottom - 70, 100, 44),
            self._reopen_gossip_modal,
        )
        cancel_btn = Button(
            "Cancel",
            pygame.Rect(modal_rect.right - 140, modal_rect.bottom - 70, 120, 44),
            self._cancel_gossip_sell,
        )
        self.modal.show(
            "Sell a rumour",
            body,
            step_buttons + [offer_btn, back_btn, cancel_btn],
        )

    def _adjust_gossip_offer(self, delta: int) -> None:
        self._gossip_sell_offer = max(1, self._gossip_sell_offer + delta)
        self._refresh_gossip_sell_modal()

    def _cancel_gossip_sell(self) -> None:
        self._gossip_sell_text = None
        self._gossip_sell_offer = 5
        self.modal.hide()

    def _reopen_gossip_modal(self) -> None:
        """Back from the price modal — return to the gossip list."""
        self._gossip_sell_text = None
        self._show_gossip_modal()

    def _confirm_gossip_offer(self) -> None:
        if self._gossip_sell_text is None or self.current_npc is None:
            return
        rumour = self._gossip_sell_text
        price = max(1, self._gossip_sell_offer)
        self._gossip_sell_text = None
        self._gossip_sell_offer = 5
        self.modal.hide()
        self._start_gossip_sell(rumour, price)

    def _start_gossip_sell(self, rumour_text: str, offered_price: int) -> None:
        if self.streaming or self.current_npc is None:
            return
        self.streaming = True
        self.text_input.set_active(False)
        self.dialogue.add(
            "You",
            f"(leans in, offers a rumour for {offered_price} gold)",
        )
        threading.Thread(
            target=self._gossip_sell_worker,
            args=(rumour_text, offered_price),
            daemon=True,
        ).start()

    def _gossip_sell_worker(self, rumour_text: str, offered_price: int) -> None:
        assert self.current_npc is not None
        npc = self.current_npc
        budget = int(npc.persona.get("budget_gold", 10))
        # Floor stays low so the model is allowed to take a cheap deal
        # if the rumour looks tame.
        floor = 1
        messages = P.build_gossip_buy_messages(
            npc.persona,
            self.world.to_prompt_dict(),
            rumour_text,
            offered_price,
        )
        try:
            decision, ok = call_with_retry(
                lambda: self.client.json_call(
                    messages, schema_hint="HaggleDecision"
                ),
                lambda raw: parse_haggle(
                    raw,
                    offered_price=offered_price,
                    persona_budget=budget,
                    persona_floor=floor,
                ),
                fallback=DEGRADED_HAGGLE,
            )
            self.event_q.put(
                GossipSellResultEvent(
                    decision=decision,
                    rumour_text=rumour_text,
                    offered_price=offered_price,
                    ok=ok,
                )
            )
        except OllamaError as exc:
            self.event_q.put(ErrorEvent(message=str(exc)))

    def _on_gossip_sell_result(self, ev: GossipSellResultEvent) -> None:
        """Apply the NPC's decision to the world state.

        Accept   -> +price gold, rumour removed from gossip_heard (it's
                    been "burned"), -1 townsfolk reputation (selling
                    customers out is bad for the tavern's name).
        Counter  -> toast tells the player; they can re-open the gossip
                    list and offer the new price.
        Walk away-> no transaction; the rumour stays.
        """
        if self.current_npc is None:
            self.streaming = False
            self.text_input.set_active(True)
            return
        self.dialogue.finalize_streaming()
        self.streaming = False
        self.text_input.set_active(True)
        decision = ev.decision
        self.dialogue.add(self.current_npc.name, decision.line)
        if decision.accept:
            self.world.add_gold(ev.offered_price)
            self.world.adjust_reputation("townsfolk", -1)
            if ev.rumour_text in self.world.gossip_heard:
                self.world.gossip_heard.remove(ev.rumour_text)
            self.world.save()
            self.sfx.play("coin")
            self.toasts.push(
                f"Sold the rumour for {ev.offered_price}g. "
                "(-1 townsfolk)",
                GOOD,
            )
        elif decision.walk_away:
            self.toasts.push(
                f"{self.current_npc.name} isn't biting on that rumour.",
                WARN,
            )
        elif decision.counter_offer is not None:
            self.toasts.push(
                f"Counter-offer: {decision.counter_offer}g. Re-open the "
                "Gossip list to accept or push back.",
                HIGHLIGHT,
            )
        if not ev.ok:
            self.toasts.push("(rumour-sell response degraded)", WARN)

    def _open_sell_picker(self) -> None:
        """Stage 1 of the sell flow: pick which item to offer."""
        if self.streaming or self.current_npc is None:
            self.toasts.push("Wait for the customer's reply first.", WARN)
            return

        modal_rect = self.modal.rect
        body = (
            f"What would you like to offer {self.current_npc.name}?\n"
            "Pick an item, then set your price on the next screen."
        )
        # Two columns of item buttons.
        cols = 2
        col_w = (modal_rect.width - 60) // cols
        row_h = 44
        gap_x = 20
        gap_y = 8
        top = modal_rect.top + 130
        buttons: list[Button] = []
        for i, item in enumerate(self.items):
            row, col = divmod(i, cols)
            bx = modal_rect.left + 20 + col * (col_w + gap_x)
            by = top + row * (row_h + gap_y)
            label = f"{item['name']} ({item['base_price']}g)"
            buttons.append(
                Button(
                    label=label,
                    rect=pygame.Rect(bx, by, col_w, row_h),
                    on_click=(lambda i=item: self._open_sell_price(i)),
                )
            )
        buttons.append(
            Button(
                "Cancel",
                pygame.Rect(modal_rect.right - 140, modal_rect.bottom - 56, 120, 38),
                self.modal.hide,
            )
        )
        self.modal.show("Sell to Customer", body, buttons)

    def _open_sell_price(self, item: dict[str, Any]) -> None:
        """Stage 2 of the sell flow: adjust price, then offer."""
        self._sell_item = item
        self._sell_offer = int(item["base_price"])
        self._refresh_sell_price_modal()

    def _refresh_sell_price_modal(self) -> None:
        if self._sell_item is None or self.current_npc is None:
            return
        item = self._sell_item
        offer = max(1, self._sell_offer)
        body = (
            f"{item['name']}\n"
            f"  {item['description']}\n\n"
            f"Base price:    {item['base_price']} gold\n"
            f"Your offer:    {offer} gold"
        )
        modal_rect = self.modal.rect
        # Stepper row, centred horizontally.
        step_y = modal_rect.bottom - 130
        # Six steppers: -5, -1, current display label, +1, +5
        step_specs = [
            ("-5", lambda: self._adjust_offer(-5)),
            ("-1", lambda: self._adjust_offer(-1)),
            ("+1", lambda: self._adjust_offer(+1)),
            ("+5", lambda: self._adjust_offer(+5)),
        ]
        sw_btn = 60
        gap = 12
        total_w = len(step_specs) * sw_btn + (len(step_specs) - 1) * gap
        sx = modal_rect.centerx - total_w // 2
        buttons: list[Button] = []
        for i, (label, cb) in enumerate(step_specs):
            buttons.append(
                Button(
                    label=label,
                    rect=pygame.Rect(sx + i * (sw_btn + gap), step_y, sw_btn, 38),
                    on_click=cb,
                )
            )
        offer_btn = Button(
            f"Offer {offer} gold",
            pygame.Rect(modal_rect.left + 20, modal_rect.bottom - 70, 240, 44),
            self._confirm_offer,
        )
        back_btn = Button(
            "Back",
            pygame.Rect(modal_rect.left + 280, modal_rect.bottom - 70, 100, 44),
            self._open_sell_picker,
        )
        cancel_btn = Button(
            "Cancel",
            pygame.Rect(modal_rect.right - 140, modal_rect.bottom - 70, 120, 44),
            self._cancel_sell,
        )
        self.modal.show(
            f"Sell {item['name']}",
            body,
            buttons + [offer_btn, back_btn, cancel_btn],
        )

    def _adjust_offer(self, delta: int) -> None:
        self._sell_offer = max(1, self._sell_offer + delta)
        self._refresh_sell_price_modal()

    def _cancel_sell(self) -> None:
        self._sell_item = None
        self._sell_offer = 0
        self.modal.hide()

    def _confirm_offer(self) -> None:
        if self._sell_item is None:
            return
        item_id = self._sell_item["id"]
        price = max(1, self._sell_offer)
        self._sell_item = None
        self._sell_offer = 0
        self.modal.hide()
        self._start_haggle(item_id, price)

    # ------------------------------------------------------------------
    # Chat streaming
    # ------------------------------------------------------------------
    def _start_chat_stream(self, player_input: str) -> None:
        assert self.current_npc is not None
        self.streaming = True
        self.text_input.set_active(False)
        self.dialogue.add(self.current_npc.name, "", streaming=True)
        messages = P.build_chat_messages(
            self.current_npc.persona,
            self.world.to_prompt_dict(),
            self.current_npc.history[:-1],  # last entry is the just-appended user
            player_input,
        )
        threading.Thread(target=self._chat_worker, args=(messages,), daemon=True).start()

    def _chat_worker(self, messages: list[dict[str, str]]) -> None:
        try:
            full = []
            for token in self.client.chat_stream(messages):
                full.append(token)
                self.event_q.put(TokenEvent(token=token))
            self.event_q.put(StreamDoneEvent(full_text="".join(full)))
        except OllamaError as exc:
            self.event_q.put(ErrorEvent(message=str(exc)))

    # ------------------------------------------------------------------
    # Haggle
    # ------------------------------------------------------------------
    def _start_haggle(self, item_id: str, offered_price: int) -> None:
        if self.streaming or self.current_npc is None:
            return
        item = next((i for i in self.items if i["id"] == item_id), None)
        if not item:
            self.toasts.push(f"No such item: {item_id}", WARN)
            return
        if offered_price < 1:
            self.toasts.push("Price must be at least 1 gold.", WARN)
            return
        self._pending_haggle_item = item
        self._pending_haggle_offer = offered_price
        self.streaming = True
        self.text_input.set_active(False)
        self.dialogue.add(
            "You",
            f"(offers {item['name']} for {offered_price} gold)",
        )
        threading.Thread(
            target=self._haggle_worker,
            args=(item, offered_price),
            daemon=True,
        ).start()

    def _haggle_worker(self, item: dict[str, Any], offered_price: int) -> None:
        assert self.current_npc is not None
        npc = self.current_npc
        floor = max(1, int(item["base_price"] * npc.persona["haggle_floor_pct"]))
        budget = int(npc.persona["budget_gold"])
        messages = P.build_haggle_messages(
            npc.persona,
            self.world.to_prompt_dict(),
            item,
            offered_price,
            npc.haggle_history,
        )
        try:
            decision, ok = call_with_retry(
                lambda: self.client.json_call(messages, schema_hint="HaggleDecision"),
                lambda raw: parse_haggle(
                    raw,
                    offered_price=offered_price,
                    persona_budget=budget,
                    persona_floor=floor,
                ),
                fallback=DEGRADED_HAGGLE,
            )
            self.event_q.put(
                HaggleResultEvent(
                    decision=decision,
                    item_id=item["id"],
                    offered_price=offered_price,
                    ok=ok,
                )
            )
        except OllamaError as exc:
            self.event_q.put(ErrorEvent(message=str(exc)))

    # ------------------------------------------------------------------
    # Quest
    # ------------------------------------------------------------------
    def _request_quest(self) -> None:
        if self.streaming or self.current_npc is None:
            return
        self.streaming = True
        self.text_input.set_active(False)
        self.dialogue.add("You", "(asks if there's any work going)")
        threading.Thread(target=self._quest_worker, daemon=True).start()

    def _quest_worker(self) -> None:
        assert self.current_npc is not None
        messages = P.build_quest_messages(
            self.current_npc.persona,
            self.world.to_prompt_dict(),
        )
        try:
            quest, ok = call_with_retry(
                lambda: self.client.json_call(messages, schema_hint="Quest"),
                parse_quest,
                fallback=DEGRADED_QUEST,
            )
            self.event_q.put(QuestResultEvent(quest=quest, ok=ok))
        except OllamaError as exc:
            self.event_q.put(ErrorEvent(message=str(exc)))

    # ------------------------------------------------------------------
    # Next customer
    # ------------------------------------------------------------------
    def _next_customer(self) -> None:
        if self.current_npc:
            self.world.mark_persona_served(self.current_npc.id)
            self.world.save()
        self._spawn_next_customer()
        self._refresh_action_buttons()

    # ------------------------------------------------------------------
    # Mode transitions + action-panel refresh
    # ------------------------------------------------------------------
    def _refresh_action_buttons(self) -> None:
        """Rebuild the side action buttons for the current mode.

        Called whenever the mode changes or the active-quest list
        changes so the player only ever sees buttons that make sense
        right now (e.g. "Leave the bar" is hidden until they have a
        quest, and the bar-only buttons disappear in exploration).
        """
        if self.mode == MODE_TAVERN:
            buttons = [
                ("Show stock", self._show_stock_modal),
                ("Sell item...", self._open_sell_picker),
                ("Ask for work", self._request_quest),
                ("View quests", self._show_quests_modal),
                ("View gossip", self._show_gossip_modal),
                ("Next customer", self._next_customer),
                ("Save game", self._save_game),
            ]
            if self.world.active_quests:
                buttons.append(("Leave the bar", self._enter_world_map))
            buttons.append(("Help", self._show_help))
        elif self.mode == MODE_WORLD_MAP:
            buttons = [
                ("Back to bar", self._return_to_tavern),
                ("Save game", self._save_game),
                ("Help", self._show_help),
            ]
        else:  # MODE_LOCATION
            buttons = [
                ("Back to map", self._enter_world_map),
                ("Back to bar", self._return_to_tavern),
                ("Save game", self._save_game),
                ("Help", self._show_help),
            ]
        self.actions.set_buttons(buttons)

    def _enter_world_map(self) -> None:
        if self.streaming or self.modal.visible:
            return
        self.mode = MODE_WORLD_MAP
        self.text_input.set_active(False)
        self.world_map_scene.set_active_locations(self.world.active_location_ids())
        self._refresh_action_buttons()
        self.toasts.push("You step out into the lane.", HIGHLIGHT)

    def _enter_location(self, location_id: str) -> None:
        if self.streaming or self.modal.visible:
            return
        self.mode = MODE_LOCATION
        self.current_location_id = location_id
        self.location_scene.set_location(location_id)
        self.location_scene.set_quests(self.world.quests_at(location_id))
        self.text_input.set_active(False)
        # Reset the per-hotspot wrong-click counter so each visit starts
        # fresh; the sass only escalates within a single sitting.
        self._wrong_click_counts = {}
        self._refresh_action_buttons()
        loc = get_location(location_id)
        self.toasts.push(f"You arrive at {loc['name']}.", HIGHLIGHT)

    def _return_to_tavern(self) -> None:
        if self.streaming:
            return
        self.mode = MODE_TAVERN
        self.current_location_id = None
        if self.current_npc is not None and not self.modal.visible:
            self.text_input.set_active(True)
        self._refresh_action_buttons()

    # ------------------------------------------------------------------
    # Per-frame: drain the worker queue
    # ------------------------------------------------------------------
    def _drain_events(self) -> None:
        while True:
            try:
                ev = self.event_q.get_nowait()
            except queue.Empty:
                break
            if isinstance(ev, TokenEvent):
                self.dialogue.append_to_last(ev.token)
            elif isinstance(ev, StreamDoneEvent):
                self.dialogue.finalize_streaming()
                self.streaming = False
                self.text_input.set_active(True)
                if self.current_npc is not None:
                    self.current_npc.append_assistant(ev.full_text)
                    self._extract_gossip(ev.full_text)
                if self.demo_mode:
                    self._demo_step_pending = False
            elif isinstance(ev, HaggleResultEvent):
                self._on_haggle_result(ev)
            elif isinstance(ev, QuestResultEvent):
                self._on_quest_result(ev)
            elif isinstance(ev, FoundResultEvent):
                self._on_found_result(ev)
            elif isinstance(ev, GossipSellResultEvent):
                self._on_gossip_sell_result(ev)
            elif isinstance(ev, OllamaStatusEvent):
                self._on_ollama_status(ev)
            elif isinstance(ev, _OllamaReadyMarker):
                self._ollama_ready = True
            elif isinstance(ev, ErrorEvent):
                self.dialogue.finalize_streaming()
                self.streaming = False
                if self.mode == MODE_TAVERN:
                    self.text_input.set_active(True)
                self.toasts.push(f"LLM error: {ev.message}", WARN)
                self._pending_found_quest = None
                if self.demo_mode:
                    self._demo_step_pending = False

    def _on_haggle_result(self, ev: HaggleResultEvent) -> None:
        assert self.current_npc is not None
        self.dialogue.finalize_streaming()
        self.streaming = False
        self.text_input.set_active(True)
        decision = ev.decision
        item = next((i for i in self.items if i["id"] == ev.item_id), None)
        item_name = item["name"] if item else ev.item_id

        self.dialogue.add(self.current_npc.name, decision.line)
        self.current_npc.haggle_history.append(
            {"price": ev.offered_price, "line": decision.line, "accepted": decision.accept}
        )

        if decision.accept:
            self.world.add_gold(ev.offered_price)
            self.world.adjust_reputation("townsfolk", 1)
            self.world.save()
            self.sfx.play("coin")
            self.toasts.push(
                f"Sold {item_name} for {ev.offered_price}g. (+1 townsfolk)", GOOD
            )
        elif decision.walk_away:
            self.toasts.push(
                f"{self.current_npc.name} walks away from the deal.", WARN
            )
        elif decision.counter_offer is not None:
            self.toasts.push(
                f"Counter-offer: {decision.counter_offer}g. Use Sell item... to reply.",
                HIGHLIGHT,
            )
        if not ev.ok:
            self.toasts.push("(haggle response degraded)", WARN)

    def _on_quest_result(self, ev: QuestResultEvent) -> None:
        assert self.current_npc is not None
        self.dialogue.finalize_streaming()
        self.streaming = False
        self.text_input.set_active(True)
        q = ev.quest
        loc = get_location(q.location)
        self.dialogue.add(
            self.current_npc.name,
            f"{q.summary} (Reward: {q.reward_gold}g, danger: {q.danger}; "
            f"try {loc['name']})",
        )
        self.world.add_active_quest(
            {
                "title": q.title,
                "summary": q.summary,
                "target": q.target,
                "reward_gold": q.reward_gold,
                "danger": q.danger,
                "location": q.location,
                "hotspot": q.hotspot,
                "from_persona": self.current_npc.id,
            }
        )
        self.world.save()
        self.sfx.play("quest")
        self.toasts.push(f"New quest: {q.title}", HIGHLIGHT)
        self._refresh_action_buttons()
        if not ev.ok:
            self.toasts.push("(quest response degraded)", WARN)

    def _on_found_result(self, ev: FoundResultEvent) -> None:
        """Resolve the found-it micro-call: deposit reward, set up return."""
        self.streaming = False
        quest = self._pending_found_quest
        self._pending_found_quest = None
        if quest is None:
            return
        line = ev.found.line.strip()
        speaker = "Narrator"
        # Append to dialogue history so the player sees continuity when
        # they get back to the bar.
        self.dialogue.add(speaker, line)
        # Mark the quest complete + reward + reputation tick.
        done = self.world.complete_quest(quest.get("title", ""))
        if done is not None:
            reward = int(done.get("reward_gold", 0))
            self.world.adjust_reputation("townsfolk", 1)
            self.world.save()
            self.sfx.play("quest")
            self.toasts.push(
                f"Quest complete: {done.get('title', '???')} (+{reward}g)",
                GOOD,
            )
        if not ev.ok:
            self.toasts.push("(found-line degraded)", WARN)
        # Brief celebration pause, then auto-return to the bar.
        self._return_to_tavern_at = time.monotonic() + 1.6
        self._refresh_action_buttons()
        if not ev.ok:
            self.toasts.push("(quest response degraded)", WARN)

    # ------------------------------------------------------------------
    # Gossip extraction
    # ------------------------------------------------------------------
    def _extract_gossip(self, text: str) -> None:
        """Cheap heuristic gossip detection.

        We do not run another LLM call to mine gossip — that would double
        latency for every line. Instead we look for sentences that
        mention rumour-y phrases. False positives are fine; the gossip
        list is capped and surfaced back to later NPCs as flavour.
        """
        triggers = ("rumour", "rumor", "they say", "i heard", "word is", "word has it")
        lowered = text.lower()
        if any(t in lowered for t in triggers):
            for sentence in text.split("."):
                s = sentence.strip()
                if 8 < len(s) < 180 and any(t in s.lower() for t in triggers):
                    if self.world.add_gossip(s):
                        self.toasts.push(f"Gossip noted: {s[:60]}...", HIGHLIGHT)
                        self.world.save()
                    break

    # ------------------------------------------------------------------
    # Settings modal (model picker + temperature + reset)
    # ------------------------------------------------------------------
    def _open_settings(self) -> None:
        models = self.client.list_models() or [self.client.config.model]
        body_lines = [
            f"Current model: {self.client.config.model}",
            f"Chat temperature: {self.client.config.chat_temperature:.2f}",
            f"JSON temperature: {self.client.config.json_temperature:.2f}",
            f"Banner: {'on' if self.banner.visible else 'off'}",
            "",
            "Models found locally:",
        ]
        for m in models[:6]:
            body_lines.append(f"  - {m}")
        body = "\n".join(body_lines)

        modal_rect = self.modal.rect
        bx = modal_rect.left + 20
        by1 = modal_rect.bottom - 110
        by2 = modal_rect.bottom - 60
        bw, bh = 130, 38
        regen_enabled = self._can_regenerate()
        buttons = [
            Button("Cycle model", pygame.Rect(bx, by1, bw, bh), self._cycle_model),
            Button("Temp -", pygame.Rect(bx + bw + 10, by1, 80, bh), self._temp_down),
            Button("Temp +", pygame.Rect(bx + bw + 100, by1, 80, bh), self._temp_up),
            Button(
                "Toggle banner",
                pygame.Rect(bx + bw + 200, by1, 160, bh),
                self._toggle_banner,
            ),
            Button(
                "Regenerate last reply",
                pygame.Rect(bx, by2, 220, bh),
                self._regenerate_last_reply,
                enabled=regen_enabled,
            ),
            Button(
                "Close",
                pygame.Rect(modal_rect.right - bw - 20, by2, bw, bh),
                self.modal.hide,
            ),
        ]
        self.modal.show("Settings", body, buttons)

    def _cycle_model(self) -> None:
        models = self.client.list_models() or [self.client.config.model]
        if self.client.config.model in models:
            i = models.index(self.client.config.model)
            self.client.config.model = models[(i + 1) % len(models)]
        else:
            self.client.config.model = models[0]
        self.toasts.push(f"Model: {self.client.config.model}", HIGHLIGHT)
        self._open_settings()

    def _temp_up(self) -> None:
        self.client.config.chat_temperature = min(1.5, self.client.config.chat_temperature + 0.1)
        self._open_settings()

    def _temp_down(self) -> None:
        self.client.config.chat_temperature = max(0.0, self.client.config.chat_temperature - 0.1)
        self._open_settings()

    def _toggle_banner(self) -> None:
        self.banner.toggle()
        self._open_settings()

    def _can_regenerate(self) -> bool:
        if self.streaming or self.current_npc is None:
            return False
        # Need at least one user/assistant pair in history.
        roles = [m["role"] for m in self.current_npc.history]
        return "assistant" in roles and "user" in roles

    def _regenerate_last_reply(self) -> None:
        """Pop the last assistant turn and re-issue the chat call.

        Useful when the model produces a flat or off-tone line; the player
        can ask for another take without retyping their prompt.
        """
        if not self._can_regenerate() or self.current_npc is None:
            return
        # Pop trailing assistant turn(s).
        while self.current_npc.history and self.current_npc.history[-1]["role"] == "assistant":
            self.current_npc.history.pop()
        if not self.current_npc.history:
            return
        last_user = self.current_npc.history[-1]["content"]
        # Drop the most recent dialogue line in the box too if it was the NPC.
        if self.dialogue.lines and self.dialogue.lines[-1].speaker == self.current_npc.name:
            self.dialogue.lines.pop()
        self.modal.hide()
        self.toasts.push("Regenerating reply...", HIGHLIGHT)
        # Re-run the chat path. Start fresh streaming line.
        self.streaming = True
        self.text_input.set_active(False)
        self.dialogue.add(self.current_npc.name, "", streaming=True)
        # Build messages excluding the trailing user we just kept (it goes
        # into the user slot of the prompt).
        history = self.current_npc.history[:-1]
        messages = P.build_chat_messages(
            self.current_npc.persona,
            self.world.to_prompt_dict(),
            history,
            last_user,
        )
        threading.Thread(target=self._chat_worker, args=(messages,), daemon=True).start()

    # ------------------------------------------------------------------
    # Demo mode scripting
    # ------------------------------------------------------------------
    def _build_demo_script(self) -> list[str]:
        """Fixed sequence of player inputs for reproducible video evidence."""
        base = [
            "Welcome to the Goblet. What brings you in tonight?",
            "Quiet night. Hear any rumours on the road?",
            "/sell strong_stout 5",
            "/quest",
        ]
        return base[: self.demo_turns]

    def _drive_demo(self) -> None:
        """Pump one scripted input per LLM idle frame."""
        if self._demo_step_pending or self.streaming:
            return
        if not self._demo_script:
            self._finish_demo()
            return
        next_input = self._demo_script.pop(0)
        self._demo_step_pending = True
        # Display the line as if the player typed it.
        self.text_input.text = next_input
        self.text_input.cursor = len(next_input)
        # Submit on the next frame so the user can see the line appear.
        pygame.time.set_timer(pygame.USEREVENT + 1, 600, loops=1)

    def _finish_demo(self) -> None:
        log_path = Path("demo_log_" + time.strftime("%Y%m%d_%H%M%S") + ".jsonl")
        prompt_log_path = Path("prompt_log_" + time.strftime("%Y%m%d_%H%M%S") + ".jsonl")
        self.client.dump_log_jsonl(str(prompt_log_path))
        with open(log_path, "w", encoding="utf-8") as fh:
            for line in self.dialogue.lines:
                fh.write(json.dumps({"speaker": line.speaker, "text": line.text}) + "\n")
        print(f"[demo] dialogue log -> {log_path}")
        print(f"[demo] prompt log   -> {prompt_log_path}")
        pygame.event.post(pygame.event.Event(pygame.QUIT))

    # ------------------------------------------------------------------
    # Per-mode event routing + drawing
    # ------------------------------------------------------------------
    def _handle_scene_event(self, event: pygame.event.Event) -> None:
        if self.mode == MODE_TAVERN:
            # Dialogue scroll bar / wheel only matter in the bar.
            self.dialogue.handle_event(event)
            return
        if self.streaming:
            return
        if self.mode == MODE_WORLD_MAP:
            location_id = self.world_map_scene.handle_event(event)
            if location_id is not None:
                self._enter_location(location_id)
            return
        if self.mode == MODE_LOCATION:
            hotspot_id = self.location_scene.handle_event(event)
            if hotspot_id is None or event.type != pygame.MOUSEBUTTONDOWN:
                return
            self._on_hotspot_click(hotspot_id)

    def _draw_tavern_frame(self) -> None:
        self.scene.draw(self.screen)
        self.dialogue.draw(self.screen)
        self.text_input.draw(self.screen)

    def _draw_world_map_frame(self) -> None:
        # Refresh active highlights each frame in case quests changed.
        self.world_map_scene.set_active_locations(self.world.active_location_ids())
        self.world_map_scene.draw(self.screen)

    def _draw_location_frame(self) -> None:
        if self.current_location_id is None:
            return
        self.location_scene.set_quests(self.world.quests_at(self.current_location_id))
        self.location_scene.draw(self.screen)

    # ------------------------------------------------------------------
    # Hotspot click -> found-it flow / wrong-click feedback
    # ------------------------------------------------------------------
    def _on_hotspot_click(self, hotspot_id: str) -> None:
        if self.current_location_id is None or self.streaming:
            return
        # Is this hotspot the target of any active quest at this location?
        match = None
        for q in self.world.quests_at(self.current_location_id):
            if q.get("hotspot") == hotspot_id:
                match = q
                break
        if match is None:
            self._handle_wrong_hotspot(hotspot_id)
            return
        self._start_found_flow(match, hotspot_id)

    def _handle_wrong_hotspot(self, hotspot_id: str) -> None:
        loc_id = self.current_location_id or ""
        hotspot = get_hotspot(loc_id, hotspot_id) or {"name": "this spot"}
        # Bump the per-(location, hotspot) click count and pick a line
        # from the appropriate sass bucket. The last bucket is reused
        # indefinitely with a random pick for stubborn players.
        key = (loc_id, hotspot_id)
        count = self._wrong_click_counts.get(key, 0)
        self._wrong_click_counts[key] = count + 1
        bucket = min(count, max(WRONG_CLICK_LINES))
        template = random.choice(WRONG_CLICK_LINES[bucket])
        msg = template.format(name=hotspot["name"])
        self.location_scene.show_note(msg)

    def _start_found_flow(self, quest: dict[str, Any], hotspot_id: str) -> None:
        self.streaming = True
        self._pending_found_quest = quest
        loc = get_location(self.current_location_id or "")
        hotspot = get_hotspot(self.current_location_id or "", hotspot_id) or {}
        item_phrase = extract_item_phrase(quest.get("summary", ""))
        persona = (
            self.current_npc.persona
            if self.current_npc is not None
            else {"name": "An old patron", "role": "wanderer", "voice_traits": ["soft-spoken"]}
        )
        threading.Thread(
            target=self._found_worker,
            args=(
                persona,
                quest,
                loc.get("name", "the place"),
                hotspot.get("name", "the spot"),
                item_phrase,
            ),
            daemon=True,
        ).start()

    def _found_worker(
        self,
        persona: dict[str, Any],
        quest: dict[str, Any],
        location_name: str,
        hotspot_name: str,
        item_phrase: str,
    ) -> None:
        messages = P.build_found_messages(
            persona,
            self.world.to_prompt_dict(),
            quest,
            location_name=location_name,
            hotspot_name=hotspot_name,
            item_phrase=item_phrase,
        )
        try:
            found, ok = call_with_retry(
                lambda: self.client.json_call(messages, schema_hint="FoundLine"),
                parse_found_line,
                fallback=DEGRADED_FOUND,
            )
            self.event_q.put(
                FoundResultEvent(
                    quest_title=quest.get("title", ""), found=found, ok=ok
                )
            )
        except OllamaError as exc:
            self.event_q.put(ErrorEvent(message=str(exc)))

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def run(self) -> int:
        self._check_ollama()
        running = True
        while running:
            dt = self.clock.tick(60) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.modal.visible:
                            self.modal.hide()
                        else:
                            running = False
                    elif event.key == pygame.K_F1:
                        self._show_help()
                    elif event.key == pygame.K_F2:
                        self._open_settings()
                    elif event.key == pygame.K_F5:
                        self._next_customer()
                    elif event.key == pygame.K_t and (event.mod & pygame.KMOD_CTRL == 0):
                        # Toggle banner only when input is empty (T as a command).
                        if not self.text_input.text:
                            self.banner.toggle()
                            continue
                        elif self.mode == MODE_TAVERN:
                            self.text_input.handle_event(event)
                    elif event.key == pygame.K_m and (event.mod & pygame.KMOD_CTRL == 0):
                        # Toggle music when the input bar is empty (or
                        # when we're not in chat mode at all). Falls
                        # through to the text input otherwise so the
                        # player can still type the letter m.
                        if not self.text_input.text or self.mode != MODE_TAVERN:
                            audible = self.music.toggle_mute()
                            self.toasts.push(
                                "Music: on" if audible else "Music: off",
                                HIGHLIGHT,
                            )
                            continue
                        elif self.mode == MODE_TAVERN:
                            self.text_input.handle_event(event)
                    else:
                        # Text input is only meaningful in tavern mode.
                        if not self.modal.visible and self.mode == MODE_TAVERN:
                            self.text_input.handle_event(event)
                elif event.type == pygame.USEREVENT + 1:
                    # Demo: submit the scripted line.
                    if self.demo_mode:
                        text = self.text_input.text
                        self.text_input.text = ""
                        self.text_input.cursor = 0
                        self._on_player_submit(text)
                else:
                    # Modal eats events first. If it's visible at all, the
                    # action panel and exploration scenes are locked out so
                    # clicks outside the modal don't accidentally fire.
                    self.modal.handle_event(event)
                    if not self.modal.visible:
                        if not self.actions.handle_event(event):
                            self._handle_scene_event(event)

            self._drain_events()
            # Auto-return to the tavern after a celebrated quest completion.
            if (
                self._return_to_tavern_at is not None
                and time.monotonic() >= self._return_to_tavern_at
            ):
                self._return_to_tavern_at = None
                self._return_to_tavern()
            # Reflect streaming state in the side panel so buttons are
            # clearly unavailable while the LLM is busy.
            self.actions.set_enabled_all(not self.streaming)

            if self.demo_mode:
                self._drive_demo()

            self.text_input.update(dt)

            self.screen.fill((0, 0, 0))
            if self.mode == MODE_TAVERN:
                self._draw_tavern_frame()
            elif self.mode == MODE_WORLD_MAP:
                self._draw_world_map_frame()
            else:
                self._draw_location_frame()
            self.banner.draw(self.screen, self.client.config.model)
            self.status_bar.draw(
                self.screen,
                gold=self.world.gold,
                reputation=self.world.reputation,
                active_quests=len(self.world.active_quests),
                gossip_count=len(self.world.gossip_heard),
                model_name=self.client.config.model,
            )
            self.actions.draw(self.screen)
            self.toasts.draw(self.screen)
            self.modal.draw(self.screen)
            self._draw_corner_help()
            pygame.display.flip()

        self.world.save()
        self.music.dispose()
        pygame.quit()
        return 0

    def _draw_corner_help(self) -> None:
        font = load_font(14)
        text = "F1 help   F2 settings   F5 next customer   T banner   Esc quit"
        surf = font.render(text, True, (180, 140, 70))
        self.screen.blit(surf, (20, SCREEN_SIZE[1] - 18))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument(
        "--model",
        default="llama3.2:3b",
        help="Ollama model tag (default: llama3.2:3b)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional fixed seed for reproducible LLM output",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run a scripted demo session and dump prompt/response logs",
    )
    parser.add_argument(
        "--persona",
        default="broke_bard",
        help="Persona to spawn first in --demo mode",
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=4,
        help="How many scripted turns to run in --demo mode",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return Game(args).run()


if __name__ == "__main__":
    sys.exit(main())
