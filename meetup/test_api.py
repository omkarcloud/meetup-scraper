"""Offline tests for the endpoint functions: the variables a search sends,
paging, and what an endpoint does with the site's answers. The fetch layer
and the cache are stand-ins."""
import json
from pathlib import Path

import pytest

from cache import DontCache
from meetup import api, fetch

FIXTURES = Path(__file__).parent / "fixtures"


def data(name):
    return json.loads((FIXTURES / name).read_text())["data"]


def page(name):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    def call(namespace, params, fn, ttl, **kw):
        result = fn(**params)
        return result.data if isinstance(result, DontCache) else result     # as cache.cached_call hands it back
    monkeypatch.setattr(api, "cached_call", call)


@pytest.fixture
def calls(monkeypatch):
    seen = {}

    def stub(name, answer):
        def call(*args, **kwargs):
            seen.setdefault(name, []).append((args, kwargs))
            if isinstance(answer, Exception):
                raise answer
            return answer(*args, **kwargs) if callable(answer) else answer
        monkeypatch.setattr(fetch, name, call)
    seen["stub"] = stub
    return seen


SEARCH = {"query": "python", "location": {"query": "New York"}, "event_type": None, "date_range": None,
          "start_date": None, "end_date": None, "distance": None, "category": None, "attendees": None,
          "sort": "RELEVANCE", "page": 1}


def test_events_search_sends_what_the_find_page_sends(calls):
    calls["stub"]("fetch_locations", data("locations_new_york.json"))
    calls["stub"]("fetch_event_search", data("events_search_python.json"))
    answer = api.events_search(**SEARCH)
    (variables, referer), _ = calls["fetch_event_search"][0]
    assert referer == "https://www.meetup.com/find/?keywords=python&location=us--ny--New%20York&source=EVENTS"
    start = variables.pop("startDateRange")
    assert start.endswith(("-05:00", "-04:00")) and variables.pop("seriesStartDate") == start[:10]
    assert variables == {"first": 50, "lat": 40.75, "lon": -73.98999786376953, "numberOfEventsForSeries": 5,
                         "query": "python", "city": "New York", "state": "NY", "country": "us", "zip": "10001",
                         "sortField": "RELEVANCE", "doConsolidateEvents": True,
                         "dataConfiguration": '{"isSimplifiedSearchEnabled": true, "include_events_from_user_chapters": true}'}
    assert answer["location"] == {"name": "New York, NY, USA", "city": "New York", "state": "NY", "country": "US",
                                  "lat": 40.75, "lng": -73.99, "timezone": "US/Eastern"}
    assert answer["query"] == "python" and answer["sort"] == "relevance" and len(answer["events"]) == 12
    assert answer["pagination"] == {"page": 1, "items_per_page": 50, "total_pages": None, "total_count": None,
                                    "has_next": True}


def test_events_search_filters_and_paging(calls):
    calls["stub"]("fetch_locations", data("locations_new_york.json"))
    calls["stub"]("fetch_event_browse", data("events_browse_no_results.json"))
    answer = api.events_search(**{**SEARCH, "query": None, "event_type": "ONLINE", "date_range": "tomorrow",
                                  "distance": 10, "category": "546", "attendees": {"min": 100}, "sort": "DATETIME",
                                  "page": 3})
    (variables, referer), _ = calls["fetch_event_browse"][0]
    assert referer == "https://www.meetup.com/find/?location=us--ny--New%20York&source=EVENTS"
    assert variables["after"] == "MTAw"                                 # base64("100"): page 3 of 50
    assert variables["eventType"] == "ONLINE" and variables["radius"] == 10 and variables["topicCategoryId"] == "546"
    assert variables["rsvpCountRange"] == {"min": 100} and variables["sortField"] == "DATETIME"
    assert variables["startDateRange"][10:] in ("T00:00:00-05:00", "T00:00:00-04:00")
    assert variables["endDateRange"][10:] in ("T23:59:59-05:00", "T23:59:59-04:00")
    assert variables["doPromotePaypalEvents"] is False and "query" not in variables and "city" not in variables
    assert variables["indexAlias"] == fetch.EVENTS_INDEX_ALIAS and "isStartingSoon" not in variables
    assert answer["events"] == [] and answer["pagination"]["has_next"] is False and answer["pagination"]["page"] == 3
    assert answer["sort"] == "date" and answer["to_time"] == variables["endDateRange"]


