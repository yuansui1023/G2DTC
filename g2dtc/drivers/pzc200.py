"""NEWPORT NanoPZ PZC200 motor driver."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable


BAUDRATE = 19200
ERRORS = {
    0: "no error",
    2: "driver fault / over-temperature shutdown",
    6: "unknown command",
    7: "parameter out of range",
    8: "motor not connected",
    26: "positive software limit",
    27: "negative software limit",
    38: "missing command parameter",
    50: "communication buffer overflow",
    213: "motor not enabled",
    214: "invalid axis/channel",
    226: "command not allowed during motion",
    227: "command not allowed",
    240: "jog knob over-speed",
}


class PZC200Error(RuntimeError):
    """Base exception for PZC200 communication and device errors."""


class PZC200ProtocolError(PZC200Error):
    """The controller returned an unexpected response."""


class PZC200DeviceError(PZC200Error):
    def __init__(self, code: int) -> None:
        self.code = int(code)
        super().__init__(
            f"PZC200 error {self.code}: {ERRORS.get(self.code, 'unknown error')}"
        )


class PZC200MotorDriver:
    """One independently assignable PZC200 controller/address."""

    kind = "motor"
    capabilities = frozenset(
        {
            "position",
            "relative_move",
            "jog",
            "stop",
            "enable",
            "digital_zero",
            "software_limits",
        }
    )
    unit = "microstep"
    jog_unit = "level"
    default_step = 100
    default_jog = 3

    def __init__(
        self,
        port: str,
        *,
        address: int = 0,
        name: str = "pzc200",
        display_name: str | None = None,
        timeout: float = 0.7,
        flow: str = "both",
        serial_factory: Callable[..., Any] | None = None,
        log_callback: Callable[[str], None] | None = None,
    ) -> None:
        if not port:
            raise ValueError("PZC200 serial port cannot be empty")
        if not 0 <= int(address) <= 255:
            raise ValueError("PZC200 address must be between 0 and 255")
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if flow not in {"both", "xonxoff", "rtscts", "none"}:
            raise ValueError("flow must be both, xonxoff, rtscts, or none")
        self.port = port
        self.address = int(address)
        self.device_id = name
        self.display_name = display_name or name
        self.timeout = float(timeout)
        self.flow = flow
        self._serial_factory = serial_factory
        self._log_callback = log_callback
        self._serial: Any = None
        self._lock = threading.RLock()
        self._version = ""

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return bool(self._serial and self._serial.is_open)

    def connect(self) -> None:
        with self._lock:
            if self.is_connected:
                return
            factory = self._serial_factory
            if factory is None:
                try:
                    import serial
                except ImportError as exc:
                    raise PZC200Error(
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
                    xonxoff=self.flow in {"both", "xonxoff"},
                    rtscts=self.flow in {"both", "rtscts"},
                    dsrdtr=False,
                )
                self._version = self._query_locked("VE")
            except Exception as exc:
                self._close_locked()
                if isinstance(exc, PZC200Error):
                    raise
                raise PZC200Error(
                    f"Could not open PZC200 on {self.port}: {exc}"
                ) from exc

    def disconnect(self) -> None:
        with self._lock:
            self._close_locked()

    def __enter__(self) -> "PZC200MotorDriver":
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.disconnect()

    def version(self) -> str:
        with self._lock:
            self._require_connected_locked()
            self._version = self._query_locked("VE")
            return self._version

    def position(self, channel: int | None = None) -> float:
        with self._lock:
            self._require_connected_locked()
            if channel is not None and not 1 <= int(channel) <= 8:
                raise ValueError("PZC200 channel must be between 1 and 8")
            return float(self._query_int_locked(f"TP{channel or ''}"))

    def status(self) -> int:
        with self._lock:
            self._require_connected_locked()
            return self._query_int_locked("TS")

    def is_moving(self) -> bool:
        return self.status() == 80

    def motor_enabled(self) -> bool:
        return self.status() in (80, 81)

    def enable(self, enabled: bool = True) -> None:
        with self._lock:
            self._require_connected_locked()
            if not enabled and self.is_moving():
                self._set_locked("ST")
            self._set_locked("MO" if enabled else "MF")

    def stop(self) -> None:
        with self._lock:
            self._require_connected_locked()
            self._set_locked("ST")

    def zero(self) -> None:
        with self._lock:
            self._require_connected_locked()
            self._set_locked("OR")

    def move_relative(self, distance: float, **_: Any) -> None:
        microsteps = int(round(float(distance)))
        if not -10_000_000 <= microsteps <= 10_000_000:
            raise ValueError("PZC200 move must be within ±10,000,000 microsteps")
        with self._lock:
            self._require_connected_locked()
            if not self.motor_enabled():
                self._set_locked("MO")
            self._set_locked(f"PR{microsteps}")

    def jog(self, direction: int, velocity: float) -> None:
        direction = int(direction)
        if direction not in (-1, 0, 1):
            raise ValueError("jog direction must be -1, 0, or 1")
        level = int(round(abs(float(velocity))))
        if not 0 <= level <= 7:
            raise ValueError("PZC200 jog level must be between 0 and 7")
        with self._lock:
            self._require_connected_locked()
            if direction and not self.motor_enabled():
                self._set_locked("MO")
            self._set_locked(f"JA{direction * level}")

    def wait_until_idle(
        self, timeout: float = 30.0, poll_interval: float = 0.05
    ) -> None:
        deadline = time.monotonic() + float(timeout)
        while time.monotonic() < deadline:
            if not self.is_moving():
                return
            time.sleep(poll_interval)
        self.stop()
        raise PZC200Error(
            f"{self.device_id} did not stop within {timeout:g} seconds"
        )

    def limits(self) -> tuple[float, float]:
        with self._lock:
            self._require_connected_locked()
            return (
                float(self._query_int_locked("SL")),
                float(self._query_int_locked("SR")),
            )

    def set_limits(
        self, negative: float, positive: float, *, save: bool = False
    ) -> None:
        negative = int(round(float(negative)))
        positive = int(round(float(positive)))
        if not -10_000_000 <= negative <= 0:
            raise ValueError("negative PZC200 limit is out of range")
        if not 0 <= positive <= 10_000_000 or negative >= positive:
            raise ValueError("positive PZC200 limit is out of range")
        with self._lock:
            self._require_connected_locked()
            self._set_locked(f"SL{negative}")
            self._set_locked(f"SR{positive}")
            if save:
                self._set_locked("SM")

    def select_channel(self, channel: int) -> None:
        channel = int(channel)
        if not 1 <= channel <= 8:
            raise ValueError("PZC200 channel must be between 1 and 8")
        with self._lock:
            self._require_connected_locked()
            self._set_locked("MF")
            self._set_locked(f"MX{channel}")

    def health(self) -> dict[str, Any]:
        with self._lock:
            self._require_connected_locked()
            status = self.status()
            return {
                "device_id": self.device_id,
                "display_name": self.display_name,
                "connected": True,
                "port": self.port,
                "address": self.address,
                "firmware": self._version,
                "position": self.position(),
                "unit": self.unit,
                "moving": status == 80,
                "enabled": status in (80, 81),
                "limits": self.limits(),
            }

    def _query_int_locked(self, body: str) -> int:
        response = self._query_locked(body)
        try:
            return int(response)
        except ValueError as exc:
            raise PZC200ProtocolError(
                f"Expected integer response to {body}, got {response!r}"
            ) from exc

    def _query_locked(self, body: str) -> str:
        command = f"{self.address}{body}?"
        self._write_locked(command)
        response = self._read_line_locked()
        if response.endswith("!"):
            raise PZC200ProtocolError(f"PZC200 rejected {command!r}")
        for prefix in (command, command[:-1]):
            if response.startswith(prefix):
                value = response[len(prefix) :].strip()
                if value:
                    return value
        if " " not in response:
            return response
        return response.rsplit(maxsplit=1)[-1]

    def _set_locked(self, body: str, *, check_error: bool = True) -> None:
        self._write_locked(f"{self.address}{body}")
        if check_error:
            time.sleep(0.03)
            code = self._query_int_locked("TE")
            if code:
                raise PZC200DeviceError(code)

    def _write_locked(self, command: str) -> None:
        self._require_connected_locked()
        self._log(f">> {command}")
        try:
            self._serial.reset_input_buffer()
            self._serial.write((command + "\r").encode("ascii"))
            self._serial.flush()
        except Exception as exc:
            raise PZC200Error(f"Failed to send {command!r}") from exc

    def _read_line_locked(self) -> str:
        deadline = time.monotonic() + self.timeout
        data = bytearray()
        try:
            while time.monotonic() < deadline:
                byte = self._serial.read(1)
                if not byte:
                    break
                if byte in (b"\r", b"\n"):
                    if data:
                        break
                    continue
                data.extend(byte)
        except Exception as exc:
            raise PZC200Error("Failed to read PZC200 response") from exc
        if not data:
            raise PZC200Error(
                f"Timed out waiting for PZC200 address {self.address}"
            )
        try:
            response = data.decode("ascii").strip()
        except UnicodeDecodeError as exc:
            raise PZC200ProtocolError(
                f"PZC200 returned non-ASCII data: {bytes(data)!r}"
            ) from exc
        self._log(f"<< {response}")
        return response

    def _require_connected_locked(self) -> None:
        if not self._serial or not self._serial.is_open:
            raise PZC200Error(f"PZC200 serial port {self.port} is not connected")

    def _close_locked(self) -> None:
        serial_port = self._serial
        self._serial = None
        self._version = ""
        if serial_port is not None:
            try:
                serial_port.close()
            except Exception:
                pass

    def _log(self, message: str) -> None:
        if self._log_callback:
            self._log_callback(message)
