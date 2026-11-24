"""Offline tests for the /meetup/* request schemas."""
import pytest

from schema_fields import load_query
from meetup import schemas


def ok(schema, **query):
    loaded, error = load_query(schema, query)
    assert error is None, error
    return loaded


def bad(schema, field, **query):
    loaded, error = load_query(schema, query)
    assert loaded is None and field in error["errors"], error
    return error["errors"][field][0]


def test_events_search_defaults_and_tokens():
    loaded = ok(schemas.EventsSearchSchema, location="New York")
    assert loaded == {"query": None, "location": {"query": "New York"}, "event_type": None, "date_range": None,
                      "start_date": None, "end_date": None, "distance": None, "category": None, "attendees": None,
                      "sort": "RELEVANCE", "page": 1}
    loaded = ok(schemas.EventsSearchSchema, location="40.75,-73.99", query=" python ", event_type="In_Person",
                date_range="this_weekend", distance="25", category="technology", attendees="over-100", sort="date",
                page="3")
    assert loaded["location"] == {"lat": 40.75, "lng": -73.99} and loaded["query"] == "python"
    assert loaded["event_type"] == "PHYSICAL" and loaded["distance"] == 25 and loaded["category"] == "546"
    assert loaded["attendees"] == {"min": 100} and loaded["sort"] == "DATETIME" and loaded["page"] == 3
    assert ok(schemas.EventsSearchSchema, location="NY", attendees="10-20")["attendees"] == {"min": 10, "max": 20}
    assert ok(schemas.EventsSearchSchema, location="NY", sort="")["sort"] == "RELEVANCE"
    assert ok(schemas.EventsSearchSchema, location="NY", query="x", event_type="hybrid")["event_type"] == "HYBRID"
    assert ok(schemas.EventsSearchSchema, location="NY", start_date="2026-12-01", end_date="2026-12-01")["end_date"] == "2026-12-01"


def test_events_search_rejects():
    assert "required" in bad(schemas.EventsSearchSchema, "location", query="python")
    assert "Must be one of" in bad(schemas.EventsSearchSchema, "sort", location="NY", sort="price")
    assert "Must be one of" in bad(schemas.EventsSearchSchema, "event_type", location="NY", event_type="outdoor")
    assert "Must be one of" in bad(schemas.EventsSearchSchema, "distance", location="NY", distance="3")
    assert "Must be one of" in bad(schemas.EventsSearchSchema, "category", location="NY", category="546")
    assert "Must be one of" in bad(schemas.EventsSearchSchema, "attendees", location="NY", attendees="100")
    assert "Must be one of" in bad(schemas.EventsSearchSchema, "date_range", location="NY", date_range="yesterday")
    assert "hybrid needs a query" in bad(schemas.EventsSearchSchema, "event_type", location="NY", event_type="hybrid")
    assert "not both" in bad(schemas.EventsSearchSchema, "date_range", location="NY", date_range="today", end_date="2026-12-01")
    assert "before start_date" in bad(schemas.EventsSearchSchema, "end_date", location="NY", start_date="2026-12-02",
                                      end_date="2026-12-01")
    assert "YYYY-MM-DD" in bad(schemas.EventsSearchSchema, "start_date", location="NY", start_date="12/01/2026")
    assert "Latitude" in bad(schemas.EventsSearchSchema, "location", location="95,10")
    bad(schemas.EventsSearchSchema, "page", location="NY", page="0")
    bad(schemas.EventsSearchSchema, "page", location="NY", page="101")
    bad(schemas.EventsSearchSchema, "limit", location="NY", limit="10")         # an unknown param is refused


def test_event_and_similar():
    assert ok(schemas.EventsDetailsSchema, event="317383946") == {"event": "317383946"}
    assert ok(schemas.EventsDetailsSchema, event="https://www.meetup.com/nycpython/events/317383946/")["event"] == "317383946"
    assert "event id" in bad(schemas.EventsDetailsSchema, "event", event="https://www.meetup.com/nycpython/")
    assert "required" in bad(schemas.EventsDetailsSchema, "event")
    assert ok(schemas.EventsSimilarSchema, event="317383946") == {"event": "317383946", "limit": 10}
    assert ok(schemas.EventsSimilarSchema, event="317383946", limit="3")["limit"] == 3
    bad(schemas.EventsSimilarSchema, "limit", event="317383946", limit="11")


