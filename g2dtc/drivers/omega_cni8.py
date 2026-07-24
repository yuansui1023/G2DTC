"""OMEGA CNi8/CNi8D iSeries ASCII and Modbus RTU driver."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from math import isfinite
from typing import Any, Callable


ISERIES = "iseries"
MODBUS = "modbus"
ASCII_ERRORS = {
    "?43": "command error",
    "?46": "format error",
    "?50": "parity error",
    "?56": "serial address error",
}
MODBUS_ERRORS = {
    1: "illegal function",
    2: "illegal data address",
    3: "illegal data value",
}
DECIMAL_PLACES = {1: 0, 2: 1, 3: 2, 4: 3}
FILTERS = {0: 1, 1: 2, 2: 4, 3: 8, 4: 16, 5: 32, 6: 64, 7: 128}
NUMBER = re.compile(
    r"^[ \t]*([+-]?(?:\d+(?:\.\d*)?|\.\d+))[ \t]*([CF])?[ \t]*$",
    re.IGNORECASE,
)


class OmegaCNi8Error(RuntimeError):
    """Base CNi8 exception."""


class OmegaCNi8TimeoutError(OmegaCNi8Error):
    """The controller did not respond in time."""


class OmegaCNi8ProtocolError(OmegaCNi8Error):
    """The controller returned an invalid response."""


class OmegaCNi8UnsupportedError(OmegaCNi8Error):
    """The selected CNi8 protocol does not expose this operation."""


@dataclass(frozen=True)
class CNi8ReadingConfiguration:
    decimal_places: int
    unit: str
    filter_constant: int
    raw: int


@dataclass(frozen=True)
class CNi8AlarmState:
    alarm1: bool
    alarm2: bool


def _protocol(value: str) -> str:
    normalised = str(value).lower().replace("-", "").replace("_", "").strip()
    if normalised in {"iseries", "ascii"}:
        return ISERIES
    if normalised in {"modbus", "modbusrtu", "rtu"}:
        return MODBUS
    raise ValueError("protocol must be iseries/ascii or modbus")


def _decode_configuration(raw: int) -> CNi8ReadingConfiguration:
    raw = int(raw)
    try:
        places = DECIMAL_PLACES[raw & 0x07]
    except KeyError as exc:
        raise OmegaCNi8ProtocolError(
            f"Invalid CNi8 decimal-position code: {raw & 0x07}"
        ) from exc
    return CNi8ReadingConfiguration(
        decimal_places=places,
        unit="F" if raw & 0x08 else "C",
        filter_constant=FILTERS[(raw >> 4) & 0x07],
        raw=raw,
    )


def _counts(value: float, places: int) -> int:
    value = float(value)
    if not isfinite(value):
        raise ValueError("setpoint must be finite")
    scale = Decimal(10) ** places
    result = int(
        (Decimal(str(value)) * scale).to_integral_value(rounding=ROUND_HALF_UP)
    )
    if not -1999 <= result <= 9999:
        raise ValueError("setpoint is outside the CNi8 four-digit range")
    return result


def _value(counts: int, places: int) -> float:
    return float(Decimal(int(counts)) / (Decimal(10) ** places))


def _encode_setpoint(value: float, places: int) -> str:
    counts = _counts(value, places)
    encoded = ((places + 1) << 20) | abs(counts)
    if counts < 0:
        encoded |= 1 << 23
    return f"{encoded:06X}"


def _decode_setpoint(data: str) -> float:
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", data):
        raise OmegaCNi8ProtocolError(
            f"Expected six hexadecimal setpoint characters, got {data!r}"
        )
    encoded = int(data, 16)
    try:
        places = DECIMAL_PLACES[(encoded >> 20) & 0x07]
    except KeyError as exc:
        raise OmegaCNi8ProtocolError("Invalid setpoint decimal code") from exc
    counts = encoded & 0xFFFFF
    if encoded & 0x800000:
        counts = -counts
    return _value(counts, places)


def _signed16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def _crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


class OmegaCNi8Driver:
    """One assignable CNi8 temperature-control loop."""

    kind = "temperature"
    capabilities = frozenset(
        {"temperature", "setpoint", "set_setpoint", "output", "alarm_status"}
    )
    default_setpoint = 25.0

    def __init__(
        self,
        port: str,
        *,
        name: str = "omega_cni8",
        display_name: str | None = None,
        protocol: str = ISERIES,
        address: int | None = None,
        baudrate: int = 9600,
        timeout: float = 1.0,
        recognition_character: str = "*",
        echo: bool | None = None,
        serial_factory: Callable[..., Any] | None = None,
        log_callback: Callable[[str], None] | None = None,
    ) -> None:
        if not port:
            raise ValueError("CNi8 serial port cannot be empty")
        if int(baudrate) not in {300, 600, 1200, 2400, 4800, 9600, 19200}:
            raise ValueError("unsupported CNi8 baud rate")
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if (
            len(recognition_character) != 1
            or not recognition_character.isascii()
            or not 0x21 <= ord(recognition_character) <= 0x7D
            or recognition_character in {"^", "A", "E"}
        ):
            raise ValueError("invalid CNi8 recognition character")

        self.port = port
        self.device_id = name
        self.display_name = display_name or name
        self.protocol = _protocol(protocol)
        if self.protocol == MODBUS:
            self.address = 1 if address is None else int(address)
            if not 1 <= self.address <= 199:
                raise ValueError("Modbus address must be between 1 and 199")
        else:
            self.address = None if address is None else int(address)
            if self.address is not None and not 0 <= self.address <= 199:
                raise ValueError("iSeries address must be between 0 and 199")
        self.baudrate = int(baudrate)
        self.timeout = float(timeout)
        self.recognition_character = recognition_character
        self._echo = echo
        self._serial_factory = serial_factory
        self._log_callback = log_callback
        self._serial: Any = None
        self._lock = threading.RLock()
        self._configuration: CNi8ReadingConfiguration | None = None
        self._volatile_setpoint: float | None = None
        self._output_enabled: bool | None = None

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return bool(self._serial and self._serial.is_open)

    @property
    def reading_configuration(self) -> CNi8ReadingConfiguration:
        if self._configuration is None:
            raise OmegaCNi8Error("CNi8 reading configuration is not loaded")
        return self._configuration

    @property
    def decimal_places(self) -> int:
        return self.reading_configuration.decimal_places

    @property
    def unit(self) -> str:
        return self.reading_configuration.unit

    @property
    def output_enabled(self) -> bool | None:
        return self._output_enabled

    def connect(self) -> None:
        with self._lock:
            if self.is_connected:
                return
            factory = self._serial_factory
            if factory is None:
                try:
                    import serial
                except ImportError as exc:
                    raise OmegaCNi8Error(
                        "pyserial is required: python -m pip install pyserial"
                    ) from exc
                factory = serial.serial_for_url
                if self.protocol == ISERIES:
                    bytesize, parity = serial.SEVENBITS, serial.PARITY_ODD
                else:
                    bytesize, parity = serial.EIGHTBITS, serial.PARITY_NONE
                stopbits = serial.STOPBITS_ONE
            else:
                bytesize = 7 if self.protocol == ISERIES else 8
                parity = "O" if self.protocol == ISERIES else "N"
                stopbits = 1
            try:
                self._serial = factory(
                    self.port,
                    baudrate=self.baudrate,
                    bytesize=bytesize,
                    parity=parity,
                    stopbits=stopbits,
                    timeout=self.timeout,
                    write_timeout=self.timeout,
                    xonxoff=False,
                    rtscts=False,
                    dsrdtr=False,
                )
                self._clear_locked()
                self.refresh_configuration()
                self.temperature()
            except Exception as exc:
                self._close_locked()
                if isinstance(exc, OmegaCNi8Error):
                    raise
                raise OmegaCNi8Error(
                    f"Could not open CNi8 on {self.port}: {exc}"
                ) from exc

    def disconnect(self) -> None:
        with self._lock:
            self._close_locked()

    def refresh_configuration(self) -> CNi8ReadingConfiguration:
        with self._lock:
            self._require_connected()
            if self.protocol == ISERIES:
                response = self._ascii_query_locked("R08")
                if not re.fullmatch(r"[0-9A-Fa-f]{2}", response):
                    raise OmegaCNi8ProtocolError(
                        f"Unexpected R08 response: {response!r}"
                    )
                raw = int(response, 16)
            else:
                raw = self._modbus_read_locked(8)
            self._configuration = _decode_configuration(raw)
            return self._configuration

    def temperature(self) -> float:
        with self._lock:
            self._require_connected()
            if self.protocol == ISERIES:
                response = self._ascii_query_locked("X01")
                match = NUMBER.fullmatch(response)
                if not match:
                    raise OmegaCNi8ProtocolError(
                        f"Unexpected X01 response: {response!r}"
                    )
                unit = match.group(2)
                if unit and unit.upper() != self.unit:
                    raise OmegaCNi8ProtocolError("CNi8 response unit mismatch")
                return float(match.group(1))
            return _value(
                _signed16(self._modbus_read_locked(39)),
                self.decimal_places,
            )

    read_temperature = temperature

    def persistent_setpoint(self) -> float:
        with self._lock:
            self._require_connected()
            if self.protocol == ISERIES:
                return _decode_setpoint(self._ascii_query_locked("R01"))
            return _value(
                _signed16(self._modbus_read_locked(1)),
                self.decimal_places,
            )

    def setpoint(self) -> float:
        with self._lock:
            self._require_connected()
            if self._volatile_setpoint is not None:
                return self._volatile_setpoint
            return self.persistent_setpoint()

    def set_setpoint(self, value: float, *, persist: bool = False) -> float:
        with self._lock:
            self._require_connected()
            counts = _counts(value, self.decimal_places)
            accepted = _value(counts, self.decimal_places)
            if self.protocol == ISERIES:
                prefix = "W" if persist else "P"
                self._ascii_write_locked(
                    f"{prefix}01{_encode_setpoint(accepted, self.decimal_places)}"
                )
                if persist:
                    self._ascii_write_locked("Z02")
                    self._volatile_setpoint = None
                    self._verify_setpoint_locked(accepted)
                else:
                    self._volatile_setpoint = accepted
                return accepted

            self._modbus_write_locked(1, counts & 0xFFFF)
            actual = self.persistent_setpoint()
            if actual != accepted:
                raise OmegaCNi8ProtocolError(
                    f"Setpoint verify failed: wrote {accepted}, read {actual}"
                )
            self._volatile_setpoint = None
            return accepted

    def output(self, enabled: bool) -> None:
        with self._lock:
            self._require_connected()
            if self.protocol != ISERIES:
                raise OmegaCNi8UnsupportedError(
                    "CNi8 standby/run is documented only in iSeries mode"
                )
            self._ascii_write_locked("E03" if enabled else "D03")
            self._output_enabled = bool(enabled)

    def alarm_status(self) -> CNi8AlarmState:
        with self._lock:
            self._require_connected()
            if self.protocol != ISERIES:
                raise OmegaCNi8UnsupportedError(
                    "CNi8 alarm status is available only in iSeries mode"
                )
            states = {
                "@": CNi8AlarmState(False, False),
                "A": CNi8AlarmState(True, False),
                "B": CNi8AlarmState(False, True),
                "C": CNi8AlarmState(True, True),
            }
            response = self._ascii_query_locked("U01")
            try:
                return states[response]
            except KeyError as exc:
                raise OmegaCNi8ProtocolError(
                    f"Unexpected U01 response: {response!r}"
                ) from exc

    def health(self) -> dict[str, Any]:
        with self._lock:
            alarm = (
                self.alarm_status() if self.protocol == ISERIES else None
            )
            return {
                "device_id": self.device_id,
                "display_name": self.display_name,
                "connected": self.is_connected,
                "port": self.port,
                "protocol": self.protocol,
                "address": self.address,
                "temperature": self.temperature(),
                "setpoint": self.setpoint(),
                "unit": self.unit,
                "decimal_places": self.decimal_places,
                "filter_constant": self.reading_configuration.filter_constant,
                "output_enabled": self.output_enabled,
                "alarms": alarm,
            }

    def _ascii_frame(self, command: str) -> bytes:
        if not re.fullmatch(r"[A-Z][0-9A-F]{2}[0-9A-F]*", command):
            raise ValueError(f"Invalid iSeries command: {command!r}")
        address = "" if self.address is None else f"{self.address:02X}"
        return (
            f"{self.recognition_character}{address}{command}\r".encode("ascii")
        )

    def _ascii_send_locked(self, command: str) -> None:
        frame = self._ascii_frame(command)
        self._clear_locked()
        self._log(f">> {frame[:-1].decode('ascii')}")
        try:
            self._serial.write(frame)
            self._serial.flush()
        except Exception as exc:
            raise OmegaCNi8Error(f"Failed to send {command!r}") from exc

    def _ascii_read_locked(self, command: str) -> str:
        try:
            if hasattr(self._serial, "read_until"):
                raw = self._serial.read_until(b"\r")
            else:
                raw = self._serial.readline()
        except Exception as exc:
            raise OmegaCNi8Error(f"Failed to read response to {command!r}") from exc
        if not raw:
            raise OmegaCNi8TimeoutError(f"Timed out waiting for {command!r}")
        try:
            response = raw.decode("ascii").strip("\x00\r\n ")
        except UnicodeDecodeError as exc:
            raise OmegaCNi8ProtocolError(
                f"CNi8 returned non-ASCII data: {raw!r}"
            ) from exc
        self._log(f"<< {response}")
        if self.address is not None:
            address = f"{self.address:02X}"
            if response.upper().startswith(address):
                response = response[2:]
        if response[:3].upper() in ASCII_ERRORS:
            code = response[:3].upper()
            raise OmegaCNi8ProtocolError(
                f"CNi8 rejected {command!r}: {ASCII_ERRORS[code]} ({code})"
            )
        return response

    def _ascii_query_locked(self, command: str) -> str:
        self._ascii_send_locked(command)
        response = self._ascii_read_locked(command)
        prefix = command[:3]
        if response.upper().startswith(prefix):
            self._echo = True
            return response[3:]
        if self._echo is True:
            raise OmegaCNi8ProtocolError(
                f"Echo mismatch for {command!r}: {response!r}"
            )
        self._echo = False
        return response

    def _ascii_write_locked(self, command: str) -> None:
        self._ascii_send_locked(command)
        if self._echo is False:
            return
        response = self._ascii_read_locked(command)
        if response.upper() != command[:3]:
            raise OmegaCNi8ProtocolError(
                f"Unexpected acknowledgement for {command!r}: {response!r}"
            )
        self._echo = True

    def _verify_setpoint_locked(self, expected: float) -> None:
        last_error: Exception | None = None
        for attempt in range(4):
            if attempt:
                time.sleep(0.15)
            try:
                actual = self.persistent_setpoint()
            except (OmegaCNi8TimeoutError, OmegaCNi8ProtocolError) as exc:
                last_error = exc
                continue
            if actual == expected:
                return
            raise OmegaCNi8ProtocolError(
                f"Setpoint verify failed: wrote {expected}, read {actual}"
            )
        raise OmegaCNi8ProtocolError(
            "CNi8 did not become ready after reset"
        ) from last_error

    def _modbus_read_locked(self, register: int) -> int:
        response = self._modbus_exchange_locked(
            0x03, int(register).to_bytes(2, "big") + b"\x00\x01"
        )
        if len(response) != 2:
            raise OmegaCNi8ProtocolError("Expected one Modbus register")
        return int.from_bytes(response, "big")

    def _modbus_write_locked(self, register: int, value: int) -> None:
        payload = int(register).to_bytes(2, "big") + int(value).to_bytes(2, "big")
        response = self._modbus_exchange_locked(0x06, payload)
        if response != payload:
            raise OmegaCNi8ProtocolError("Modbus write echo mismatch")

    def _modbus_exchange_locked(self, function: int, payload: bytes) -> bytes:
        assert self.address is not None
        body = bytes((self.address, function)) + payload
        request = body + _crc16(body).to_bytes(2, "little")
        self._clear_locked()
        self._log(f">> {request.hex(' ').upper()}")
        try:
            self._serial.write(request)
            self._serial.flush()
            header = self._read_exact_locked(3)
            if header[1] & 0x80:
                response = header + self._read_exact_locked(2)
            elif function in (3, 4):
                response = header + self._read_exact_locked(header[2] + 2)
            else:
                response = header + self._read_exact_locked(5)
        except OmegaCNi8Error:
            raise
        except Exception as exc:
            raise OmegaCNi8Error("Modbus transaction failed") from exc
        self._log(f"<< {response.hex(' ').upper()}")
        self._validate_modbus(response, function)
        if response[1] & 0x80:
            code = response[2]
            raise OmegaCNi8ProtocolError(
                f"Modbus exception {code}: "
                f"{MODBUS_ERRORS.get(code, 'unknown exception')}"
            )
        return (
            response[3 : 3 + response[2]]
            if function in (3, 4)
            else response[2:-2]
        )

    def _read_exact_locked(self, count: int) -> bytes:
        deadline = time.monotonic() + self.timeout
        data = bytearray()
        while len(data) < count and time.monotonic() < deadline:
            chunk = self._serial.read(count - len(data))
            if chunk:
                data.extend(chunk)
        if len(data) != count:
            raise OmegaCNi8TimeoutError(
                f"Received {len(data)} of {count} Modbus bytes"
            )
        return bytes(data)

    def _validate_modbus(self, response: bytes, function: int) -> None:
        if len(response) < 5:
            raise OmegaCNi8ProtocolError("Short Modbus response")
        received = int.from_bytes(response[-2:], "little")
        expected = _crc16(response[:-2])
        if received != expected:
            raise OmegaCNi8ProtocolError("Modbus CRC mismatch")
        if response[0] != self.address:
            raise OmegaCNi8ProtocolError("Modbus address mismatch")
        if response[1] not in {function, function | 0x80}:
            raise OmegaCNi8ProtocolError("Modbus function mismatch")

    def _clear_locked(self) -> None:
        self._serial.reset_input_buffer()
        if hasattr(self._serial, "reset_output_buffer"):
            self._serial.reset_output_buffer()

    def _require_connected(self) -> None:
        if not self._serial or not self._serial.is_open:
            raise OmegaCNi8Error(f"CNi8 port {self.port} is not connected")

    def _close_locked(self) -> None:
        serial_port = self._serial
        self._serial = None
        self._configuration = None
        self._volatile_setpoint = None
        self._output_enabled = None
        if serial_port is not None:
            try:
                serial_port.close()
            except Exception:
                pass

    def _log(self, message: str) -> None:
        if self._log_callback:
            self._log_callback(message)
