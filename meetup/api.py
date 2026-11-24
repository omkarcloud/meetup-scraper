"""The /meetup/* endpoint functions (route_glue's route_table calls them
with the schema's loaded kwargs).

Caching (cache.cached_call) sits here, on the upstream pieces as well as
on the answers:

  meetup.place          the place a search's `location` text resolves to
                        (the site's own place search, first answer); both
                        searches and every page of them share it
  meetup.topic_groups   a topic's whole group list (one upstream batch):
                        every page of topics/groups is a slice of it

groups/details is not cached here: its route caches it (routes.py, the
website-contacts wrapper).

Paging: the two searches take `page`. The site pages them by a cursor that
is the row offset, so the cursor is built from the page number
(_offset_cursor). The site publishes no total for them: `has_next` says
whether a next page exists, and a page past the end is empty. A group's
event list is paged by a cursor only the site can make, so groups/events
takes `cursor` (the `next_cursor` of the page before).
"""
import base64

import config
from cache import DontCache, cached_call
from meetup import cache_config as ttl
from meetup import parsers, refs, timeframes
from meetup import fetch
from meetup.fetch import MeetupNotFound, MeetupUpstreamError
from meetup.schemas import EVENTS_PER_PAGE, GROUPS_PER_PAGE, TOPIC_GROUPS_PER_PAGE
from scraper_errors import UpstreamError
from scraper_utils import fanout

TOPIC_GROUPS_BATCH = 10000      # the most the site answers in one call; 10,001 answers "no such topic" (2026-11-23)

_EVENT_SORT_NAMES = {token: name for name, token in refs.EVENT_SORTS.items()}
_PLACE_KEYS = ("name", "city", "state", "country", "lat", "lng", "timezone")


# ---- the place of a search -----------------------------------------------------------

def _fetch_place(query):
    place = parsers.first_place(fetch.fetch_locations(query=query))
    if place is None:
        raise MeetupNotFound(f"no place found for '{query}': try a city with its country code (London gb), "
                             "a US zip code, or lat,lng")
    return place


def _fetch_place_at(lat, lng):
    return parsers.first_place(fetch.fetch_locations(lat=lat, lng=lng)) or {}


def _place(location, need_zone):
    """The schema's `location` -> (the site's place record or {}, lat, lon).
    A point is used as given; its time zone is looked up only when a day
    filter needs the place's clock."""
    if "query" in location:
        place = cached_call("meetup.place", {"query": location["query"].lower()}, _fetch_place, ttl.LOCATION_CACHE)
        return place, place["lat"], place["lon"]
    place = {}
    if need_zone:
        nearest = cached_call("meetup.place_at", {"lat": location["lat"], "lng": location["lng"]}, _fetch_place_at,
                              ttl.LOCATION_CACHE)
        place = {"timeZone": nearest.get("timeZone")}
    return place, location["lat"], location["lng"]


def _place_fields(place):
    """The city / state / country / zip a keyword search sends with its point."""
    return {key: place[key] for key in ("city", "state", "country", "zip") if place.get(key)}


def _place_token(place):
    """us--ny--New York: how the find page writes a place in its address."""
    if not place.get("city") or not place.get("country"):
        return None
    parts = [place["country"], str(place["state"]).lower()] if place.get("state") else [place["country"]]
    return "--".join([*parts, place["city"]])


def _place_answer(place, lat, lng):
    if place.get("name"):
        parsed = parsers.parse_locations({"result": [place]})[0]
        return {key: parsed.get(key) for key in _PLACE_KEYS}
    return {**dict.fromkeys(_PLACE_KEYS), "lat": lat, "lng": lng, "timezone": place.get("timeZone")}


def _offset_cursor(page, per_page):
    """The site's cursor for a page of a search: the row offset, base64."""
    if page <= 1:
        return None
    return base64.b64encode(str((page - 1) * per_page).encode()).decode()


def _has_next_block(page, per_page, has_next):
    return {"page": page, "items_per_page": per_page, "total_pages": None, "total_count": None, "has_next": has_next}


# ---- events --------------------------------------------------------------------------

