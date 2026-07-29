"""Persistent book catalog for the integration, saved via Home Assistant's Store.

Wraps the pure ``catalog`` logic with load/save and the mutations the rate /
assign services need. One store per config entry (keyed by entry id).
"""

from __future__ import annotations

from typing import Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from . import catalog
from .const import DOMAIN
from .models import Account

STORAGE_VERSION = 1


class CatalogStore:
    """Load, mutate and persist the book catalog for one config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.catalog"
        )
        self.catalog: catalog.Catalog = {}

    async def async_load(self) -> None:
        self.catalog = await self._store.async_load() or {}

    async def async_save(self) -> None:
        await self._store.async_save(self.catalog)

    def ingest(self, accounts: list[Account]) -> None:
        """Fold current loans and loan history into the catalog (in memory)."""
        for account in accounts:
            for loan in account.loans:
                catalog.upsert(
                    self.catalog,
                    title=loan.title,
                    author=loan.author,
                    isbn=loan.isbn,
                    doc_type=loan.doc_type,
                    source="loan",
                    card_name=account.name,
                )
            for item in account.history:
                catalog.upsert(
                    self.catalog,
                    title=item.title,
                    author=item.author,
                    isbn=item.isbn,
                    doc_type=item.doc_type,
                    source="history",
                    card_name=account.name,
                    library_rating=item.library_rating,
                )

    async def async_ingest(self, accounts: list[Account]) -> None:
        before = _fingerprint(self.catalog)
        self.ingest(accounts)
        if _fingerprint(self.catalog) != before:
            await self.async_save()

    async def async_rate(
        self, book_id: str, person: str, stars: Optional[int]
    ) -> bool:
        changed = catalog.set_rating(self.catalog, book_id, person, stars)
        if changed:
            await self.async_save()
        return changed

    async def async_assign(
        self, book_id: str, person: str, assigned: bool = True
    ) -> bool:
        changed = catalog.assign(self.catalog, book_id, person, assigned)
        if changed:
            await self.async_save()
        return changed

    def has(self, book_id: str) -> bool:
        return book_id in self.catalog


def _fingerprint(cat: catalog.Catalog) -> tuple:
    """Cheap change-detector so we only write storage when something changed."""
    return tuple(
        (bid, e.get("seen_count"), e.get("last_seen")) for bid, e in sorted(cat.items())
    )
