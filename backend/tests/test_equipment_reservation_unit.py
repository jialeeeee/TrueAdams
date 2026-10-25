"""SCRUM-44 reservation rules, run on plain objects without a database.

The same rules are exercised through the API in test_equipment_reservation.py; these
pin down the edge cases. See docs/test-cases/SCRUM-44-reserve-equipment.md (A5, A6).
"""

import unittest
from types import SimpleNamespace

from app.resources import availability


def _reservations():
    # Imported here so the tests fail on behaviour, not on import, until it exists.
    from app.resources import reservations

    return reservations


def item(id, name, category, quantity):
    return SimpleNamespace(id=id, name=name, category=category, quantity_available=quantity)


def requirement(id=1, equipment_type="Wireless microphone", quantity=3, technical=None):
    return SimpleNamespace(id=id, equipment_type=equipment_type, quantity=quantity,
                           technical_requirements=technical)


SHURE = item(10, "Shure SLX-D", "Wireless microphone", 2)
SENNHEISER = item(11, "Sennheiser EW-D", "wireless  MICROPHONE", 2)
BENQ = item(12, "BenQ LU935", "Projector", 2)


class DeductionRuleTests(unittest.TestCase):
    """availability.check with the quantities other overlapping events have reserved."""

    def test_reserved_quantities_are_deducted_from_each_item(self):
        line = availability.check(requirement(), [SHURE, SENNHEISER], {}, reserved={10: 1})

        self.assertEqual(
            [(s["name"], s["quantity_available"], s["reserved_for_other_events"],
              s["available_quantity"]) for s in line["suitable"]],
            [("Shure SLX-D", 2, 1, 1), ("Sennheiser EW-D", 2, 0, 2)])
        self.assertEqual(line["available_quantity"], 3)

    def test_an_item_never_has_less_than_nothing_available(self):
        line = availability.check(requirement(), [SHURE], {}, reserved={10: 5})

        self.assertEqual(line["suitable"][0]["available_quantity"], 0)
        self.assertEqual(line["available_quantity"], 0)
        self.assertEqual(line["result"], availability.NONE_SUITABLE)

    def test_without_reservations_the_check_is_unchanged(self):
        line = availability.check(requirement(), [SHURE, SENNHEISER], {})

        self.assertEqual(line["available_quantity"], 4)
        self.assertEqual({s["reserved_for_other_events"] for s in line["suitable"]}, {0})

    def test_check_all_passes_the_reservations_on(self):
        lines = availability.check_all([requirement()], [SHURE], {}, reserved={10: 2})

        self.assertEqual(lines[0]["available_quantity"], 0)


class OptionRuleTests(unittest.TestCase):
    def test_this_events_own_reservations_are_taken_off_what_it_can_still_reserve(self):
        line = availability.check(requirement(), [SHURE, SENNHEISER], {}, reserved={11: 1})

        options = _reservations().options(line, reserved_here={10: 2})

        self.assertEqual([(o["name"], o["reserved_for_other_events"], o["reserved_for_this_event"],
                           o["available_to_reserve"]) for o in options],
                         [("Shure SLX-D", 0, 2, 0), ("Sennheiser EW-D", 1, 0, 1)])

    def test_what_can_be_reserved_is_never_negative(self):
        line = availability.check(requirement(), [SHURE], {}, reserved={10: 1})

        [option] = _reservations().options(line, reserved_here={10: 2})

        self.assertEqual(option["available_to_reserve"], 0)

    def test_state_of_a_requirement(self):
        state = _reservations().state
        self.assertEqual(state(remaining=0, available=0), "fully_reserved")
        self.assertEqual(state(remaining=0, available=4), "fully_reserved")
        self.assertEqual(state(remaining=2, available=0), "none_available")
        self.assertEqual(state(remaining=2, available=1), "can_reserve")

    def test_an_event_that_cannot_be_reserved_for_says_so_whatever_is_available(self):
        # SCRUM-44 review: a submitted event said "can be reserved", an undated one
        # "no suitable equipment".
        state = _reservations().state
        self.assertEqual(state(remaining=2, available=1, reservable=False), "not_reservable")
        self.assertEqual(state(remaining=2, available=0, reservable=False), "not_reservable")
        self.assertEqual(state(remaining=0, available=0, reservable=False), "fully_reserved")


