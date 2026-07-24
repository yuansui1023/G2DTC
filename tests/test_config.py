from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from g2dtc.config import (
    MANUAL_ASSIGNMENT,
    SLOTS,
    AppConfig,
    load_config,
    save_config,
)


class ConfigTests(unittest.TestCase):
    def test_default_covers_ten_motors_and_temperature(self) -> None:
        config = AppConfig()
        self.assertEqual(len(SLOTS), 11)
        self.assertEqual(
            len(
                {
                    value
                    for value in config.assignments.values()
                    if value and value.startswith("sim.motor.")
                }
            ),
            10,
        )
        self.assertEqual(
            config.assignments["stage.temperature"],
            "sim.temperature.1",
        )

    def test_assignment_is_exclusive(self) -> None:
        config = AppConfig()
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
