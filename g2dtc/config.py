"""Configuration model for devices, logical slots, and assignments."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


CONFIG_VERSION = 2
MANUAL_ASSIGNMENT = "__manual__"


@dataclass(frozen=True)
class SlotDefinition:
    key: str
    group: str
    group_label: str
    label: str
    kind: str


SLOTS: tuple[SlotDefinition, ...] = (
    SlotDefinition("transfer_arm.x", "transfer_arm", "Transfer Arm", "X", "motor"),
    SlotDefinition("transfer_arm.y", "transfer_arm", "Transfer Arm", "Y", "motor"),
    SlotDefinition("transfer_arm.z", "transfer_arm", "Transfer Arm", "Z", "motor"),
    SlotDefinition("stage.x", "stage", "Stage", "X", "motor"),
    SlotDefinition("stage.y", "stage", "Stage", "Y", "motor"),
    SlotDefinition("stage.z", "stage", "Stage", "Z", "motor"),
    SlotDefinition("stage.rz", "stage", "Stage", "Rz", "motor"),
    SlotDefinition(
        "stage.temperature",
        "stage",
        "Stage",
        "Temperature",
        "temperature",
    ),
    SlotDefinition("microscope.x", "microscope", "Microscope", "X", "motor"),
    SlotDefinition("microscope.y", "microscope", "Microscope", "Y", "motor"),
    SlotDefinition("microscope.z", "microscope", "Microscope", "Z", "motor"),
)

SLOT_BY_KEY = {slot.key: slot for slot in SLOTS}


def is_hardware_assignment(value: str | None) -> bool:
    """Return whether an assignment should create a dashboard module."""
    return bool(value) and value != MANUAL_ASSIGNMENT


def default_config_path() -> Path:
    """Return the per-user configuration location without creating it."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "g2dtc" / "config.json"


def _default_assignments() -> dict[str, str | None]:
    return {slot.key: None for slot in SLOTS}


def _legacy_simulation_assignments() -> dict[str, str | None]:
    motor_index = 1
    assignments: dict[str, str | None] = {}
    for slot in SLOTS:
        if slot.kind == "temperature":
            assignments[slot.key] = "sim.temperature.1"
        else:
            assignments[slot.key] = f"sim.motor.{motor_index}"
            motor_index += 1
    return assignments


@dataclass
class AppConfig:
    """Serializable application configuration."""

    version: int = CONFIG_VERSION
    simulation: bool = True
    devices: list[dict[str, Any]] = field(default_factory=list)
    assignments: dict[str, str | None] = field(default_factory=_default_assignments)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "AppConfig":
        version = int(raw.get("version", CONFIG_VERSION))
        if version not in (1, CONFIG_VERSION):
            raise ValueError(
                f"Unsupported configuration version {version}; "
                f"expected 1 or {CONFIG_VERSION}"
            )
        devices_raw = raw.get("devices", [])
        assignments_raw = raw.get("assignments", {})
        if not isinstance(devices_raw, list):
            raise ValueError("'devices' must be a list")
        if not isinstance(assignments_raw, Mapping):
            raise ValueError("'assignments' must be an object")

        assignments: dict[str, str | None] = {}
        for slot in SLOTS:
            value = assignments_raw.get(slot.key)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"Assignment for {slot.key} must be text or null")
            assignments[slot.key] = value
        if (
            version == 1
            and bool(raw.get("simulation", False))
            and not devices_raw
            and assignments == _legacy_simulation_assignments()
        ):
            assignments = _default_assignments()

        devices: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for index, item in enumerate(devices_raw):
            if not isinstance(item, Mapping):
                raise ValueError(f"Device #{index + 1} must be an object")
            device = dict(item)
            device_id = str(device.get("id", "")).strip()
            device_type = str(device.get("type", "")).strip().lower()
            if not device_id or not device_type:
                raise ValueError(f"Device #{index + 1} needs 'id' and 'type'")
            if device_id in seen_ids:
                raise ValueError(f"Duplicate device id: {device_id}")
            seen_ids.add(device_id)
            device["id"] = device_id
            device["type"] = device_type
            device["enabled"] = bool(device.get("enabled", True))
            devices.append(device)

        return cls(
            version=CONFIG_VERSION,
            simulation=bool(raw.get("simulation", False)),
            devices=devices,
            assignments=assignments,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "simulation": self.simulation,
            "devices": self.devices,
            "assignments": {
                slot.key: self.assignments.get(slot.key) for slot in SLOTS
            },
        }

    def assign(
        self,
        slot_key: str,
        device_id: str | None,
        *,
        device_kind: str | None = None,
    ) -> str | None:
        """
        Assign one device and return a previous slot cleared by this change.

        Physical devices are exclusive. Manual and unassigned entries may be
        used by any number of slots.
        """
        try:
            slot = SLOT_BY_KEY[slot_key]
        except KeyError as exc:
            raise KeyError(f"Unknown logical slot: {slot_key}") from exc
        if device_id == "":
            device_id = None
        if (
            device_id not in (None, MANUAL_ASSIGNMENT)
            and device_kind is not None
            and device_kind != slot.kind
        ):
            raise ValueError(
                f"{slot_key} requires {slot.kind}, got {device_kind}"
            )

        cleared: str | None = None
        if device_id not in (None, MANUAL_ASSIGNMENT):
            for other_key, assigned in self.assignments.items():
                if other_key != slot_key and assigned == device_id:
                    self.assignments[other_key] = None
                    cleared = other_key
                    break
        self.assignments[slot_key] = device_id
        return cleared


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        return AppConfig()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read configuration {path}: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise ValueError("Configuration root must be a JSON object")
    return AppConfig.from_dict(raw)


def save_config(config: AppConfig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(config.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