class SelectionRuleTests(unittest.TestCase):
    def parse(self, items):
        return _reservations().parse_items(items)

    def test_a_valid_selection_is_kept_in_order(self):
        selection, problems = self.parse([{"resource_id": 11, "quantity": 1},
                                          {"resource_id": 10, "quantity": 2}])

        self.assertEqual(problems, [])
        self.assertEqual(selection, [(11, 1), (10, 2)])

    def test_bad_quantities_and_items_are_problems(self):
        for items in ([{"resource_id": 10, "quantity": value}]
                      for value in (0, -1, 1001, 1.5, "2", True, None)):
            with self.subTest(items=items):
                _, problems = self.parse(items)
                self.assertTrue(any("whole number from 1 to 1000" in p for p in problems), problems)
        for items in ([], None, "Shure", [5], [{"quantity": 1}],
                      [{"resource_id": "10", "quantity": 1}], [{"resource_id": True, "quantity": 1}]):
            with self.subTest(items=items):
                _, problems = self.parse(items)
                self.assertTrue(problems)

    def check(self, selection, remaining=3, resources=(SHURE, SENNHEISER, BENQ)):
        return _reservations().selection_problems(
            selection, {r.id: r for r in resources}, requirement(), remaining)

    def test_items_must_exist_suit_the_requirement_and_be_chosen_once(self):
        self.assertEqual(self.check([(10, 1), (11, 2)]), [])
        self.assertIn("was not found", " ".join(self.check([(99, 1)])))
        self.assertIn("BenQ LU935 is not suitable", " ".join(self.check([(12, 1)])))
        self.assertIn("Shure SLX-D is selected more than once", " ".join(self.check([(10, 1), (10, 1)])))

    def test_no_more_than_the_requirement_still_needs(self):
        self.assertEqual(self.check([(10, 2)], remaining=2), [])
        problems = self.check([(10, 2), (11, 1)], remaining=2)
        self.assertIn("Select no more than 2", " ".join(problems))

    def test_shortfalls_list_only_the_items_asked_for_beyond_what_is_available(self):
        shortfalls = _reservations().shortfalls(
            [(10, 2), (11, 1)], {10: 1, 11: 2}, {10: "Shure SLX-D", 11: "Sennheiser EW-D"})

        self.assertEqual(shortfalls, [{"resource_id": 10, "name": "Shure SLX-D",
                                       "requested_quantity": 2, "available_quantity": 1}])

    def test_the_shortfall_message_shows_the_available_quantity(self):
        message = _reservations().not_enough_message([
            {"resource_id": 10, "name": "Shure SLX-D", "requested_quantity": 2,
             "available_quantity": 1},
            {"resource_id": 11, "name": "Sennheiser EW-D", "requested_quantity": 3,
             "available_quantity": 0}])

        self.assertEqual(message,
                         "Only 1 × Shure SLX-D is available for this event's period, not 2. "
                         "None of Sennheiser EW-D is available for this event's period. "
                         "Nothing was reserved.")

    def test_items_are_named_with_their_quantities(self):
        describe = _reservations().describe_items
        self.assertEqual(describe([("Shure SLX-D", 2)]), "2 × Shure SLX-D")
        self.assertEqual(describe([("Shure SLX-D", 2), ("Sennheiser EW-D", 1)]),
                         "2 × Shure SLX-D and 1 × Sennheiser EW-D")
        self.assertEqual(describe([("A", 1), ("B", 2), ("C", 3)]), "1 × A, 2 × B and 3 × C")


if __name__ == "__main__":
    unittest.main()