def _events_search(**data):
    page, query = data["page"], data.get("query")
    dated = bool(data.get("date_range") or data.get("start_date") or data.get("end_date"))
    place, lat, lon = _place(data["location"], need_zone=dated)
    start, end, soon = timeframes.window(data.get("date_range"), data.get("start_date"), data.get("end_date"),
                                         place.get("timeZone"))
    variables = {"first": EVENTS_PER_PAGE, "lat": lat, "lon": lon}
    if data.get("category"):
        variables["topicCategoryId"] = data["category"]
    if data.get("distance"):
        variables["radius"] = data["distance"]
    variables["startDateRange"] = start
    if end:
        variables["endDateRange"] = end
    if soon:
        variables["isStartingSoon"] = True
    if data.get("event_type"):
        variables["eventType"] = data["event_type"]
    variables["numberOfEventsForSeries"] = fetch.SERIES_EVENTS
    variables["seriesStartDate"] = timeframes.window(zone_name=place.get("timeZone"))[0][:10]
    if data.get("attendees"):
        variables["rsvpCountRange"] = data["attendees"]
    referer = refs.find_link("EVENTS", query, _place_token(place))
    if query:
        variables.update({"query": query, **_place_fields(place), "sortField": data["sort"],
                          "doConsolidateEvents": True, "dataConfiguration": fetch.EVENTS_DATA_CONFIGURATION})
    else:
        variables.update({"sortField": data["sort"], "doConsolidateEvents": True, "doPromotePaypalEvents": False,
                          "indexAlias": fetch.EVENTS_INDEX_ALIAS,
                          "dataConfiguration": fetch.EVENTS_DATA_CONFIGURATION})
    cursor = _offset_cursor(page, EVENTS_PER_PAGE)
    if cursor:
        variables["after"] = cursor
    raw = fetch.fetch_event_search(variables, referer) if query else fetch.fetch_event_browse(variables, referer)
    listing = parsers.parse_event_list(raw)
    return {
        "query": query,
        "location": _place_answer(place, lat, lon),
        "sort": _EVENT_SORT_NAMES.get(data["sort"], data["sort"]),
        "from_time": start,
        "to_time": end,
        "events": listing["events"],
        "pagination": _has_next_block(page, EVENTS_PER_PAGE, listing["has_next"]),
    }


def events_search(**data):
    return cached_call("meetup.events_search", data, _events_search, ttl.EVENT_LIST_CACHE)


def _optional(fn, what):
    """An addition to an answer: a failure leaves it out rather than
    failing the answer."""
    def run():
        try:
            return fn()
        except UpstreamError as e:
            print(f"meetup: {what} skipped: {type(e).__name__}: {e}")
            return None
    return run


def _event_details(event, all_loaded_attendees, ended_event_pages):
    link, next_data = fetch.fetch_event_page(event)
    if parsers.page_event(next_data) is None:
        raise MeetupUpstreamError(f"event {event}: the page carries no event")
    if parsers.is_ended(next_data):
        parsed = parsers.parse_event(next_data)
        return parsed if ended_event_pages else parsers.public_part_of_ended(parsed)
    extras, attendees = fanout.per_call([
        _optional(lambda: fetch.fetch_event_extras(event, link), f"the page's second call for event {event}"),
        _optional(lambda: fetch.fetch_event_attendees(event, link), f"the attendees of event {event}"),
    ], 2)
    parsed = parsers.parse_event(next_data, extras, attendees, every_loaded_attendee=all_loaded_attendees)
    # an event missing what a failed call adds is served but not kept, so the next call asks again
    return DontCache(parsed) if extras is None or attendees is None else parsed


def events_details(**data):
    # the two switches change the answer: they are part of the cache key, so a row made under one
    # setting is not served under the other
    key = {**data, "all_loaded_attendees": bool(config.MEETUP_ALL_LOADED_ATTENDEES),
           "ended_event_pages": bool(config.MEETUP_ENDED_EVENT_PAGES)}
    return cached_call("meetup.event", key, _event_details, ttl.EVENT_CACHE)


def _events_similar(event, limit):
    referer = f"{refs.SITE}/events/events/{event}/"
    events = parsers.parse_similar_events(fetch.fetch_similar_events(event, limit, referer))
    if not events and not isinstance(fetch.fetch_event_extras(event, referer).get("event"), dict):
        raise MeetupNotFound(f"event {event} not found")
    return {"event_id": event, "events": events[:limit]}


def events_similar(**data):
    return cached_call("meetup.events_similar", data, _events_similar, ttl.SIMILAR_CACHE)


# ---- groups --------------------------------------------------------------------------

def _groups_search(**data):
    page, query = data["page"], data.get("query")
    place, lat, lon = _place(data["location"], need_zone=False)
    variables = {"first": GROUPS_PER_PAGE, "lat": lat, "lon": lon}
    if data.get("category"):
        variables["topicCategoryId"] = data["category"]
    if data.get("distance"):
        variables["radius"] = data["distance"]
    referer = refs.find_link("GROUPS", query, _place_token(place))
    if query:
        variables.update({"query": query, **_place_fields(place),
                          "dataConfiguration": fetch.GROUPS_DATA_CONFIGURATION})
    else:
        variables["indexAlias"] = fetch.GROUPS_INDEX_ALIAS
    cursor = _offset_cursor(page, GROUPS_PER_PAGE)
    if cursor:
        variables["after"] = cursor
    raw = fetch.fetch_group_search(variables, referer) if query else fetch.fetch_group_browse(variables, referer)
    listing = parsers.parse_group_list(raw)
    return {
        "query": query,
        "location": _place_answer(place, lat, lon),
        "groups": listing["groups"],
        "pagination": _has_next_block(page, GROUPS_PER_PAGE, listing["has_next"]),
    }


