"""Cache TTL per /meetup/* surface (cache.py, keyed on the validated
params)."""
from datetime import timedelta

# events/search: RSVP counts move through the day and new events are posted
# all the time; the list starts at "now"
EVENT_LIST_CACHE = timedelta(minutes=30)
# events/details: the going count and the attendees shown change with every RSVP
EVENT_CACHE = timedelta(minutes=30)
# events/similar: the site's own recommendation, recomputed as events fill up
SIMILAR_CACHE = timedelta(hours=2)
# groups/search: member counts and ratings move slowly
GROUP_LIST_CACHE = timedelta(hours=6)
# groups/details: carries the next events and the member count
GROUP_CACHE = timedelta(hours=2)
# groups/events: an organizer adds or cancels an event at any time; the
# past list only grows
GROUP_EVENTS_CACHE = timedelta(minutes=30)
# topics/list, topics/details: the topic directory changes over months
TOPICS_CACHE = timedelta(hours=24)
# the whole group list of a topic (one upstream call, sliced per page): new
# groups join a topic daily
TOPIC_GROUPS_CACHE = timedelta(hours=12)
# topics/suggestions: follows the topic directory
SUGGESTIONS_CACHE = timedelta(hours=24)
# locations/suggestions and the place a search's `location` resolves to:
# the site's place index does not move
LOCATION_CACHE = timedelta(days=7)
