"""Wholesale stock for the tavern (buy from town market, not NPC haggles)."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_TAVERN_SUPPLIES: dict[str, int] = {
    "ale_stock": 20,
    "wine_stock": 6,
    "provisions": 25,
    "fuel": 15,
}


@dataclass(frozen=True)
class MarketOffer:
    supply_key: str
    blurb: str
    add_qty: int
    price_gold: int


MARKET_OFFERS: tuple[MarketOffer, ...] = (
    MarketOffer(
        "ale_stock",
        "Small ale cask — tops up the common taps.",
        12,
        10,
    ),
    MarketOffer(
        "wine_stock",
        "Southern wine crate — for fussier cups.",
        6,
        22,
    ),
    MarketOffer(
        "provisions",
        "Salted meat, roots, and flour for the kettle.",
        15,
        14,
    ),
    MarketOffer(
        "fuel",
        "Lamp oil, tallow candles, and dry kindling.",
        10,
        9,
    ),
)
