"""Behavior checks for the PySide6 application shell."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "minimal")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from g2dtc.config import MANUAL_ASSIGNMENT
from g2dtc.ui import (
    APP_STYLESHEET,
    G2DTCWindow,
    ModernComboBox,
    MotorCard,
)


class UserInterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_app = QApplication.instance() or QApplication([])
        cls.qt_app.setStyle("Fusion")
        cls.qt_app.setStyleSheet(APP_STYLESHEET)

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        config_path = Path(self.temporary_directory.name) / "config.json"
        self.window = G2DTCWindow(config_path)

    def tearDown(self) -> None:
        self.window.close()
        self.qt_app.processEvents()
        self.temporary_directory.cleanup()

    def test_manual_slots_do_not_create_dashboard_cards(self) -> None:
        self.assertEqual(self.window.dashboard.cards, [])
        self.assertEqual(
            self.window.dashboard.horizontalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        )
        self.assertEqual(
            self.window.dashboard.verticalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        )

    def test_assignment_creates_one_resizable_motor_card(self) -> None:
        driver = self.window.registry.require("sim.motor.1")
        self.window.config.assign(
            "transfer_arm.x",
            driver.device_id,
            device_kind=driver.kind,
        )
        self.window.rebuild_views(selected_tab=0)

        self.assertEqual(len(self.window.dashboard.cards), 1)
        card = self.window.dashboard.cards[0]
        self.assertIsInstance(card, MotorCard)
        card.setFixedSize(520, 510)
        self.window.store_module_size(card.module_key, card.size())
        self.assertEqual(
            self.window.module_sizes["transfer_arm.x"],
            (520, 510),
        )

    def test_assignment_selector_uses_manual_and_modern_combo(self) -> None:
        self.window.set_current_page(1)
        page = self.window.stack.currentWidget()
        combo = page.combos["stage.x"]

        self.assertIsInstance(combo, ModernComboBox)
        self.assertEqual(combo.itemText(0), "Manual")
        self.assertEqual(
            self.window.config.assignments["stage.x"],
            MANUAL_ASSIGNMENT,
        )
        self.assertEqual(combo.arrow.text(), "⌄")
        combo.setCurrentText("Sim Motor 01")
        self.qt_app.processEvents()
        self.assertEqual(
            self.window.config.assignments["stage.x"],
            "sim.motor.1",
        )
        self.assertEqual(len(self.window.dashboard.cards), 1)

    def test_version_metadata_uses_seven_character_sha(self) -> None:
        if self.window.commit_sha != "unavailable":
            self.assertEqual(len(self.window.commit_sha), 7)


if __name__ == "__main__":
    unittest.main()
