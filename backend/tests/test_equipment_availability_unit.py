"""SCRUM-43: the equipment availability rules on plain objects (no app, no database).

See docs/test-cases/SCRUM-43-equipment-availability.md. Which unavailable periods
overlap the event is decided by the database query (scheduling.overlapping), so here
`unavailable` already holds only the overlapping periods, by item id.
"""

import unittest
from datetime import datetime
from types import SimpleNamespace


def _rules():
    # Imported here so the tests fail on behaviour, not on import, until it exists.
    from app.resources import availability

    return availability


def item(id, name, category, quantity):
    return SimpleNamespace(id=id, name=name, category=category, quantity_available=quantity)


def need(equipment_type, quantity, technical=None, id=1):
    return SimpleNamespace(id=id, equipment_type=equipment_type, quantity=quantity,
                           technical_requirements=technical)


def period(reason="Lamp replacement"):
    return SimpleNamespace(start_time=datetime(2026, 12, 5, 17, 0),
                           end_time=datetime(2026, 12, 5, 19, 0), reason=reason)


MICS = [item(1, "Shure SLX-D", "Wireless microphone", 2),
        item(2, "Sennheiser EW-D", "wireless  MICROPHONE", 2),
        item(3, "Epson EB-L", "Projector", 1),
        item(4, "Unlabelled", None, 9)]


