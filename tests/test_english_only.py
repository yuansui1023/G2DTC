from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
CJK_PATTERN = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"
)
SKIPPED_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "venv",
}


class EnglishOnlyTests(unittest.TestCase):
    def test_repository_text_files_do_not_contain_cjk_characters(self) -> None:
        violations: list[str] = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if any(
                part in SKIPPED_DIRECTORIES or part.endswith(".egg-info")
                for part in path.parts
            ):
                continue
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if CJK_PATTERN.search(line):
                    violations.append(
                        f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}"
                    )
        self.assertEqual([], violations, "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
