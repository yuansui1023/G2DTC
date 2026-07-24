from __future__ import annotations

import unittest

from g2dtc.drivers.esp300 import build_esp300_axes
from g2dtc.drivers.omega_cni8 import (
    CNi8AlarmState,
    OmegaCNi8Driver,
    _crc16,
    _decode_setpoint,
    _encode_setpoint,
)
from g2dtc.drivers.pzc200 import PZC200MotorDriver


class FakeESPSerial:
    def __init__(self, *_args, **kwargs) -> None:
        self.is_open = True
        self.commands: list[str] = []
        self.response = b""

    def reset_input_buffer(self) -> None:
        self.response = b""

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.is_open = False

    def write(self, data: bytes) -> int:
        command = data.decode("ascii").strip()
        self.commands.append(command)
        responses = {
            "VE?": "ESP300 Version 3.0",
            "1SN?": "2",
            "2SN?": "2",
            "1VU?": "10",
            "2VU?": "10",
            "1TP": "1.25",
            "1MD?": "1",
            "1MO?": "1",
            "1SL?": "-10",
            "1SR?": "10",
        }
        if command in responses:
            self.response = (responses[command] + "\r\n").encode("ascii")
        return len(data)

    def readline(self) -> bytes:
        response = self.response
        self.response = b""
        return response


class FakePZSerial:
    def __init__(self, *_args, **kwargs) -> None:
        self.is_open = True
        self.commands: list[str] = []
        self.response = bytearray()

    def reset_input_buffer(self) -> None:
        self.response.clear()

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.is_open = False

    def write(self, data: bytes) -> int:
        command = data.decode("ascii").strip()
        self.commands.append(command)
        if command.endswith("?"):
            body = command[1:-1]
            values = {
                "VE": "PZC200 v1",
                "TP": "123",
                "TS": "81",
                "TE": "0",
                "SL": "-1000",
                "SR": "1000",
            }
            value = values.get(body, "0")
            self.response.extend(f"{command} {value}\r".encode("ascii"))
        return len(data)

    def read(self, count: int) -> bytes:
        data = bytes(self.response[:count])
        del self.response[:count]
        return data


class FakeCNiAsciiSerial:
    def __init__(self, *_args, **kwargs) -> None:
        self.is_open = True
        self.commands: list[str] = []
        self.response = bytearray()
        self.persistent = "20012C"  # 30.0

    def reset_input_buffer(self) -> None:
        self.response.clear()

    def reset_output_buffer(self) -> None:
        pass

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.is_open = False

    def write(self, data: bytes) -> int:
        command = data.decode("ascii").strip()[1:]
        self.commands.append(command)
        if command == "R08":
            response = "R0842"  # Celsius, one decimal, filter 4
        elif command == "X01":
            response = "X01025.3"
        elif command == "R01":
            response = "R01" + self.persistent
        elif command == "U01":
            response = "U01@"
        elif command.startswith("W01"):
            self.persistent = command[3:]
            response = "W01"
        else:
            response = command[:3]
        self.response.extend((response + "\r").encode("ascii"))
        return len(data)

    def read_until(self, _terminator: bytes) -> bytes:
        data = bytes(self.response)
        self.response.clear()
        return data


class FakeCNiModbusSerial:
    def __init__(self, *_args, **kwargs) -> None:
        self.is_open = True
        self.timeout = kwargs["timeout"]
        self.response = bytearray()
        self.registers = {1: 300, 8: 0x42, 39: 253}

    def reset_input_buffer(self) -> None:
        self.response.clear()

    def reset_output_buffer(self) -> None:
        pass

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.is_open = False

    def write(self, frame: bytes) -> int:
        body = frame[:-2]
        self.assert_crc(frame)
        address, function = body[:2]
        register = int.from_bytes(body[2:4], "big")
        if function == 3:
            value = self.registers[register] & 0xFFFF
            response_body = bytes((address, function, 2)) + value.to_bytes(
                2, "big"
            )
        elif function == 6:
            self.registers[register] = int.from_bytes(body[4:6], "big")
            response_body = body
        else:
            raise AssertionError(function)
        self.response.extend(
            response_body + _crc16(response_body).to_bytes(2, "little")
        )
        return len(frame)

    def read(self, count: int) -> bytes:
        data = bytes(self.response[:count])
        del self.response[:count]
        return data

    @staticmethod
    def assert_crc(frame: bytes) -> None:
        assert _crc16(frame[:-2]) == int.from_bytes(frame[-2:], "little")


