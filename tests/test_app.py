import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import app as A
import minikit


class StatsTests(unittest.TestCase):
    def test_median(self):
        self.assertEqual(A.median([3, 1, 2]), 2)
        self.assertEqual(A.median([1, 2, 3, 4]), 2.5)
        self.assertIsNone(A.median([]))

    def test_suspicious(self):
        self.assertTrue(A.is_suspicious(50000, [1000, 1100, 900]))
        self.assertFalse(A.is_suspicious(1200, [1000, 1100, 900]))
        self.assertFalse(A.is_suspicious(5, []))

    def test_trend(self):
        self.assertEqual(A.trend(1100, 1000), 10)
        self.assertIsNone(A.trend(1100, None))


class AppTests(minikit.AppTestCase):
    site = A.site

    def report(self, price, day="2026-10-20"):
        return self.post("/report", market_id="1", commodity="Beans", unit="kg", price=str(price), reported_on=day)

    def test_board_shows_median(self):
        for p in (2000, 2200, 2400):
            self.report(p)
        body = self.get("/?today=2026-10-22")[1]
        self.assertIn("Beans", body)
        self.assertIn("UGX 2,200", body)

    def test_outlier_hidden(self):
        for p in (2000, 2100, 1900):
            self.report(p)
        self.assertIn("unusual", self.report(90000)[2])
        self.assertNotIn("90,000", self.get("/?today=2026-10-22")[1])

    def test_zero_rejected(self):
        self.assertIn("more than zero", self.report(0)[2])


if __name__ == "__main__":
    unittest.main()
