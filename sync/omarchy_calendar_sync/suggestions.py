"""Guest suggestions for the event form: people you already have events with.

Built from the events the sync fetches anyway, so it needs no contacts scope
and no extra call. The most frequent guests come first.
"""

from collections import Counter

from .contract import MAX_GUEST_SUGGESTIONS, SUGGESTION_LENGTHS
from .plaintext import clipped

def guest_suggestions(gevents, exclude, limit=MAX_GUEST_SUGGESTIONS):
    """[{"email", "name"}] from the attendees of `gevents`, most frequent first.

    Leaves out you (the attendee marked self), rooms, and the addresses in
    `exclude` (your own calendars).
    """
    skip = {str(address).lower() for address in exclude}
    counts = Counter()
    names = {}
    for gevent in gevents:
        for attendee in gevent.get("attendees") or []:
            email = str(attendee.get("email") or "").strip().lower()
            if not email or email in skip or attendee.get("self") or attendee.get("resource"):
                continue
            if len(email) > SUGGESTION_LENGTHS["email"]:
                continue
            counts[email] += 1
            if attendee.get("displayName") and email not in names:
                names[email] = clipped(str(attendee["displayName"]), SUGGESTION_LENGTHS["name"])
    # Ties keep a stable order, so the list does not reshuffle every sync.
    ranked = sorted(counts, key=lambda email: (-counts[email], email))
    return [{"email": email, "name": names.get(email, "")} for email in ranked[:limit]]