def test_search_by_point_looks_the_zone_up_only_for_a_day_filter(calls):
    calls["stub"]("fetch_locations", data("locations_by_point_london.json"))
    calls["stub"]("fetch_event_browse", data("events_browse_no_results.json"))
    point = {**SEARCH, "query": None, "location": {"lat": 51.5072, "lng": -0.1276}}
    answer = api.events_search(**point)
    assert "fetch_locations" not in calls and answer["location"]["lat"] == 51.5072 and answer["location"]["name"] is None
    assert calls["fetch_event_browse"][0][0][0]["startDateRange"].endswith("+00:00")
    api.events_search(**{**point, "date_range": "starting_soon"})
    assert calls["fetch_locations"][0][1] == {"lat": 51.5072, "lng": -0.1276}
    assert calls["fetch_event_browse"][1][0][0]["isStartingSoon"] is True


def test_unknown_place_is_not_found(calls):
    calls["stub"]("fetch_locations", data("locations_none.json"))
    with pytest.raises(fetch.MeetupNotFound, match="no place found for 'zzqxjvkwpl'"):
        api.events_search(**{**SEARCH, "location": {"query": "zzqxjvkwpl"}})


def test_groups_search(calls):
    calls["stub"]("fetch_locations", data("locations_london.json"))
    calls["stub"]("fetch_group_search", data("groups_search_python.json"))
    calls["stub"]("fetch_group_browse", data("groups_browse_london.json"))
    answer = api.groups_search(query="yoga", location={"query": "london"}, distance=5, category="511", page=2)
    (variables, referer), _ = calls["fetch_group_search"][0]
    assert variables == {"first": 50, "lat": 51.52000045776367, "lon": -0.10000000149011612, "topicCategoryId": "511",
                         "radius": 5, "query": "yoga", "city": "London", "state": "17", "country": "gb",
                         "zip": "EC1A 4DD", "dataConfiguration": '{ "isSimplifiedGroupSearchEnabled": true }',
                         "after": "NTA="}
    assert referer == "https://www.meetup.com/find/?keywords=yoga&location=gb--17--London&source=GROUPS"
    assert len(answer["groups"]) == 15 and answer["pagination"]["has_next"] is True
    api.groups_search(query=None, location={"query": "london"}, distance=None, category=None, page=1)
    (variables, _), _ = calls["fetch_group_browse"][0]
    assert variables == {"first": 50, "lat": 51.52000045776367, "lon": -0.10000000149011612,
                         "indexAlias": "popular_groups_nearby_current"}


def test_event_details_asks_for_the_attendees_the_page_loads(calls, monkeypatch):
    link = "https://www.meetup.com/pymc-labs-online-meetup/events/317300966/"
    calls["stub"]("fetch_event_page", (link, page("event_online.next_data.json")))
    calls["stub"]("fetch_event_extras", fetch.MeetupUpstreamError("down"))      # an addition: it may fail
    calls["stub"]("fetch_event_attendees", data("event_attendees_online.json"))
    event = api.events_details(event="317300966")
    assert calls["fetch_event_attendees"][0][0] == ("317300966", link)
    assert len(event["attendees"]) == 6 and event["how_to_find_us"] is None and event["id"] == "317300966"
    monkeypatch.setattr(api.config, "MEETUP_ALL_LOADED_ATTENDEES", True)
    assert len(api.events_details(event="317300966")["attendees"]) == 19


def test_ended_event_is_answered_from_its_public_part(calls, monkeypatch):
    calls["stub"]("fetch_event_page", ("https://www.meetup.com/nycpython/events/311095399/", page("event_past.next_data.json")))
    event = api.events_details(event="311095399")
    assert "fetch_event_attendees" not in calls and "fetch_event_extras" not in calls
    assert event["status"] == "past" and event["hosts"] == [] and event["attendees"] == [] and event["title"]
    monkeypatch.setattr(api.config, "MEETUP_ENDED_EVENT_PAGES", True)
    assert api.events_details(event="311095399")["hosts"]


