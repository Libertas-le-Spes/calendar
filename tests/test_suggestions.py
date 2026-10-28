import unittest

from omarchy_calendar_sync import contract, suggestions


def event(*attendees):
    return {"id": "e", "attendees": list(attendees)}


class TestGuestSuggestions(unittest.TestCase):
    def test_the_most_frequent_guests_come_first(self):
        events = [
            event({"email": "ana@example.com"}, {"email": "bo@example.com"}),
            event({"email": "bo@example.com", "displayName": "Bo Lee"}),
        ]
        self.assertEqual(
            suggestions.guest_suggestions(events, exclude=[]),
            [{"email": "bo@example.com", "name": "Bo Lee"}, {"email": "ana@example.com", "name": ""}],
        )

    def test_you_rooms_and_excluded_addresses_are_left_out(self):
        events = [event(
            {"email": "me@example.com", "self": True},
            {"email": "room-2@resource.calendar.google.com", "resource": True},
            {"email": "team@example.com"},
            {"email": "ana@example.com"},
        )]
        self.assertEqual(
            [s["email"] for s in suggestions.guest_suggestions(events, exclude=["team@example.com"])],
            ["ana@example.com"],
        )

    def test_addresses_are_matched_without_case(self):
        events = [event({"email": "Ana@Example.com"}), event({"email": "ana@example.com"})]
        self.assertEqual(
            suggestions.guest_suggestions(events, exclude=[]),
            [{"email": "ana@example.com", "name": ""}],
        )

    def test_the_list_is_capped(self):
        events = [event({"email": f"p{i}@example.com"}) for i in range(10)]
        self.assertEqual(len(suggestions.guest_suggestions(events, exclude=[], limit=3)), 3)

    def test_events_without_attendees_are_fine(self):
        self.assertEqual(suggestions.guest_suggestions([{"id": "e"}], exclude=[]), [])


if __name__ == "__main__":
    unittest.main()


class TestLengths(unittest.TestCase):
    def attendee_event(self, email, name):
        return {"attendees": [{"email": email, "displayName": name}]}

    def test_a_name_over_its_limit_is_cut(self):
        limit = contract.SUGGESTION_LENGTHS["name"]
        found = suggestions.guest_suggestions([self.attendee_event("made-up@example.invalid", "x" * (limit + 10))], [])
        self.assertEqual(len(found[0]["name"]), limit)

    def test_an_address_too_long_to_be_real_is_left_out(self):
        email = "x" * contract.SUGGESTION_LENGTHS["email"] + "@example.invalid"
        self.assertEqual(suggestions.guest_suggestions([self.attendee_event(email, "")], []), [])


class TestSuggestionCeilings(unittest.TestCase):
    def document(self, suggestion_list):
        return contract.build_document([], "2026-10-21T08:00:00+00:00", "made-up/1", None, suggestion_list)

    def test_a_suggestion_with_a_name_over_its_limit_is_a_problem(self):
        name = "x" * (contract.SUGGESTION_LENGTHS["name"] + 1)
        self.assertEqual(len(contract.validate(self.document([{"email": "a@example.invalid", "name": name}]))), 1)

    def test_more_suggestions_than_the_ceiling_are_a_problem(self):
        many = [{"email": "a@example.invalid"}] * (contract.MAX_GUEST_SUGGESTIONS + 1)
        self.assertEqual(len(contract.validate(self.document(many))), 1)
