"""Canonical world map data.

Pure-Python module with no `pygame` import. Lives apart from
``world_map.py`` (which owns the scene classes) so that
``src/llm/parsers.py`` can validate Quest fields against the
location/hotspot tables without forcing every test runner to pull in
pygame.

Each location has:
- ``id``       : machine-readable identifier (used by the Quest schema).
- ``name``     : in-fiction display name.
- ``blurb``    : one-line description (shown on the world-map card and
                 injected into the quest-generation prompt).
- ``palette``  : drives the procedural art in ``world_map.py``.
- ``hotspots`` : four hand-authored search targets, each with
                 ``{id, name, pos}`` where ``pos`` is normalised
                 ``(x, y)`` coordinates inside the location's canvas.
"""

from __future__ import annotations

from typing import Any


# Default fallback used when a quest's location/hotspot is unknown.
DEFAULT_LOCATION_ID = "outskirts"
DEFAULT_HOTSPOT_ID = "creek_bed"

# Regions where quests may place objectives. Wholesale Row is UI-only for
# buying stock and must not appear as an LLM quest ``location``.
QUEST_LOCATION_IDS: tuple[str, ...] = (
    "mines",
    "town",
    "outskirts",
    "castle_hall",
)

WHOLESALE_MARKET_ID = "wholesale_market"


LOCATIONS: dict[str, dict[str, Any]] = {
    "mines": {
        "id": "mines",
        "name": "The Old Mines",
        "blurb": "Dark tunnels east of town, abandoned twenty years.",
        "palette": "stone",
        "hotspots": [
            {"id": "main_shaft",       "name": "Main Shaft",         "pos": (0.20, 0.62)},
            {"id": "collapsed_tunnel", "name": "Collapsed Tunnel",   "pos": (0.50, 0.40)},
            {"id": "miner_cart",       "name": "Rusty Miner's Cart", "pos": (0.72, 0.70)},
            {"id": "underground_pool", "name": "Underground Pool",   "pos": (0.86, 0.50)},
        ],
    },
    "town": {
        "id": "town",
        "name": "Town Square",
        "blurb": "Cobbled square, market stalls, the apothecary.",
        "palette": "warm",
        "hotspots": [
            {"id": "market_stalls", "name": "Market Stalls",   "pos": (0.28, 0.55)},
            {"id": "apothecary",    "name": "Apothecary",      "pos": (0.58, 0.50)},
            {"id": "fountain",      "name": "Old Fountain",    "pos": (0.45, 0.72)},
            {"id": "alley",         "name": "Narrow Alley",    "pos": (0.82, 0.45)},
        ],
    },
    "outskirts": {
        "id": "outskirts",
        "name": "The Outskirts",
        "blurb": "Forest edge, hunters' tracks, a broken bridge.",
        "palette": "forest",
        "hotspots": [
            {"id": "broken_bridge", "name": "Broken Bridge", "pos": (0.22, 0.55)},
            {"id": "hunters_blind", "name": "Hunter's Blind", "pos": (0.55, 0.60)},
            {"id": "old_oak",       "name": "Old Oak",        "pos": (0.40, 0.38)},
            {"id": "creek_bed",     "name": "Creek Bed",      "pos": (0.80, 0.70)},
        ],
    },
    "castle_hall": {
        "id": "castle_hall",
        "name": "Castle Hall",
        "blurb": "Stone halls, tapestries, the dais and throne.",
        "palette": "cold",
        "hotspots": [
            {"id": "dais",           "name": "The Dais",            "pos": (0.50, 0.40)},
            {"id": "tapestry",       "name": "Tapestried Alcove",   "pos": (0.22, 0.55)},
            {"id": "armoury",        "name": "Side Armoury",        "pos": (0.74, 0.50)},
            {"id": "servants_door",  "name": "Servants' Door",      "pos": (0.85, 0.72)},
        ],
    },
    WHOLESALE_MARKET_ID: {
        "id": WHOLESALE_MARKET_ID,
        "name": "Wholesale Row",
        "blurb": "Bulk importers — restock ale, wine, kitchen, and fuel.",
        "palette": "bazaar",
        "hotspots": [
            {"id": "importers_stall", "name": "Importers' Stall", "pos": (0.50, 0.58)},
        ],
    },
}


def location_ids() -> list[str]:
    """Return ids valid for quests and story exploration (excludes services)."""
    return list(QUEST_LOCATION_IDS)


def map_destination_ids() -> list[str]:
    """Ordered list of every world-map card, including Wholesale Row."""
    return list(QUEST_LOCATION_IDS) + [WHOLESALE_MARKET_ID]


def get_location(location_id: str) -> dict[str, Any]:
    """Return the location dict, falling back to the default location."""
    return LOCATIONS.get(location_id, LOCATIONS[DEFAULT_LOCATION_ID])


def hotspot_ids(location_id: str) -> list[str]:
    """Return the valid hotspot ids for a location."""
    return [h["id"] for h in get_location(location_id)["hotspots"]]


def get_hotspot(location_id: str, hotspot_id: str) -> dict[str, Any] | None:
    """Return a hotspot dict or None if not in this location."""
    for h in get_location(location_id)["hotspots"]:
        if h["id"] == hotspot_id:
            return h
    return None


def render_locations_for_prompt() -> str:
    """Format the locations table for inclusion in an LLM system prompt."""
    lines: list[str] = []
    for loc_id in QUEST_LOCATION_IDS:
        loc = LOCATIONS[loc_id]
        lines.append(f"- {loc['id']} ({loc['name']}): {loc['blurb']}")
        lines.append("    hotspots:")
        for h in loc["hotspots"]:
            lines.append(f"      - {h['id']} ({h['name']})")
    return "\n".join(lines)
