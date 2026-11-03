"""Unit tests for scheduling.parse_operating_hours (SCRUM-36 A2, SCRUM-64): hours that
can't be used are None, so the calendar shows "hours not recorded" rather than guessing."""

import unittest
from datetime import time

from app.venues import scheduling


class ParseOperatingHoursTests(unittest.TestCase):
    def test_day_ranges_and_single_days(self):
        hours = scheduling.parse_operating_hours("Mon-Fri 09:00-18:00, Sat 10:00-14:00")
        self.assertEqual(hours[0], (time(9), time(18)))
        self.assertEqual(hours[4], (time(9), time(18)))
        self.assertEqual(hours[5], (time(10), time(14)))
        self.assertNotIn(6, hours)

    def test_hours_that_cannot_be_used_are_none(self):
        for text in ("Mon-Xyz 09:00-18:00",   # not a day
                     "Mon-Fri 25:00-26:00",   # not a time
                     "Mon-Fri 18:00-09:00",   # closes before it opens
                     "Mon-Fri 09:00-09:00",   # open for no time
                     "By appointment", "   ", None):
            with self.subTest(text=text):
                self.assertIsNone(scheduling.parse_operating_hours(text))


if __name__ == "__main__":
    unittest.main()
