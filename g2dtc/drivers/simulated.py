"""Deterministic simulation drivers for UI development without hardware."""

from __future__ import annotations

import threading
import time
from math import isfinite
from typing import Any


class SimulatedMotorDriver:
    kind = "motor"
    capabilities = frozenset(
        {
            "position",
            "relative_move",
            "absolute_move",
            "jog",
            "stop",
            "enable",
            "digital_zero",
            "home",
        }
    )

    def __init__(
        self,
        device_id: str,
        *,
        display_name: str | None = None,
        unit: str = "mm",
    ) -> None:
        self.device_id = device_id
        self.display_name = display_name or device_id
        self.unit = unit
        self.jog_unit = f"{unit}/s"
        self.default_step = 0.1
        self.default_jog = 0.5
        self._connected = False
        self._enabled = True
        self._position = 0.0
        self._velocity = 0.0
        self._updated_at = time.monotonic()
        self._lock = threading.RLock()

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        self._connected = True
        self._updated_at = time.monotonic()

    def disconnect(self) -> None:
        with self._lock:
            self._advance()
            self._velocity = 0.0
            self._connected = False

    def position(self) -> float:
        with self._lock:
            self._require_connected()
            self._advance()
            return self._position

    def move_relative(self, distance: float, **_: Any) -> None:
        with self._lock:
            self._require_ready()
            distance = float(distance)
            if not isfinite(distance):
                raise ValueError("distance must be finite")
            self._advance()
            self._position += distance

    def move_absolute(self, position: float, **_: Any) -> None:
        with self._lock:
            self._require_ready()
            position = float(position)
            if not isfinite(position):
                raise ValueError("position must be finite")
            self._advance()
            self._position = position

    def jog(self, direction: int, velocity: float) -> None:
        with self._lock:
            self._require_ready()
            if int(direction) not in (-1, 0, 1):
                raise ValueError("direction must be -1, 0, or 1")
            velocity = abs(float(velocity))
            if not isfinite(velocity):
                raise ValueError("velocity must be finite")
            self._advance()
            self._velocity = int(direction) * velocity

    def stop(self) -> None:
        with self._lock:
            self._require_connected()
            self._advance()
            self._velocity = 0.0

    def enable(self, enabled: bool = True) -> None:
        with self._lock:
            self._require_connected()
            self._advance()
            self._enabled = bool(enabled)
            if not self._enabled:
                self._velocity = 0.0

    def motor_enabled(self) -> bool:
        self._require_connected()
        return self._enabled

    def is_moving(self) -> bool:
        self._require_connected()
        return self._velocity != 0

    def zero(self) -> None:
        with self._lock:
            self._require_ready()
            self._advance()
            self._position = 0.0

    def home(self) -> None:
        self.zero()

    def health(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "connected": self.is_connected,
            "position": self.position(),
            "unit": self.unit,
            "moving": self.is_moving(),
            "enabled": self.motor_enabled(),
        }

    def _advance(self) -> None:
        now = time.monotonic()
        self._position += self._velocity * (now - self._updated_at)
        self._updated_at = now

    def _require_connected(self) -> None:
        if not self._connected:
            raise RuntimeError(f"{self.device_id} is not connected")

    def _require_ready(self) -> None:
        self._require_connected()
        if not self._enabled:
            raise RuntimeError(f"{self.device_id} is disabled")


class SimulatedTemperatureDriver:
    kind = "temperature"
    capabilities = frozenset(
        {"temperature", "setpoint", "set_setpoint", "output"}
    )

    def __init__(
        self,
        device_id: str = "sim.temperature.1",
        *,
        display_name: str = "Simulated temperature",
        ambient: float = 22.0,
        unit: str = "C",
    ) -> None:
        self.device_id = device_id
        self.display_name = display_name
        self.unit = unit
        self._temperature = float(ambient)
        self._setpoint = float(ambient)
        self._output_enabled = False
        self._connected = False
        self._updated_at = time.monotonic()
        self._lock = threading.RLock()

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def output_enabled(self) -> bool:
        return self._output_enabled

    def connect(self) -> None:
        self._connected = True
        self._updated_at = time.monotonic()

    def disconnect(self) -> None:
        with self._lock:
            self._advance()
            self._connected = False

    def temperature(self) -> float:
        with self._lock:
            self._require_connected()
            self._advance()
            return self._temperature

    read_temperature = temperature

    def setpoint(self) -> float:
        self._require_connected()
        return self._setpoint

    def persistent_setpoint(self) -> float:
        return self.setpoint()

    def set_setpoint(self, value: float, **_: Any) -> float:
        with self._lock:
            self._require_connected()
            value = float(value)
            if not isfinite(value):
                raise ValueError("setpoint must be finite")
            self._advance()
            self._setpoint = value
            return value

    def output(self, enabled: bool) -> None:
        with self._lock:
            self._require_connected()
            self._advance()
            self._output_enabled = bool(enabled)

    def health(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "connected": self.is_connected,
            "temperature": self.temperature(),
            "setpoint": self.setpoint(),
            "unit": self.unit,
            "output_enabled": self.output_enabled,
        }

    def _advance(self) -> None:
        now = time.monotonic()
        elapsed = min(now - self._updated_at, 5.0)
        target = self._setpoint if self._output_enabled else 22.0
        rate = 1.5 if self._output_enabled else 0.35
        difference = target - self._temperature
        step = min(abs(difference), rate * elapsed)
        self._temperature += step if difference >= 0 else -step
        self._updated_at = now

    def _require_connected(self) -> None:
        if not self._connected:
            raise RuntimeError(f"{self.device_id} is not connected")
