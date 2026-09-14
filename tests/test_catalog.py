from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]


class CatalogTest(unittest.TestCase):
    def test_generated_catalog_is_current(self) -> None:
        subprocess.run(
            [sys.executable, "scripts/build_catalog.py", "--check"],
            cwd=ROOT,
            check=True,
        )

    def test_packages_contain_declared_entries(self) -> None:
        catalog = json.loads((ROOT / "dist/catalog.json").read_text())
        for app in catalog["apps"]:
            archive = ROOT / "dist" / app["archive"]
            with zipfile.ZipFile(archive) as package:
                self.assertIn("manifest.json", package.namelist())
                self.assertIn(app["entry"], package.namelist())

    def test_packages_have_platform_independent_metadata(self) -> None:
        catalog = json.loads((ROOT / "dist/catalog.json").read_text())
        for app in catalog["apps"]:
            archive = ROOT / "dist" / app["archive"]
            with zipfile.ZipFile(archive) as package:
                for info in package.infolist():
                    self.assertEqual(info.create_system, 3)
                    self.assertEqual(info.date_time, (2020, 1, 1, 0, 0, 0))

    def test_packages_contain_current_source_bytes(self) -> None:
        catalog = json.loads((ROOT / "dist/catalog.json").read_text())
        for app in catalog["apps"]:
            app_directory = ROOT / "apps" / app["id"]
            source_files = sorted(
                path
                for path in app_directory.rglob("*")
                if path.is_file() and path.name != "manifest.json"
            )
            archive = ROOT / "dist" / app["archive"]
            with zipfile.ZipFile(archive) as package:
                packaged_files = set(package.namelist()) - {"manifest.json"}
                expected_files = {
                    path.relative_to(app_directory).as_posix()
                    for path in source_files
                }
                self.assertEqual(packaged_files, expected_files)
                for source in source_files:
                    relative = source.relative_to(app_directory).as_posix()
                    self.assertEqual(package.read(relative), source.read_bytes())


if __name__ == "__main__":
    unittest.main()
