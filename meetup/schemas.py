"""Marshmallow request schemas for every /meetup/* route.

ONE param per input (never a sibling `url` / `id` pair):

    event     an event id (317383946) OR a meetup.com event link
    group     a group's url name (nycpython) OR a meetup.com group link
    topic     a topic's url key (python) OR a meetup.com topic link
    location  a place as text (New York, 10001, London gb) OR "lat,lng"

The two searches need a `location`: the site lists what is near a place
(online events included) and would otherwise place the caller by IP
address. With `query` they search by keywords; without it they list what
the site recommends there.

A value the site would ignore is refused here: `event_type=hybrid` works
only with a `query` (the site's keyword-less list ignores it).
"""
import base64
import binascii

from marshmallow import ValidationError, pre_load, validates_schema

from schema_fields import BaseSchema as _SharedBase
from schema_fields import ChoiceField, DateField, LimitField, PageField, QueryField, RefField, StrippedString
from meetup import refs
from scraper_utils.schema import max_length as _max_length

EVENTS_PER_PAGE = 50        # the find page asks for 12; 200 is the most the site answers (201: an empty list)
GROUPS_PER_PAGE = 50
TOPIC_GROUPS_PER_PAGE = 200
MAX_PAGE = 100              # the deepest list measured ended on page 18 (885 groups); a page past the end is empty
MAX_TOPIC_GROUPS_PAGE = 50  # a topic's list is one upstream batch of at most 10,000 groups
MAX_SIMILAR = 10            # the site answers 10 similar events at most
MAX_CURSOR_LENGTH = 200


class BaseSchema(_SharedBase):
    """The base of every /meetup/* schema."""

    @pre_load
    def empty_is_absent(self, data, **kwargs):
        """An optional param sent empty (`page=`, `start_date=`, `limit=`: a
        form or an automation that sends every field) is the absent param,
        so it takes its default. A required param sent empty is still refused."""
        required = {field.data_key or name for name, field in self.fields.items() if field.required}
        return {key: value for key, value in data.items()
                if key in required or not (isinstance(value, str) and not value.strip())}


class EventRefField(RefField):
    resolver = staticmethod(refs.resolve_event)


class GroupRefField(RefField):
    resolver = staticmethod(refs.resolve_group)


class TopicRefField(RefField):
    resolver = staticmethod(refs.resolve_topic)


class LocationField(RefField):
    """'New York' -> {"query"}; '40.75,-73.99' -> {"lat", "lng"}."""
    resolver = staticmethod(refs.resolve_location)


class DefaultedChoice(ChoiceField):
    """A choice whose empty value means its default, as a missing one does
    (StrippedString hands back None for `?sort=`)."""

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None and self.load_default is not None and not callable(self.load_default):
            return self.load_default
        return value