def groups_search(**data):
    return cached_call("meetup.groups_search", data, _groups_search, ttl.GROUP_LIST_CACHE)


def groups_details(group):
    """A group, with its rating summary. Not cached here: the route's
    website-contacts wrapper caches this answer (routes.py), unless the
    rating call failed: that answer is served but not kept (DontCache)."""
    raw, rating = fanout.per_call([
        lambda: fetch.fetch_group(group),
        _optional(lambda: fetch.fetch_group_rating(group), f"the rating summary of group {group}"),
    ], 2)
    parsed = parsers.parse_group(raw, rating)
    return DontCache(parsed) if rating is None else parsed


def _groups_events(group, status, title, from_date, to_date, cursor):
    now = timeframes.now_utc()
    after_time = timeframes.day_bound(from_date, None) if from_date else None
    before_time = timeframes.day_bound(to_date, None, end=True) if to_date else None
    if status == "upcoming":
        after_time = max(after_time or now, now)
    else:
        before_time = min(before_time or now, now)
    raw = fetch.fetch_group_events(group, status, after=cursor, title=title, after_time=after_time,
                                   before_time=before_time)
    listing = parsers.parse_group_events(raw)
    return {
        "group": {"id": listing["group_id"], "url_name": group, "link": refs.group_link(group)},
        "status": status,
        "total_count": listing["total_count"],
        "next_cursor": listing["next_cursor"],
        "events": listing["events"],
    }


def groups_events(**data):
    return cached_call("meetup.group_events", data, _groups_events, ttl.GROUP_EVENTS_CACHE)


# ---- topics --------------------------------------------------------------------------

def _topics_list():
    categories = parsers.parse_topics_page(fetch.fetch_topics_page())
    if not categories:
        raise MeetupUpstreamError("the topics page carries no categories")
    return {"category_count": len(categories), "categories": categories}


def topics_list(**data):
    return cached_call("meetup.topics", data, _topics_list, ttl.TOPICS_CACHE)


def _topics_details(topic):
    page, stats = fanout.per_call([
        lambda: fetch.fetch_topic_page(topic),
        _optional(lambda: fetch.fetch_topic_stats(topic), f"the counts of topic {topic}"),
    ], 2)
    parsed = parsers.parse_topic_page(page or {}, stats)
    if parsed is None:
        fetch.fetch_topic_groups(topic, 1)      # MeetupNotFound for a topic the site does not have
        raise MeetupUpstreamError(f"topic {topic}: the site answered its error page")
    # a topic missing the counts of a failed call is served but not kept, so the next call asks again
    return DontCache(parsed) if stats is None else parsed


def topics_details(**data):
    # its own namespace since the counts come from `stats`: rows of the page's 0 counts are not served
    return cached_call("meetup.topic_details", data, _topics_details, ttl.TOPICS_CACHE)


def _fetch_topic_groups(topic):
    return parsers.parse_topic_groups(fetch.fetch_topic_groups(topic, TOPIC_GROUPS_BATCH))


def _topics_groups(topic, page):
    """A page of a topic's groups: a slice of the whole list, which the site
    answers in one call (asked for in pages, it repeats and skips groups)."""
    everything = cached_call("meetup.topic_groups", {"topic": topic}, _fetch_topic_groups, ttl.TOPIC_GROUPS_CACHE)
    groups = everything["groups"]
    start = (page - 1) * TOPIC_GROUPS_PER_PAGE
    return {
        "topic": {"id": everything["topic_id"], "key": topic, "link": refs.topic_link(topic)},
        "groups": groups[start:start + TOPIC_GROUPS_PER_PAGE],
        "pagination": {"page": page, "items_per_page": TOPIC_GROUPS_PER_PAGE,
                       "total_pages": -(-len(groups) // TOPIC_GROUPS_PER_PAGE), "total_count": len(groups)},
    }


def topics_groups(**data):
    return _topics_groups(**data)


def _topics_suggestions(query):
    return {"query": query, "topics": parsers.parse_topic_suggestions(fetch.fetch_topic_suggestions(query))}


def topics_suggestions(**data):
    return cached_call("meetup.topic_suggestions", data, _topics_suggestions, ttl.SUGGESTIONS_CACHE)


# ---- locations -----------------------------------------------------------------------

def _locations_suggestions(query):
    return {"query": query, "locations": parsers.parse_locations(fetch.fetch_locations(query=query))}


def locations_suggestions(**data):
    return cached_call("meetup.locations", data, _locations_suggestions, ttl.LOCATION_CACHE)
