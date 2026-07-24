"""Build and own the assignable driver registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from .config import AppConfig
from .drivers import (
    OmegaCNi8Driver,
    PZC200MotorDriver,
    SimulatedMotorDriver,
    SimulatedTemperatureDriver,
    build_esp300_axes,
)


SUPPORTED_DEVICE_TYPES = {
    "esp300": "Newport ESP300 (3 axes)",
    "pzc200": "Newport NanoPZ PZC200",
    "omega_cni8": "OMEGA CNi8/CNi8D",
}


@dataclass(frozen=True)
class DeviceSummary:
    device_id: str
    display_name: str
    kind: str
    source: str


class DeviceRegistry:
    """Registry of physical and simulated drivers keyed by stable IDs."""

    def __init__(
        self,
        config: AppConfig,
        *,
        log_callback: Callable[[str], None] | None = None,
    ) -> None:
        self.config = config
        self._log_callback = log_callback
        self._drivers: dict[str, Any] = {}
        self._sources: dict[str, str] = {}
        self._build()

    def __contains__(self, device_id: str) -> bool:
        return device_id in self._drivers

    def __len__(self) -> int:
        return len(self._drivers)

    def get(self, device_id: str) -> Any | None:
        return self._drivers.get(device_id)

    def source(self, device_id: str) -> str:
        return self._sources.get(device_id, "Unknown")

    def require(self, device_id: str) -> Any:
        try:
            return self._drivers[device_id]
        except KeyError as exc:
            raise KeyError(f"Unknown device: {device_id}") from exc

    def drivers(self, kind: str | None = None) -> list[Any]:
        values = list(self._drivers.values())
        if kind is not None:
            values = [driver for driver in values if driver.kind == kind]
        return sorted(
            values,
            key=lambda driver: (
                str(getattr(driver, "display_name", driver.device_id)).lower(),
                driver.device_id,
            ),
        )

    def summaries(self) -> list[DeviceSummary]:
        return [
            DeviceSummary(
                device_id=driver.device_id,
                display_name=str(
                    getattr(driver, "display_name", driver.device_id)
                ),
                kind=driver.kind,
                source=self._sources[driver.device_id],
            )
            for driver in self.drivers()
        ]

    def assigned_drivers(
        self, assignments: Iterable[str | None]
    ) -> list[Any]:
        seen: set[int] = set()
        result: list[Any] = []
        for device_id in assignments:
            if not device_id:
                continue
            driver = self.get(device_id)
            if driver is not None and id(driver) not in seen:
                seen.add(id(driver))
                result.append(driver)
        return result

    def shutdown(self) -> None:
        for driver in reversed(self.drivers()):
            try:
                if getattr(driver, "is_connected", False):
                    driver.disconnect()
            except Exception:
                pass

    def _build(self) -> None:
        if self.config.simulation:
            for number in range(1, 11):
                driver = SimulatedMotorDriver(
                    f"sim.motor.{number}",
                    display_name=f"Sim Motor {number:02d}",
                )
                self._add(driver, "Simulation")
            self._add(
                SimulatedTemperatureDriver(),
                "Simulation",
            )

        for item in self.config.devices:
            if not item.get("enabled", True):
                continue
            device_type = item["type"]
            if device_type == "esp300":
                self._build_esp300(item)
            elif device_type == "pzc200":
                driver = PZC200MotorDriver(
                    str(item.get("port", "")),
                    address=int(item.get("address", 0)),
                    name=item["id"],
                    display_name=str(item.get("name", item["id"])),
                    timeout=float(item.get("timeout", 0.7)),
                    flow=str(item.get("flow", "both")),
                    log_callback=self._device_log(item["id"]),
                )
                self._add(driver, "PZC200")
            elif device_type in {"omega_cni8", "cni8", "cni8d"}:
                address = item.get("address")
                driver = OmegaCNi8Driver(
                    str(item.get("port", "")),
                    name=item["id"],
                    display_name=str(item.get("name", item["id"])),
                    protocol=str(item.get("protocol", "iseries")),
                    address=None if address is None else int(address),
                    baudrate=int(item.get("baudrate", 9600)),
                    timeout=float(item.get("timeout", 1.0)),
                    recognition_character=str(
                        item.get("recognition_character", "*")
                    ),
                    log_callback=self._device_log(item["id"]),
                )
                self._add(driver, "OMEGA CNi8")
            else:
                raise ValueError(
                    f"Unsupported device type {device_type!r} "
                    f"for {item['id']}"
                )

    def _build_esp300(self, item: dict[str, Any]) -> None:
        axis_names_raw = item.get("axis_names", {})
        if not isinstance(axis_names_raw, dict):
            raise ValueError(f"{item['id']}.axis_names must be an object")
        axis_names = {
            int(axis): str(label) for axis, label in axis_names_raw.items()
        }
        axes = build_esp300_axes(
            str(item.get("port", "")),
            name=item["id"],
            timeout=float(item.get("timeout", 1.0)),
            rtscts=bool(item.get("rtscts", True)),
            axis_names=axis_names,
            log_callback=self._device_log(item["id"]),
        )
        enabled_axes = {int(axis) for axis in item.get("axes", [1, 2, 3])}
        for driver in axes.values():
            if driver.axis in enabled_axes:
                self._add(driver, "ESP300")

    def _add(self, driver: Any, source: str) -> None:
        if driver.device_id in self._drivers:
            raise ValueError(f"Duplicate assignable device id: {driver.device_id}")
        self._drivers[driver.device_id] = driver
        self._sources[driver.device_id] = source

    def _device_log(self, device_id: str) -> Callable[[str], None] | None:
        if self._log_callback is None:
            return None

        def callback(message: str) -> None:
            self._log_callback(f"[{device_id}] {message}")

        return callback
