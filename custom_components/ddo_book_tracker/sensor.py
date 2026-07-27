"""Sensor platform for the DDO Library Book Tracker."""

from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DDOConfigEntry
from .const import DOMAIN
from .coordinator import DDOCoordinator
from .models import Account


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DDOConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one sensor per account plus overall summary sensors."""
    coordinator = entry.runtime_data
    accounts = coordinator.data or []

    entities: list[SensorEntity] = [
        AccountSensor(coordinator, entry, account.account_id)
        for account in accounts
    ]
    entities.append(TotalOnLoanSensor(coordinator, entry))
    entities.append(OverdueSensor(coordinator, entry))
    entities.append(NextDueSensor(coordinator, entry))
    entities.append(ReadyForPickupSensor(coordinator, entry))
    entities.append(ReservedSensor(coordinator, entry))
    async_add_entities(entities)


def _all_loans(accounts: list[Account]):
    return [loan for account in accounts for loan in account.loans]


def _all_reservations(accounts: list[Account]):
    return [res for account in accounts for res in account.reservations]


class _BaseSensor(CoordinatorEntity[DDOCoordinator], SensorEntity):
    """Shared device grouping + attribution."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DDOCoordinator, entry: DDOConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"DDO Library ({entry.title})",
            manufacturer="Dollard-des-Ormeaux Public Library",
            model="Iguana OPAC",
            entry_type=None,
        )

    @property
    def _accounts(self) -> list[Account]:
        return self.coordinator.data or []


class AccountSensor(_BaseSensor):
    """One sensor per (primary or linked) library card."""

    _attr_icon = "mdi:book-multiple"
    _attr_native_unit_of_measurement = "books"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: DDOCoordinator, entry: DDOConfigEntry, account_id: str
    ) -> None:
        super().__init__(coordinator, entry)
        self._account_id = account_id
        self._attr_unique_id = f"{entry.entry_id}_{account_id}"
        account = self._find()
        self._attr_name = account.name if account else account_id

    def _find(self) -> Account | None:
        for account in self._accounts:
            if account.account_id == self._account_id:
                return account
        return None

    @property
    def available(self) -> bool:
        return super().available and self._find() is not None

    @property
    def native_value(self) -> int | None:
        account = self._find()
        return account.item_count if account else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        account = self._find()
        if account is None:
            return {}
        loans = sorted(
            account.loans, key=lambda ln: (ln.due_date or date.max, ln.title)
        )
        reservations = sorted(
            account.reservations,
            key=lambda r: (not r.is_ready, r.queue_position, r.title),
        )
        return {
            "account_name": account.name,
            "is_primary": account.is_primary,
            "next_due_date": account.next_due_date.isoformat()
            if account.next_due_date
            else None,
            "overdue_count": sum(1 for ln in account.loans if ln.is_overdue),
            "reservation_count": len(account.reservations),
            "reservations_ready": account.reservations_ready,
            "books": [
                {
                    "title": ln.title,
                    "author": ln.author,
                    "due_date": ln.due_date.isoformat() if ln.due_date else None,
                    "days_until_due": ln.days_until_due,
                    "is_overdue": ln.is_overdue,
                    "isbn": ln.isbn,
                    "renewable": ln.renewable,
                }
                for ln in loans
            ],
            "reservations": [
                {
                    "title": r.title,
                    "author": r.author,
                    "queue_position": r.queue_position,
                    "is_ready": r.is_ready,
                    "available_until": r.available_until.isoformat()
                    if r.available_until
                    else None,
                    "pickup_location": r.pickup_location,
                    "isbn": r.isbn,
                }
                for r in reservations
            ],
        }


class TotalOnLoanSensor(_BaseSensor):
    """Total items on loan across every account."""

    _attr_icon = "mdi:bookshelf"
    _attr_native_unit_of_measurement = "books"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_name = "Total on loan"

    def __init__(self, coordinator: DDOCoordinator, entry: DDOConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_total_on_loan"

    @property
    def native_value(self) -> int:
        return len(_all_loans(self._accounts))


class OverdueSensor(_BaseSensor):
    """How many items are overdue across every account."""

    _attr_icon = "mdi:alert-circle"
    _attr_native_unit_of_measurement = "books"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_name = "Overdue"

    def __init__(self, coordinator: DDOCoordinator, entry: DDOConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_overdue"

    @property
    def native_value(self) -> int:
        return sum(1 for ln in _all_loans(self._accounts) if ln.is_overdue)


class NextDueSensor(_BaseSensor):
    """The soonest due date across every account."""

    _attr_icon = "mdi:calendar-clock"
    _attr_device_class = SensorDeviceClass.DATE
    _attr_name = "Next due date"

    def __init__(self, coordinator: DDOCoordinator, entry: DDOConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_next_due"

    @property
    def native_value(self) -> date | None:
        dates = [ln.due_date for ln in _all_loans(self._accounts) if ln.due_date]
        return min(dates) if dates else None


class ReservedSensor(_BaseSensor):
    """Total reservations (holds) placed across every account."""

    _attr_icon = "mdi:bookmark-multiple"
    _attr_native_unit_of_measurement = "holds"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_name = "Reserved"

    def __init__(self, coordinator: DDOCoordinator, entry: DDOConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_reserved"

    @property
    def native_value(self) -> int:
        return len(_all_reservations(self._accounts))


class ReadyForPickupSensor(_BaseSensor):
    """How many held items are waiting on the hold shelf for pickup."""

    _attr_icon = "mdi:bell-ring"
    _attr_native_unit_of_measurement = "holds"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_name = "Ready for pickup"

    def __init__(self, coordinator: DDOCoordinator, entry: DDOConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_ready_for_pickup"

    @property
    def native_value(self) -> int:
        return sum(1 for r in _all_reservations(self._accounts) if r.is_ready)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        ready = [r for r in _all_reservations(self._accounts) if r.is_ready]
        return {
            "items": [
                {
                    "title": r.title,
                    "account_name": r.account_name,
                    "pickup_location": r.pickup_location,
                    "available_until": r.available_until.isoformat()
                    if r.available_until
                    else None,
                }
                for r in ready
            ]
        }
