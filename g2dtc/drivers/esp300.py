"""Newport ESP300 driver with separately assignable shared-port axes."""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from math import isfinite
from typing import Any, Callable, Iterator


BAUDRATE = 19200
VALID_AXES = (1, 2, 3)
UNIT_NAMES = {
    0: "encoder_count",
    1: "motor_step",
    2: "mm",
    3: "um",
    4: "inch",
    5: "milli_inch",
    6: "micro_inch",
    7: "degree",
    8: "gradient",
    9: "radian",
    10: "milliradian",
    11: "microradian",
}


class ESP300Error(RuntimeError):
    """Base ESP300 exception."""


class ESP300ProtocolError(ESP300Error):
    """The ESP300 returned an unexpected response."""


class ESP300BusyError(ESP300Error):
    """A motion was requested while an axis was already moving."""


def _axis_number(axis: int) -> int:
    axis = int(axis)
    if axis not in VALID_AXES:
        raise ValueError("ESP300 axis must be 1, 2, or 3")
    return axis


def _format_number(value: float) -> str:
    value = float(value)
    if not isfinite(value):
        raise ValueError("ESP300 values must be finite")
    return f"{value:.12g}"


class ESP300Controller:
    """One serial connection shared by all assigned ESP300 axes."""

    def __init__(
        self,
        port: str,
        *,
        name: str = "esp300",
        timeout: float = 1.0,
        rtscts: bool = True,
        serial_factory: Callable[..., Any] | None = None,
        log_callback: Callable[[str], None] | None = None,
    ) -> None:
        if not port:
            raise ValueError("ESP300 serial port cannot be empty")
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        self.port = port
        self.name = name
        self.timeout = float(timeout)
        self.rtscts = bool(rtscts)
        self._serial_factory = serial_factory
        self._log_callback = log_callback
        self._serial: Any = None
        self._identity = ""
        self._lock = threading.RLock()
        self._attached_axes: set[int] = set()
        self._axes: dict[int, ESP300AxisDriver] = {}

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return bool(self._serial and self._serial.is_open)

    @property
    def identity(self) -> str:
        return self._identity

    def axis(
        self, axis: int, *, display_name: str | None = None
    ) -> "ESP300AxisDriver":
        axis = _axis_number(axis)
        with self._lock:
            if axis not in self._axes:
                self._axes[axis] = ESP300AxisDriver(
                    self, axis, display_name=display_name
                )
            elif display_name:
                self._axes[axis].display_name = display_name
            return self._axes[axis]

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            self._require_open_locked()
            yield

    def write(self, command: str) -> None:
        with self._lock:
            self._require_open_locked()
            self._write_locked(command)

    def query(self, command: str) -> str:
        with self._lock:
            self._require_open_locked()
            return self._query_locked(command)

    def _attach(self, axis: int) -> None:
        with self._lock:
            self._ensure_open_locked()
            self._attached_axes.add(_axis_number(axis))

    def _detach(self, axis: int) -> None:
        with self._lock:
            self._attached_axes.discard(_axis_number(axis))
            if not self._attached_axes:
                self._close_locked()

    def shutdown(self) -> None:
        with self._lock:
            self._attached_axes.clear()
            for axis in self._axes.values():
                axis._connected = False
            self._close_locked()

    def _ensure_open_locked(self) -> None:
        if self._serial and self._serial.is_open:
            return
        factory = self._serial_factory
        if factory is None:
            try:
                import serial
            except ImportError as exc:
                raise ESP300Error(
                    "pyserial is required: python -m pip install pyserial"
                ) from exc
            factory = serial.serial_for_url
            bytesize = serial.EIGHTBITS
            parity = serial.PARITY_NONE
            stopbits = serial.STOPBITS_ONE
        else:
            bytesize, parity, stopbits = 8, "N", 1
        try:
            self._serial = factory(
                self.port,
                baudrate=BAUDRATE,
                bytesize=bytesize,
                parity=parity,
                stopbits=stopbits,
                timeout=self.timeout,
                write_timeout=self.timeout,
                rtscts=self.rtscts,
                xonxoff=False,
                dsrdtr=False,
            )
            self._serial.reset_input_buffer()
            response = self._query_locked("VE?")
            if not any(
                token in response.upper()
                for token in ("ESP300", "ESP301", "ESP0300")
            ):
                raise ESP300ProtocolError(
                    f"Device did not identify as ESP300/ESP301: {response!r}"
                )
            self._identity = response
        except Exception as exc:
            self._close_locked()
            if isinstance(exc, ESP300Error):
                raise
            raise ESP300Error(
                f"Could not open ESP300 on {self.port}: {exc}"
            ) from exc

    def _write_locked(self, command: str) -> None:
        command = command.rstrip("\r\n")
        if not command or not command.isascii():
            raise ValueError("ESP300 command must be non-empty ASCII")
        self._log(f">> {command}")
        try:
            self._serial.write((command + "\r").encode("ascii"))
            self._serial.flush()
        except Exception as exc:
            raise ESP300Error(f"Failed to write {command!r}") from exc

    def _query_locked(self, command: str) -> str:
        try:
            self._serial.reset_input_buffer()
            self._write_locked(command)
            raw = self._serial.readline()
        except Exception as exc:
            raise ESP300Error(f"Failed to query {command!r}") from exc
        if not raw:
            raise ESP300Error(f"Timed out waiting for {command!r}")
        try:
            response = raw.decode("ascii").strip()
        except UnicodeDecodeError as exc:
            raise ESP300ProtocolError(
                f"ESP300 returned non-ASCII data: {raw!r}"
            ) from exc
        self._log(f"<< {response}")
        return response

    def _require_open_locked(self) -> None:
        if not self._serial or not self._serial.is_open:
            raise ESP300Error(f"ESP300 port {self.port} is not open")

    def _close_locked(self) -> None:
        serial_port = self._serial
        self._serial = None
        self._identity = ""
        if serial_port is not None:
            try:
                serial_port.close()
            except Exception:
                pass

    def _log(self, message: str) -> None:
        if self._log_callback:
            self._log_callback(message)