def test_event_details_cache_keeps_only_whole_answers_and_follows_the_switches(calls, monkeypatch):
    kept = {}

    def keeping(namespace, params, fn, ttl, **kw):          # cache.cached_call, on a dict
        key = (namespace, json.dumps(params, sort_keys=True))
        if key not in kept:
            result = fn(**params)
            if isinstance(result, DontCache):
                return result.data
            kept[key] = result
        return kept[key]
    monkeypatch.setattr(api, "cached_call", keeping)
    link = "https://www.meetup.com/pymc-labs-online-meetup/events/317300966/"
    calls["stub"]("fetch_event_page", (link, page("event_online.next_data.json")))
    calls["stub"]("fetch_event_extras", {"event": {}})
    calls["stub"]("fetch_event_attendees", fetch.MeetupBlocked("403"))
    assert api.events_details(event="317300966")["attendees"] == [] and not kept     # served without them, not kept
    calls["stub"]("fetch_event_attendees", data("event_attendees_online.json"))
    assert len(api.events_details(event="317300966")["attendees"]) == 6 and len(kept) == 1
    # a row made under one setting of a switch is not served under the other
    monkeypatch.setattr(api.config, "MEETUP_ALL_LOADED_ATTENDEES", True)
    assert len(api.events_details(event="317300966")["attendees"]) == 19
    calls["stub"]("fetch_event_page", ("https://www.meetup.com/nycpython/events/311095399/", page("event_past.next_data.json")))
    assert api.events_details(event="311095399")["hosts"] == []
    monkeypatch.setattr(api.config, "MEETUP_ENDED_EVENT_PAGES", True)
    assert api.events_details(event="311095399")["hosts"]


def test_event_page_without_an_event_is_an_upstream_error(calls):
    calls["stub"]("fetch_event_page", ("https://www.meetup.com/x/", {"props": {"pageProps": {}}}))
    with pytest.raises(fetch.MeetupUpstreamError):
        api.events_details(event="317300966")


def test_similar_events(calls):
    calls["stub"]("fetch_similar_events", data("events_similar.json"))
    answer = api.events_similar(event="317383946", limit=2)
    assert answer["event_id"] == "317383946" and len(answer["events"]) == 2
    calls["stub"]("fetch_similar_events", data("events_similar_none.json"))
    calls["stub"]("fetch_event_extras", data("event_extras_not_found.json"))
    with pytest.raises(fetch.MeetupNotFound):
        api.events_similar(event="999999999", limit=10)
    calls["stub"]("fetch_event_extras", data("event_extras_physical.json"))
    assert api.events_similar(event="317383946", limit=10)["events"] == []      # a real event with none


def test_group_details_and_events(calls):
    calls["stub"]("fetch_group", data("group_nycpython.json"))
    calls["stub"]("fetch_group_rating", fetch.MeetupBlocked("403"))
    group = api.groups_details(group="nycpython")
    assert isinstance(group, DontCache)         # the rating call failed: served, not kept (the route's cache unwraps it)
    group = group.data
    assert group["website"] == "http://nycpython.org" and group["rating"]["average"] == 4.66
    assert group["rating"]["breakdown"] == []
    calls["stub"]("fetch_group_rating", data("group_rating_nycpython.json"))
    assert api.groups_details(group="nycpython")["rating"]["breakdown"][0] == {"stars": 5, "count": 2216}
    calls["stub"]("fetch_group", fetch.MeetupNotFound("group zz not found"))
    with pytest.raises(fetch.MeetupNotFound):
        api.groups_details(group="zz")
    calls["stub"]("fetch_group_events", data("group_events_past.json"))
    answer = api.groups_events(group="nycpython", status="past", title=None, from_date="2019-01-01", to_date=None,
                               cursor=None)
    (args, kwargs) = calls["fetch_group_events"][0]
    assert args == ("nycpython", "past") and kwargs["after_time"] == "2019-01-01T00:00:00.000Z"
    assert kwargs["before_time"].endswith("Z") and kwargs["before_time"] > "2026-11-21"
    assert answer["total_count"] == 953 and answer["next_cursor"] and answer["group"]["link"].endswith("/nycpython/")
    api.groups_events(group="nycpython", status="upcoming", title="talk", from_date=None, to_date="2099-01-01", cursor="abc")
    (args, kwargs) = calls["fetch_group_events"][1]
    assert kwargs["before_time"] == "2099-01-01T23:59:59.000Z" and kwargs["after"] == "abc" and kwargs["title"] == "talk"
    assert kwargs["after_time"] > "2026-11-21"


