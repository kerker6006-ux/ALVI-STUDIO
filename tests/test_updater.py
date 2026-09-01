from __future__ import annotations

import unittest

from dubstudio.updater import _version


class UpdaterTests(unittest.TestCase):
    def test_semantic_versions_compare_numerically(self) -> None:
        self.assertGreater(_version("v1.10.0"), _version("1.9.9"))
        self.assertEqual(_version("v2.0.0"), (2, 0, 0))


if __name__ == "__main__":
    unittest.main()