class ESP300AxisDriver:
    """One independently assignable motor axis on a shared ESP300."""

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
            "software_limits",
        }
    )

    def __init__(
        self,
        controller: ESP300Controller,
        axis: int,
        *,
        display_name: str | None = None,
    ) -> None:
        self.controller = controller
        self.axis = _axis_number(axis)
        self.device_id = f"{controller.name}.axis{self.axis}"
        self.display_name = (
            display_name or f"{controller.name} · Axis {self.axis}"
        )
        self.default_step = 0.1
        self.default_jog = 0.5
        self._connected = False
        self._unit_code: int | None = None
        self._max_velocity: float | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected and self.controller.is_connected

    @property
    def unit(self) -> str:
        if self._unit_code is None:
            return "native_unit"
        return UNIT_NAMES.get(self._unit_code, f"unit_{self._unit_code}")

    @property
    def jog_unit(self) -> str:
        return f"{self.unit}/s"

    def connect(self) -> None:
        if self.is_connected:
            return
        self.controller._attach(self.axis)
        try:
            self._connected = True
            self._unit_code = self._query_int("SN?")
            self._max_velocity = self._query_float("VU?")
            if self._max_velocity and self._max_velocity > 0:
                self.default_jog = min(self.default_jog, self._max_velocity)
        except Exception:
            self._connected = False
            self.controller._detach(self.axis)
            raise

    def disconnect(self) -> None:
        if self._connected:
            self._connected = False
            self.controller._detach(self.axis)

    def position(self) -> float:
        self._require_connected()
        return self._query_float("TP")

    def is_moving(self) -> bool:
        self._require_connected()
        value = self._query_int("MD?")
        if value not in (0, 1):
            raise ESP300ProtocolError(f"Invalid MD? response: {value}")
        return value == 0

    def motor_enabled(self) -> bool:
        self._require_connected()
        value = self._query_int("MO?")
        if value not in (0, 1):
            raise ESP300ProtocolError(f"Invalid MO? response: {value}")
        return bool(value)

    def enable(self, enabled: bool = True) -> None:
        self._require_connected()
        if enabled:
            self._write("MO")
        else:
            if self.is_moving():
                self.stop()
            self._write("MF")

    def move_relative(self, distance: float, *, velocity: float | None = None) -> None:
        self._move("PR", distance, velocity)

    def move_absolute(self, position: float, *, velocity: float | None = None) -> None:
        self._move("PA", position, velocity)

    def _move(self, command: str, value: float, velocity: float | None) -> None:
        self._require_connected()
        with self.controller.transaction():
            if self.is_moving():
                raise ESP300BusyError(f"{self.device_id} is already moving")
            commands: list[str] = []
            if velocity is not None:
                commands.append(
                    f"{self.axis}VA{_format_number(self._checked_velocity(velocity))}"
                )
            commands.append(f"{self.axis}{command}{_format_number(value)}")
            self.controller._write_locked(";".join(commands))

    def jog(self, direction: int, velocity: float) -> None:
        self._require_connected()
        direction = int(direction)
        if direction == 0:
            self.stop()
            return
        if direction not in (-1, 1):
            raise ValueError("jog direction must be -1, 0, or 1")
        velocity = self._checked_velocity(velocity)
        sign = "+" if direction > 0 else "-"
        with self.controller.transaction():
            if self.is_moving():
                self._write("ST")
            self.controller._write_locked(
                f"{self.axis}VA{_format_number(velocity)};"
                f"{self.axis}MV{sign}"
            )

    def stop(self) -> None:
        self._require_connected()
        self._write("ST")

    def zero(self) -> None:
        self._require_connected()
        if self.is_moving():
            raise ESP300BusyError("Cannot zero a moving ESP300 axis")
        self._write("DH0")

    def home(self) -> None:
        self._require_connected()
        if self.is_moving():
            raise ESP300BusyError("Cannot home a moving ESP300 axis")
        self._write("OR")

    def limits(self) -> tuple[float, float]:
        self._require_connected()
        return self._query_float("SL?"), self._query_float("SR?")

    def set_limits(self, negative: float, positive: float) -> None:
        negative, positive = float(negative), float(positive)
        if not isfinite(negative) or not isfinite(positive) or negative >= positive:
            raise ValueError("negative limit must be below positive limit")
        with self.controller.transaction():
            if self.is_moving():
                raise ESP300BusyError("Cannot change limits during motion")
            self.controller._write_locked(
                f"{self.axis}SL{_format_number(negative)};"
                f"{self.axis}SR{_format_number(positive)}"
            )

    def wait_until_idle(
        self, timeout: float = 30.0, poll_interval: float = 0.1
    ) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.is_moving():
                return
            time.sleep(poll_interval)
        self.stop()
        raise ESP300Error(
            f"{self.device_id} did not stop within {timeout:g} seconds"
        )

    def health(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "display_name": self.display_name,
            "connected": self.is_connected,
            "controller": self.controller.identity,
            "port": self.controller.port,
            "axis": self.axis,
            "unit": self.unit,
            "position": self.position(),
            "moving": self.is_moving(),
            "enabled": self.motor_enabled(),
            "max_velocity": self._max_velocity,
            "limits": self.limits(),
        }

    def _checked_velocity(self, velocity: float) -> float:
        velocity = abs(float(velocity))
        if not isfinite(velocity) or velocity <= 0:
            raise ValueError("velocity must be greater than zero")
        if self._max_velocity and velocity > self._max_velocity:
            raise ValueError(
                f"velocity exceeds maximum {self._max_velocity:g} {self.jog_unit}"
            )
        return velocity

    def _query_float(self, command: str) -> float:
        response = self.controller.query(f"{self.axis}{command}")
        try:
            return float(response)
        except ValueError as exc:
            raise ESP300ProtocolError(
                f"Unexpected response to {self.axis}{command}: {response!r}"
            ) from exc

    def _query_int(self, command: str) -> int:
        value = self._query_float(command)
        if not value.is_integer():
            raise ESP300ProtocolError(f"Expected integer response, got {value}")
        return int(value)

    def _write(self, command: str) -> None:
        self.controller.write(f"{self.axis}{command}")

    def _require_connected(self) -> None:
        if not self.is_connected:
            raise ESP300Error(f"{self.device_id} is not connected")


def build_esp300_axes(
    port: str,
    *,
    name: str = "esp300",
    timeout: float = 1.0,
    rtscts: bool = True,
    axis_names: dict[int, str] | None = None,
    serial_factory: Callable[..., Any] | None = None,
    log_callback: Callable[[str], None] | None = None,
) -> dict[str, ESP300AxisDriver]:
    """Build three assignable axes backed by one shared serial connection."""
    controller = ESP300Controller(
        port,
        name=name,
        timeout=timeout,
        rtscts=rtscts,
        serial_factory=serial_factory,
        log_callback=log_callback,
    )
    axes = [
        controller.axis(
            number,
            display_name=(axis_names or {}).get(number),
        )
        for number in VALID_AXES
    ]
    return {axis.device_id: axis for axis in axes}
