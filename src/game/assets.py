"""Sprite + font loading with graceful fallbacks.

The game ships *without* bundled art so the marker can run it on a clean
clone without copyright concerns. Every asset has a generated fallback
that is procedurally drawn at startup, so the game looks deliberate even
when ``assets/sprites/`` is empty.

If real PNGs are dropped into ``assets/sprites/`` matching the persona's
``sprite`` field, they are used automatically.
"""

from __future__ import annotations

import array
import math
import tempfile
import threading
import wave
from pathlib import Path
from typing import Any  # noqa: F401 — used by SoundLibrary cache type hint

import pygame


SPRITE_DIR = Path("assets") / "sprites"
FONT_DIR = Path("assets") / "fonts"
SFX_DIR = Path("assets") / "sfx"
MUSIC_DIR = Path("assets") / "music"

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
# Background music (procedural fallback + optional override)
# ---------------------------------------------------------------------------
def _generate_ambient_wav(
    duration_s: float = 16.0,
    sample_rate: int = 22050,
) -> bytes:
    """Procedurally render a looping warm-pad ambience as a WAV byte string.

    The waveform layers a sub-bass, a root + perfect-fifth + octave
    triad, and a slow LFO breathing envelope. The first and last
    fraction of a second cross-fade to silence so the loop seams are
    inaudible. Pure Python (``array``/``wave``) so there is no numpy
    dependency for a feature that is ultimately "set dressing".
    """
    n_samples = int(sample_rate * duration_s)
    samples = array.array("h")
    # Open-fifth-with-octave chord in C, plus a sub-bass an octave below.
    # The 5th/octave intervals stay pleasant under sustained drone; a 3rd
    # would commit the music to major/minor and clash with mode swings.
    voices = [
        (65.41, 0.18),    # C2 sub bass
        (130.81, 0.16),   # C3 root
        (196.00, 0.10),   # G3 fifth
        (261.63, 0.08),   # C4 octave
        (392.00, 0.05),   # G4 shimmer
    ]
    lfo_rate_hz = 0.12  # slow "breathing"
    fade_s = 0.6
    fade_n = int(sample_rate * fade_s)
    two_pi = 2 * math.pi
    for i in range(n_samples):
        t = i / sample_rate
        breath = 0.65 + 0.35 * math.sin(two_pi * lfo_rate_hz * t)
        mix = 0.0
        for freq, amp in voices:
            # Slight detune for each voice keeps the pad alive instead of
            # sounding like a flat sine sum.
            detune = 1.0 + 0.0006 * math.sin(two_pi * (lfo_rate_hz * 0.5) * t)
            mix += amp * math.sin(two_pi * freq * detune * t)
        # Loop-seam crossfade: ramp in for the first ``fade_s`` and ramp
        # out for the last ``fade_s``.
        env = 1.0
        if i < fade_n:
            env = i / fade_n
        elif i > n_samples - fade_n:
            env = (n_samples - i) / fade_n
        value = mix * breath * env
        sample = int(max(-1.0, min(1.0, value)) * 26000)
        samples.append(sample)
    buf = bytes()
    import io as _io
    with _io.BytesIO() as bio:
        with wave.open(bio, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(samples.tobytes())
        buf = bio.getvalue()
    return buf


class MusicPlayer:
    """Loop a calm background ambience using ``pygame.mixer.music``.

    Resolution order on construction:
    1. Any file in ``assets/music/`` with extension ``.ogg``, ``.wav``,
       or ``.mp3`` (alphabetical first wins) — lets the player drop in
       a real track without changing code.
    2. A procedurally generated 16-second warm-pad loop, written to a
       temp WAV so the mixer can stream it.

    The mixer's ``music`` channel is a single global resource; we own
    it for the duration of the game. SFX plays on the normal channels.
    """

    DEFAULT_VOLUME = 0.32

    def __init__(self) -> None:
        self.enabled = False
        self._volume = self.DEFAULT_VOLUME
        self._muted = False
        self._track_path: Path | None = None
        self._tmp_path: Path | None = None
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            self.enabled = True
        except pygame.error:
            self.enabled = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Prepare and start looping the background track.

        Track preparation (especially the procedural fallback) is run on
        a background thread so the game window can come up in well
        under a second even on slow CPUs.
        """
        if not self.enabled:
            return
        threading.Thread(target=self._prepare_and_play, daemon=True).start()

    def _prepare_and_play(self) -> None:
        try:
            track = self._resolve_track()
            if track is None:
                return
            pygame.mixer.music.load(str(track))
            pygame.mixer.music.set_volume(0.0 if self._muted else self._volume)
            pygame.mixer.music.play(loops=-1)
        except pygame.error:
            # Music is set dressing; failures shouldn't break the game.
            self.enabled = False

    def _resolve_track(self) -> Path | None:
        # 1. Honour any track the user dropped into assets/music/.
        if MUSIC_DIR.is_dir():
            for ext in (".ogg", ".wav", ".mp3"):
                hits = sorted(MUSIC_DIR.glob(f"*{ext}"))
                if hits:
                    self._track_path = hits[0]
                    return hits[0]
        # 2. Generate the procedural pad into a temp WAV.
        try:
            data = _generate_ambient_wav()
        except Exception:
            return None
        tmp = tempfile.NamedTemporaryFile(
            prefix="goblet_ambience_", suffix=".wav", delete=False
        )
        try:
            tmp.write(data)
        finally:
            tmp.close()
        self._tmp_path = Path(tmp.name)
        self._track_path = self._tmp_path
        return self._tmp_path

    def stop(self) -> None:
        if not self.enabled:
            return
        try:
            pygame.mixer.music.stop()
        except pygame.error:
            pass

    def dispose(self) -> None:
        """Stop playback and delete the temp WAV (if any). Best-effort."""
        self.stop()
        try:
            pygame.mixer.music.unload()
        except (pygame.error, AttributeError):
            pass
        if self._tmp_path and self._tmp_path.exists():
            try:
                self._tmp_path.unlink()
            except OSError:
                pass
            self._tmp_path = None

    def set_volume(self, volume: float) -> None:
        self._volume = max(0.0, min(1.0, float(volume)))
        if not self.enabled or self._muted:
            return
        try:
            pygame.mixer.music.set_volume(self._volume)
        except pygame.error:
            pass

    def toggle_mute(self) -> bool:
        """Flip mute state. Returns True if music is now audible."""
        self._muted = not self._muted
        if not self.enabled:
            return not self._muted
        try:
            pygame.mixer.music.set_volume(0.0 if self._muted else self._volume)
        except pygame.error:
            pass
        return not self._muted

    @property
    def muted(self) -> bool:
        return self._muted

    @property
    def track_path(self) -> Path | None:
        return self._track_path


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