class CursorField(StrippedString):
    """The `next_cursor` of the previous page, as the site made it (base64)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None:
            return None
        try:
            if len(value) > MAX_CURSOR_LENGTH:
                raise ValueError
            decoded = base64.b64decode(value, validate=True).decode("ascii")
        except (ValueError, binascii.Error, UnicodeDecodeError):
            decoded = ""
        if not decoded:
            raise ValidationError("Must be the next_cursor of the previous page.")
        return value


def _location_field():
    return LocationField(metadata={"description": "place to search around: a city, a US zip code or a city with its "
                                                  "country code (New York, 10001, London gb), or lat,lng (40.75,-73.99)"})


def _query_field(what):
    return QueryField(required=False, load_default=None, validate=_max_length(200),
                      metadata={"description": f"keywords; without them, the {what} the site recommends at the location"})


def _distance_field():
    return ChoiceField({str(miles): miles for miles in refs.DISTANCES},
                       metadata={"description": "search radius in miles: 2, 5, 10, 25, 50 or 100"})


def _category_field():
    return ChoiceField(dict(refs.CATEGORY_IDS),
                       metadata={"description": "one of the site's 20 categories, by key: "
                                                + ", ".join(refs.CATEGORY_IDS)})


# ---- events --------------------------------------------------------------------------

class EventsSearchSchema(BaseSchema):
    query = _query_field("events")
    location = _location_field()
    event_type = ChoiceField(dict(refs.EVENT_TYPES),
                             metadata={"description": "in_person, online or hybrid (hybrid needs a query)"})
    date_range = ChoiceField(list(refs.DATE_RANGES),
                             metadata={"description": "starting_soon, today, tomorrow, this_week, this_weekend, "
                                                      "next_week or next_weekend, on the location's clock"})
    start_date = DateField(metadata={"description": "first day of a custom range, YYYY-MM-DD (in place of date_range)"})
    end_date = DateField(metadata={"description": "last day of a custom range, YYYY-MM-DD (in place of date_range)"})
    distance = _distance_field()
    category = _category_field()
    attendees = ChoiceField(dict(refs.ATTENDEES),
                            metadata={"description": "events by number of RSVPs: " + ", ".join(refs.ATTENDEES)})
    sort = DefaultedChoice(dict(refs.EVENT_SORTS), load_default=refs.EVENT_SORTS["relevance"],
                           metadata={"description": "relevance or date (soonest first)"})
    page = PageField(max_page=MAX_PAGE, metadata={"description": f"page number, from 1 ({EVENTS_PER_PAGE} events a page)"})

    @validates_schema
    def _check(self, data, **kwargs):
        if data.get("date_range") and (data.get("start_date") or data.get("end_date")):
            raise ValidationError("Use date_range or start_date / end_date, not both.", "date_range")
        if data.get("start_date") and data.get("end_date") and data["end_date"] < data["start_date"]:
            raise ValidationError("end_date is before start_date.", "end_date")
        if data.get("event_type") == refs.EVENT_TYPES["hybrid"] and not data.get("query"):
            raise ValidationError("hybrid needs a query: the site's keyword-less list ignores it.", "event_type")


class EventsDetailsSchema(BaseSchema):
    event = EventRefField(metadata={"description": "event id (317383946) or a meetup.com event link"})


class EventsSimilarSchema(BaseSchema):
    event = EventRefField(metadata={"description": "event id (317383946) or a meetup.com event link"})
    limit = LimitField(default=MAX_SIMILAR, max_size=MAX_SIMILAR,
                       metadata={"description": "similar events to return, up to 10"})


# ---- groups --------------------------------------------------------------------------

class GroupsSearchSchema(BaseSchema):
    query = _query_field("groups")
    location = _location_field()
    distance = _distance_field()
    category = _category_field()
    page = PageField(max_page=MAX_PAGE, metadata={"description": f"page number, from 1 ({GROUPS_PER_PAGE} groups a page)"})


class GroupsDetailsSchema(BaseSchema):
    group = GroupRefField(metadata={"description": "the group's url name (nycpython) or a meetup.com group link"})


class GroupsEventsSchema(BaseSchema):
    group = GroupRefField(metadata={"description": "the group's url name (nycpython) or a meetup.com group link"})
    status = DefaultedChoice(list(refs.GROUP_EVENT_STATUSES), load_default="upcoming",
                             metadata={"description": "upcoming (soonest first, 30 a page) or past (latest first, "
                                                      "10 a page, cancelled ones included)"})
    title = StrippedString(load_default=None, validate=_max_length(100),
                           metadata={"description": "only events whose title has these words"})
    from_date = DateField(metadata={"description": "only events on or after this day, YYYY-MM-DD (a UTC day)"})
    to_date = DateField(metadata={"description": "only events on or before this day, YYYY-MM-DD (a UTC day)"})
    cursor = CursorField(metadata={"description": "next_cursor of the previous page (omit for the first page)"})

    @validates_schema
    def _check(self, data, **kwargs):
        if data.get("from_date") and data.get("to_date") and data["to_date"] < data["from_date"]:
            raise ValidationError("to_date is before from_date.", "to_date")


# ---- topics / locations --------------------------------------------------------------

class TopicsListSchema(BaseSchema):
    pass


class TopicsDetailsSchema(BaseSchema):
    topic = TopicRefField(metadata={"description": "the topic's url key (python) or a meetup.com topic link"})


class TopicsGroupsSchema(BaseSchema):
    topic = TopicRefField(metadata={"description": "the topic's url key (python) or a meetup.com topic link"})
    page = PageField(max_page=MAX_TOPIC_GROUPS_PAGE,
                     metadata={"description": f"page number, from 1 ({TOPIC_GROUPS_PER_PAGE} groups a page)"})


class TopicsSuggestionsSchema(BaseSchema):
    query = QueryField(max_length=100, metadata={"description": "the start of a topic name"})


class LocationsSuggestionsSchema(BaseSchema):
    query = QueryField(max_length=100, metadata={"description": "the start of a place name, or a US zip code"})