def test_topics(calls):
    calls["stub"]("fetch_topics_page", page("topics_page.next_data.json"))
    assert api.topics_list()["category_count"] == 20
    calls["stub"]("fetch_topic_page", page("topic_python.next_data.json"))
    calls["stub"]("fetch_topic_stats", {"topicByUrlkey": {"id": "1064", "stats": {"groupCount": 1526, "memberCount": 2215941}}})
    assert api.topics_details(topic="python")["id"] == "1064"
    calls["stub"]("fetch_topic_page", None)
    calls["stub"]("fetch_topic_stats", data("topic_stats_unknown.json"))
    calls["stub"]("fetch_topic_groups", fetch.MeetupNotFound("topic zz not found"))
    with pytest.raises(fetch.MeetupNotFound):
        api.topics_details(topic="zz")
    calls["stub"]("fetch_topic_groups", data("topic_groups_python.json"))
    with pytest.raises(fetch.MeetupUpstreamError):                               # the topic exists; its page failed
        api.topics_details(topic="python")
    answer = api.topics_groups(topic="python", page=1)
    assert calls["fetch_topic_groups"][-1][0] == ("python", 10000)
    assert answer["topic"] == {"id": "1064", "key": "python", "link": "https://www.meetup.com/topics/python/"}
    assert len(answer["groups"]) == 22
    assert answer["pagination"] == {"page": 1, "items_per_page": 200, "total_pages": 1, "total_count": 22}
    assert api.topics_groups(topic="python", page=2)["groups"] == []
    calls["stub"]("fetch_topic_suggestions", data("topics_suggestions_python.json"))
    assert len(api.topics_suggestions(query="python")["topics"]) == 5


def test_topic_counts_come_from_the_stats_call(calls, monkeypatch):
    calls["stub"]("fetch_topic_page", page("topic_hiking.next_data.json"))      # the page's own counts are 0
    calls["stub"]("fetch_topic_stats", data("topic_stats_hiking.json"))
    topic = api.topics_details(topic="hiking")
    assert calls["fetch_topic_stats"][0][0] == ("hiking",)
    assert topic["group_count"] == 1937 and topic["member_count"] == 4442971 and len(topic["largest_groups"]) == 10
    # the call failed: the topic is served with no counts (not the page's 0) and is not kept
    monkeypatch.setattr(api, "cached_call", lambda namespace, params, fn, ttl, **kw: fn(**params))
    calls["stub"]("fetch_topic_stats", fetch.MeetupBlocked("403"))
    answer = api.topics_details(topic="hiking")
    assert isinstance(answer, DontCache)
    assert answer.data["group_count"] is None and answer.data["member_count"] is None and answer.data["name"] == "Hiking"
    calls["stub"]("fetch_topic_stats", fetch.MeetupSchemaChanged("the site rejected getTopicStats"))
    assert isinstance(api.topics_details(topic="hiking"), DontCache)


def test_locations(calls):
    calls["stub"]("fetch_locations", data("locations_london.json"))
    answer = api.locations_suggestions(query="london")
    assert answer["query"] == "london" and len(answer["locations"]) == 5 and answer["locations"][0]["country"] == "GB"


def test_offset_cursor():
    assert api._offset_cursor(1, 50) is None and api._offset_cursor(2, 50) == "NTA=" and api._offset_cursor(2, 12) == "MTI="
