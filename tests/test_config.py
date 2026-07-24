from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from g2dtc.config import (
    MANUAL_ASSIGNMENT,
    SLOTS,
    AppConfig,
    is_hardware_assignment,
    load_config,
    save_config,
)


class ConfigTests(unittest.TestCase):
    def test_default_starts_with_every_slot_unassigned(self) -> None:
        config = AppConfig()
        self.assertEqual(len(SLOTS), 11)
        self.assertTrue(
            all(value is None for value in config.assignments.values())
        )

    def test_legacy_default_simulation_assignments_are_cleared(self) -> None:
        assignments: dict[str, str] = {}
        motor_index = 1
        for slot in SLOTS:
            if slot.kind == "temperature":
                assignments[slot.key] = "sim.temperature.1"
            else:
                assignments[slot.key] = f"sim.motor.{motor_index}"
                motor_index += 1
        config = AppConfig.from_dict(
            {
                "version": 1,
                "simulation": True,
                "devices": [],
                "assignments": assignments,
            }
        )
        self.assertTrue(
            all(value is None for value in config.assignments.values())
        )

    def test_assignment_is_exclusive(self) -> None:
        config = AppConfig()
        config.assign(
            "transfer_arm.x",
            "sim.motor.1",
            device_kind="motor",
        )
        cleared = config.assign(
            "stage.x",
            "sim.motor.1",
            device_kind="motor",
        )
        self.assertEqual(cleared, "transfer_arm.x")
        self.assertIsNone(config.assignments["transfer_arm.x"])
        self.assertEqual(config.assignments["stage.x"], "sim.motor.1")

    def test_manual_assignment_is_not_exclusive(self) -> None:
        config = AppConfig()
        config.assign("stage.x", MANUAL_ASSIGNMENT)
        config.assign("stage.y", MANUAL_ASSIGNMENT)
        self.assertEqual(config.assignments["stage.x"], MANUAL_ASSIGNMENT)
        self.assertEqual(config.assignments["stage.y"], MANUAL_ASSIGNMENT)

    def test_only_hardware_assignments_create_dashboard_modules(self) -> None:
        self.assertFalse(is_hardware_assignment(None))
        self.assertFalse(is_hardware_assignment(MANUAL_ASSIGNMENT))
        self.assertTrue(is_hardware_assignment("esp300.stage.axis1"))

    def test_kind_mismatch_is_rejected(self) -> None:
        config = AppConfig()
        with self.assertRaises(ValueError):
            config.assign(
                "stage.temperature",
                "sim.motor.1",
                device_kind="motor",
            )

    def test_json_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            original = AppConfig()
            original.assign("stage.rz", MANUAL_ASSIGNMENT)
            save_config(original, path)
            loaded = load_config(path)
            self.assertEqual(loaded.to_dict(), original.to_dict())


if __name__ == "__main__":
    unittest.main()