class HardwareProtocolTests(unittest.TestCase):
    def test_esp_axes_share_one_serial_connection(self) -> None:
        created: list[FakeESPSerial] = []

        def factory(*args, **kwargs):
            serial = FakeESPSerial(*args, **kwargs)
            created.append(serial)
            return serial

        axes = build_esp300_axes("FAKE", serial_factory=factory)
        axis1 = axes["esp300.axis1"]
        axis2 = axes["esp300.axis2"]
        axis1.connect()
        axis2.connect()
        self.assertEqual(len(created), 1)
        self.assertEqual(axis1.position(), 1.25)
        axis1.move_relative(0.5)
        self.assertIn("1PR0.5", created[0].commands)
        axis1.disconnect()
        self.assertTrue(created[0].is_open)
        axis2.disconnect()
        self.assertFalse(created[0].is_open)

    def test_pzc200_protocol(self) -> None:
        serials: list[FakePZSerial] = []

        def factory(*args, **kwargs):
            serial = FakePZSerial(*args, **kwargs)
            serials.append(serial)
            return serial

        motor = PZC200MotorDriver("FAKE", serial_factory=factory)
        motor.connect()
        self.assertEqual(motor.position(), 123.0)
        motor.move_relative(50)
        self.assertIn("0PR50", serials[0].commands)
        self.assertEqual(motor.limits(), (-1000.0, 1000.0))
        motor.disconnect()

    def test_cni8_manual_vectors(self) -> None:
        self.assertEqual(_decode_setpoint("2003E8"), 100.0)
        self.assertEqual(_decode_setpoint("A003E8"), -100.0)
        self.assertEqual(_encode_setpoint(100.0, 1), "2003E8")
        request = bytes.fromhex("01 03 00 01 00 01")
        self.assertEqual(
            _crc16(request).to_bytes(2, "little"),
            bytes.fromhex("D5 CA"),
        )

    def test_cni8_ascii(self) -> None:
        controller = OmegaCNi8Driver(
            "FAKE", serial_factory=FakeCNiAsciiSerial
        )
        controller.connect()
        self.assertEqual(controller.temperature(), 25.3)
        self.assertEqual(controller.unit, "C")
        self.assertEqual(controller.persistent_setpoint(), 30.0)
        self.assertEqual(controller.set_setpoint(42.46), 42.5)
        self.assertEqual(controller.setpoint(), 42.5)
        controller.output(False)
        self.assertFalse(controller.output_enabled)
        self.assertEqual(
            controller.alarm_status(),
            CNi8AlarmState(False, False),
        )
        controller.set_setpoint(-10.0, persist=True)
        self.assertEqual(controller.persistent_setpoint(), -10.0)
        controller.disconnect()

    def test_cni8_modbus(self) -> None:
        controller = OmegaCNi8Driver(
            "FAKE",
            protocol="modbus",
            serial_factory=FakeCNiModbusSerial,
        )
        controller.connect()
        self.assertEqual(controller.temperature(), 25.3)
        self.assertEqual(controller.setpoint(), 30.0)
        self.assertEqual(controller.set_setpoint(-5.5), -5.5)
        self.assertEqual(controller.setpoint(), -5.5)
        controller.disconnect()


if __name__ == "__main__":
    unittest.main()
