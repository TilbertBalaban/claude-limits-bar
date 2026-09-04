import unittest

from claude_usage_bar.update import is_newer


class TestIsNewer(unittest.TestCase):
    def test_newer(self):
        self.assertTrue(is_newer("1.1.0", "1.0.5"))
        self.assertTrue(is_newer("2.0.0", "1.9.9"))
        self.assertTrue(is_newer("1.0.10", "1.0.9"))

    def test_not_newer(self):
        self.assertFalse(is_newer("1.0.5", "1.0.5"))
        self.assertFalse(is_newer("1.0.4", "1.0.5"))

    def test_garbage(self):
        self.assertFalse(is_newer(None, "1.0.5"))
        self.assertFalse(is_newer("", "1.0.5"))
        self.assertFalse(is_newer("not-a-version", "1.0.5"))


if __name__ == "__main__":
    unittest.main()