def test_groups():
    loaded = ok(schemas.GroupsSearchSchema, location="London gb", query="yoga", category="health-wellbeing", distance="5")
    assert loaded == {"query": "yoga", "location": {"query": "London gb"}, "distance": 5, "category": "511", "page": 1}
    assert "required" in bad(schemas.GroupsSearchSchema, "location")
    bad(schemas.GroupsSearchSchema, "sort", location="NY", sort="date")         # groups have no sort
    assert ok(schemas.GroupsDetailsSchema, group="https://www.meetup.com/nycpython/") == {"group": "nycpython"}
    assert "url name" in bad(schemas.GroupsDetailsSchema, "group", group="https://www.meetup.com/find/")
    loaded = ok(schemas.GroupsEventsSchema, group="nycpython")
    assert loaded == {"group": "nycpython", "status": "upcoming", "title": None, "from_date": None, "to_date": None,
                      "cursor": None}
    loaded = ok(schemas.GroupsEventsSchema, group="nycpython", status="PAST", title="pydata", from_date="2019-01-01",
                to_date="2019-12-31", cursor="Mjk2MjYzMTIwOjE2OTcwNjM0MDAwMDA=")
    assert loaded["status"] == "past" and loaded["cursor"] == "Mjk2MjYzMTIwOjE2OTcwNjM0MDAwMDA="
    assert "next_cursor" in bad(schemas.GroupsEventsSchema, "cursor", group="nycpython", cursor="not a cursor")
    assert "Must be one of" in bad(schemas.GroupsEventsSchema, "status", group="nycpython", status="cancelled")
    assert "before from_date" in bad(schemas.GroupsEventsSchema, "to_date", group="nycpython", from_date="2026-02-01",
                                     to_date="2026-01-01")


def test_topics_and_locations():
    assert ok(schemas.TopicsListSchema) == {}
    bad(schemas.TopicsListSchema, "page", page="2")
    assert ok(schemas.TopicsDetailsSchema, topic="https://www.meetup.com/topics/Python/") == {"topic": "python"}
    assert "url key" in bad(schemas.TopicsDetailsSchema, "topic", topic="https://www.meetup.com/nycpython/")
    assert ok(schemas.TopicsGroupsSchema, topic="python", page="2") == {"topic": "python", "page": 2}
    bad(schemas.TopicsGroupsSchema, "page", topic="python", page="51")
    assert ok(schemas.TopicsSuggestionsSchema, query="pyth") == {"query": "pyth"}
    assert "required" in bad(schemas.TopicsSuggestionsSchema, "query")
    assert ok(schemas.LocationsSuggestionsSchema, query="lond") == {"query": "lond"}
    bad(schemas.LocationsSuggestionsSchema, "query", query="x" * 101)


VALID = {"location": "New York", "event": "317383946", "group": "nycpython", "topic": "python", "query": "pyth"}
ROUTE_SCHEMAS = [schemas.EventsSearchSchema, schemas.EventsDetailsSchema, schemas.EventsSimilarSchema,
                 schemas.GroupsSearchSchema, schemas.GroupsDetailsSchema, schemas.GroupsEventsSchema,
                 schemas.TopicsListSchema, schemas.TopicsDetailsSchema, schemas.TopicsGroupsSchema,
                 schemas.TopicsSuggestionsSchema, schemas.LocationsSuggestionsSchema]


@pytest.mark.parametrize("schema", ROUTE_SCHEMAS, ids=lambda c: c.__name__)
def test_an_empty_optional_param_is_the_absent_param(schema):
    """A form or an automation sends every field, the unset ones empty
    (`page=`, `start_date=`, `limit=`, `cursor=`)."""
    fields = {field.data_key or name: field for name, field in schema().fields.items()}
    base = {key: VALID[key] for key, field in fields.items() if field.required}
    expected = ok(schema, **base)
    for key, field in fields.items():
        loaded, error = load_query(schema, dict(base, **{key: ""}))
        if field.required:
            assert loaded is None and key in error["errors"]
        else:
            assert error is None and loaded == expected, key
    assert load_query(schema, dict(base, **{key: "  " for key in fields if key not in base})) == (expected, None)


@pytest.mark.parametrize("schema", [getattr(schemas, name) for name in dir(schemas) if name.endswith("Schema")
                                    and name != "BaseSchema"])
def test_every_field_is_described(schema):
    for name, field in schema().fields.items():
        assert field.metadata.get("description"), f"{schema.__name__}.{name}"
