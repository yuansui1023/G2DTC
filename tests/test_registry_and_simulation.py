from __future__ import annotations

import time
import unittest

from g2dtc.config import AppConfig
from g2dtc.drivers.simulated import (
    SimulatedMotorDriver,
    SimulatedTemperatureDriver,
)
from g2dtc.registry import DeviceRegistry


class RegistryTests(unittest.TestCase):
    def test_default_registry(self) -> None:
        registry = DeviceRegistry(AppConfig())
        self.assertEqual(len(registry.drivers("motor")), 10)
        self.assertEqual(len(registry.drivers("temperature")), 1)
        registry.shutdown()

    def test_all_hardware_types_build_without_connecting(self) -> None:
        config = AppConfig.from_dict(
            {
                "version": 1,
                "simulation": False,
                "devices": [
                    {
                        "type": "esp300",
                        "id": "esp",
                        "port": "COM1",
                        "axes": [1, 3],
                    },
                    {
                        "type": "pzc200",
                        "id": "pzc",
                        "port": "COM2",
                    },
                    {
                        "type": "omega_cni8",
                        "id": "temp",
                        "port": "COM3",
                    },
                ],
                "assignments": {},
            }
        )
        registry = DeviceRegistry(config)
        self.assertEqual(
            {driver.device_id for driver in registry.drivers()},
            {"esp.axis1", "esp.axis3", "pzc", "temp"},
        )


class SimulationTests(unittest.TestCase):
    def test_motor_motion_and_stop(self) -> None:
        motor = SimulatedMotorDriver("motor")
        motor.connect()
        motor.move_relative(2.5)
        self.assertEqual(motor.position(), 2.5)
        motor.jog(1, 10)
        time.sleep(0.02)
        motor.stop()
        self.assertGreater(motor.position(), 2.5)
        motor.zero()
        self.assertAlmostEqual(motor.position(), 0.0, places=5)

    def test_temperature_approaches_setpoint(self) -> None:
        temperature = SimulatedTemperatureDriver(ambient=22.0)
        temperature.connect()
        temperature.set_setpoint(30)
        temperature.output(True)
        time.sleep(0.02)
        self.assertGreater(temperature.temperature(), 22.0)
        self.assertEqual(temperature.setpoint(), 30.0)


if __name__ == "__main__":
    unittest.main()