class EquipmentAvailabilityRuleTests(unittest.TestCase):
    def check(self, requirement, resources=MICS, unavailable=None):
        return _rules().check(requirement, resources, unavailable or {})

    def test_types_match_categories_ignoring_case_and_spacing(self):  # A2
        line = self.check(need("  WIRELESS microphone ", 3))
        self.assertEqual([s["name"] for s in line["suitable"]], ["Shure SLX-D", "Sennheiser EW-D"])
        self.assertEqual(line["available_quantity"], 4)

    def test_an_item_without_a_category_is_never_suitable(self):  # A2
        line = self.check(need("None", 1))
        self.assertEqual((line["suitable"], line["excluded"]), ([], []))

    def test_enough_at_exactly_the_requested_quantity(self):  # A7
        self.assertEqual(self.check(need("Wireless microphone", 4))["result"], "enough")
        self.assertEqual(self.check(need("Wireless microphone", 5))["result"], "not_enough")

    def test_none_suitable_when_nothing_is_available(self):  # A7
        line = self.check(need("Hologram projector", 1))
        self.assertEqual((line["available_quantity"], line["result"]), (0, "none_suitable"))
        self.assertEqual(line["result_label"], "No suitable equipment available")

    def test_an_item_with_no_quantity_recorded_is_excluded_not_counted(self):  # A4
        resources = [item(5, "JBL EON", "Speaker", None), item(6, "Bose S1", "Speaker", 1)]
        line = self.check(need("Speaker", 2), resources)
        self.assertEqual(line["available_quantity"], 1)
        self.assertEqual([(e["name"], e["reason"]) for e in line["excluded"]],
                         [("JBL EON", "quantity_not_recorded")])
        self.assertEqual(line["result"], "not_enough")

    def test_an_unavailable_item_is_excluded_with_its_reason_and_period(self):  # A5
        line = self.check(need("Projector", 1), unavailable={3: [period()]})
        self.assertEqual((line["available_quantity"], line["result"]), (0, "none_suitable"))
        [excluded] = line["excluded"]
        self.assertEqual((excluded["name"], excluded["reason"]), ("Epson EB-L", "unavailable"))
        self.assertIn("Lamp replacement", excluded["detail"])
        self.assertIn("2026-12-05 17:00", excluded["detail"])
        self.assertIn("2026-12-05 19:00", excluded["detail"])

    def test_an_unavailable_period_without_a_reason_still_excludes(self):  # A5
        line = self.check(need("Projector", 1), unavailable={3: [period(reason=None)]})
        self.assertEqual(line["available_quantity"], 0)
        self.assertIn("no reason recorded", line["excluded"][0]["detail"])

    def test_technical_requirements_are_shown_for_technical_support_to_confirm(self):  # A3
        line = self.check(need("Wireless microphone", 1, technical="Lapel"))
        self.assertEqual(line["technical_requirements"], "Lapel")
        self.assertIn("Lapel", line["technical_note"])
        self.assertIn("confirm", line["technical_note"])
        self.assertIsNone(self.check(need("Wireless microphone", 1))["technical_note"])

    def test_the_line_names_the_requirement(self):  # AC2
        line = self.check(need("Wireless microphone", 3, id=42))
        self.assertEqual((line["requirement_id"], line["equipment_type"], line["requested_quantity"]),
                         (42, "Wireless microphone", 3))

    def test_the_summary_counts_the_requirements_that_can_be_met(self):  # A7
        rules = _rules()
        lines = [self.check(need("Wireless microphone", 3)), self.check(need("Hologram projector", 1))]
        self.assertEqual(rules.summary(lines), "1 of 2 equipment requirements can be met from available equipment.")
        self.assertEqual(rules.summary(lines[:1]),
                         "Every equipment requirement can be met from available equipment.")
        self.assertIsNone(rules.summary([]))

    # ---------- Review of PR #48 ----------

    def check_all(self, *requirements, resources=MICS, unavailable=None):
        return _rules().check_all(list(requirements), resources, unavailable or {})

    def test_requirements_for_the_same_equipment_share_its_stock(self):  # A11
        lapel, handheld = self.check_all(need("Wireless microphone", 3, id=1),
                                         need("wireless  MICROPHONE", 3, id=2))
        for line, other in ((lapel, 2), (handheld, 1)):
            self.assertEqual(line["available_quantity"], 4)
            self.assertEqual(line["shared_requested_quantity"], 6)
            self.assertEqual(line["shared_with"], [other])
            self.assertEqual(line["result"], "not_enough")
            self.assertIn("together 6 requested, 4 available", line["shared_note"])

    def test_shared_stock_that_covers_every_requirement_is_enough(self):  # A11
        lines = self.check_all(need("Wireless microphone", 2, id=1),
                               need("Wireless microphone", 2, id=2))
        self.assertEqual([line["result"] for line in lines], ["enough", "enough"])
        self.assertIn("together 4 requested, 4 available", lines[0]["shared_note"])

    def test_different_equipment_does_not_share_stock(self):  # A11
        mics, projector = self.check_all(need("Wireless microphone", 4, id=1),
                                         need("Projector", 1, id=2))
        self.assertEqual((mics["shared_with"], mics["shared_note"], mics["result"]),
                         ([], None, "enough"))
        self.assertEqual(projector["shared_with"], [])

    def test_enough_by_category_is_not_confirmed_technical_suitability(self):  # A3
        line = self.check(need("Wireless microphone", 1, technical="Lapel"))
        self.assertEqual(line["result"], "enough_by_category")
        self.assertEqual(line["result_label"],
                         "Enough by category; technical requirements still to be checked")
        self.assertEqual(self.check(need("Wireless microphone", 1))["result"], "enough")

    def test_too_few_stays_not_enough_whatever_the_technical_requirements(self):  # A3
        line = self.check(need("Wireless microphone", 9, technical="Lapel"))
        self.assertEqual(line["result"], "not_enough")

    def test_the_summary_counts_unconfirmed_requirements_separately(self):  # A3
        rules = _rules()
        lines = [self.check(need("Wireless microphone", 1)),
                 self.check(need("Wireless microphone", 1, technical="Lapel")),
                 self.check(need("Hologram projector", 1))]
        self.assertEqual(rules.summary(lines),
                         "1 of 3 equipment requirements can be met from available equipment. "
                         "1 more has enough by category, but its technical requirements are "
                         "still to be checked.")
        self.assertEqual(rules.summary(lines[1:2]),
                         "0 of 1 equipment requirements can be met from available equipment. "
                         "1 more has enough by category, but its technical requirements are "
                         "still to be checked.")

    def test_nothing_says_reserved_booked_or_confirmed(self):  # AC4
        # The text shown, not the field names: since SCRUM-44 each item has a number
        # under "reserved_for_other_events", which says nothing was reserved here.
        for requirement in (need("Wireless microphone", 3), need("Hologram projector", 1),
                            need("Wireless microphone", 1, technical="Lapel")):
            text = " ".join(texts(self.check(requirement))).lower()
            for word in ("reserved", "booked", "confirmed"):
                self.assertNotIn(word, text)


def texts(value):
    """Every piece of text in a result, at any depth, without the field names."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in texts(item)]
    if isinstance(value, (list, tuple)):
        return [text for item in value for text in texts(item)]
    return []


if __name__ == "__main__":
    unittest.main()
