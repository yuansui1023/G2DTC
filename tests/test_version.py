from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from g2dtc.version import REPOSITORY_URL, current_commit_sha, source_url


class VersionMetadataTests(unittest.TestCase):
    def test_environment_commit_override(self) -> None:
        with patch.dict(
            os.environ,
            {"G2DTC_COMMIT_SHA": "1234567890abcdef"},
        ):
            self.assertEqual(current_commit_sha(), "1234567")

    def test_missing_repository_returns_unavailable(self) -> None:
        with TemporaryDirectory() as directory:
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(
                    current_commit_sha(Path(directory)),
                    "unavailable",
                )

    def test_source_url_links_to_commit_when_available(self) -> None:
        self.assertEqual(
            source_url("1234567"),
            f"{REPOSITORY_URL}/commit/1234567",
        )
        self.assertEqual(source_url("unavailable"), REPOSITORY_URL)


if __name__ == "__main__":
    unittest.main()
