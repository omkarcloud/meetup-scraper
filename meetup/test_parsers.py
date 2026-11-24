"""Offline tests for the Meetup parsers, reference resolvers and time
windows, against the fixtures captured on 2026-11-21."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from meetup import parsers, refs, timeframes
from meetup.fetch import next_data

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text())


def data(name):
    return load(name)["data"]


def _keys(value, path=""):
    """Every key of a parsed answer, for the naming rules."""
    if isinstance(value, dict):
        for key, inner in value.items():
            yield key
            yield from _keys(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _keys(inner)


def _values(value):
    if isinstance(value, dict):
        for inner in value.values():
            yield from _values(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _values(inner)
    else:
        yield value


def assert_clean(parsed):
    for key in _keys(parsed):
        assert key == key.lower() and "__" not in key and key != "url", key
    for value in _values(parsed):
        assert value != "" and value != "N/A"


# ---- event lists ---------------------------------------------------------------------

def test_event_search_rows():
    listing = parsers.parse_event_list(data("events_search_python.json"))
    assert len(listing["events"]) == 12 and listing["has_next"] is True
    assert_clean(listing)
    online, physical = listing["events"][0], listing["events"][1]
    assert online["event_type"] == "online" and online["is_online"] is True and online["venue"] is None
    assert physical["id"] == "317383946"
    assert physical["link"] == "https://www.meetup.com/j-dynamic-functional-programming/events/317383946/"
    assert physical["starts_at"] == "2026-12-08T23:30:00Z"
    assert physical["starts_at_local"] == "2026-12-08T18:30:00-05:00"
    assert physical["timezone"] == "America/New_York"
    assert physical["going_count"] == 5 and physical["max_attendees"] == 23
    assert physical["is_free"] is True and physical["fee"] is None
    assert physical["venue"] == {"name": "Brouwerij Lane", "address": "78 Greenpoint Ave, Brooklyn, NY 11222, USA",
                                 "city": "Brooklyn", "state": "NY", "country": "US"}
    assert physical["group"]["url_name"] == "j-dynamic-functional-programming"
    assert physical["group"]["rating"] == 4.78 and physical["group"]["rating_count"] == 126
    series = physical["series"]
    assert series["description"] == "Every 2nd Tuesday of the month"
    assert series["monthly"] == {"day": "tuesday", "week_of_month": 2} and series["weekly"] is None
    assert series["upcoming_dates"][1]["event_id"] == "sfnhctykccbqb"
    assert series["upcoming_dates"][1]["link"].endswith("/events/sfnhctykccbqb/")


def test_event_rows_share_their_keys():
    for name in ("events_search_python.json", "events_browse_new_york.json", "events_search_hybrid.json"):
        rows = parsers.parse_event_list(data(name))["events"]
        assert rows and len({tuple(row) for row in rows}) == 1, name


def test_event_rows_leave_people_out():
    """The sample attendees inside a row are shown nowhere: no name of
    theirs is in the answer."""
    raw = data("events_search_python.json")
    assert "Devon McCormick" in json.dumps(raw)
    text = json.dumps(parsers.parse_event_list(raw))
    assert "Devon" not in text and "memberPhoto" not in text and "/photos/member/" not in text


def test_event_list_kinds_and_fee():
    hybrid = parsers.parse_event_list(data("events_search_hybrid.json"))
    assert {row["event_type"] for row in hybrid["events"]} == {"hybrid"} and hybrid["has_next"] is False
    browse = parsers.parse_event_list(data("events_browse_new_york.json"))
    assert len(browse["events"]) == 9 and browse["has_next"] is False
    assert all(row["going_count"] >= 100 for row in browse["events"])
    paid = [row for row in parsers.parse_event_list(data("events_search_python.json"))["events"] if row["fee"]]
    for row in paid:
        assert row["is_free"] is False and isinstance(row["fee"]["amount"], (int, float))
        assert row["fee"]["currency"] == "USD" and row["fee"]["payment_method"] in ("cash", "paypal")


def test_event_list_empty():
    for name in ("events_search_past_end.json", "events_browse_no_results.json"):
        assert parsers.parse_event_list(data(name)) == {"events": [], "has_next": False}


def test_similar_events():
    rows = parsers.parse_similar_events(data("events_similar.json"))
    assert len(rows) == 3 and rows[0]["id"] == "317213249" and rows[0]["status"] == "active"
    assert rows[0]["ends_at"] == "2026-12-12T21:00:00Z" and rows[0]["going_count"] == 16
    assert rows[0]["group"]["url_name"] == "nj-code-coffee" and rows[0]["venue"]["city"] == "Newark"
    assert_clean(rows)
    assert parsers.parse_similar_events(data("events_similar_none.json")) == []


def test_group_events():
    upcoming = parsers.parse_group_events(data("group_events_upcoming.json"))
    assert upcoming["total_count"] == 9 and len(upcoming["events"]) == 9 and upcoming["next_cursor"] is None
    first = upcoming["events"][0]
    assert first["status"] == "active" and first["venue"]["id"] and first["group"]["url_name"] == "ccccc-nyc"
    assert first["created_at"] and first["is_rsvp_closed"] is False
    assert_clean(upcoming)
    past = parsers.parse_group_events(data("group_events_past.json"))
    assert past["total_count"] == 953 and len(past["events"]) == 10
    assert past["next_cursor"] == "Mjk2MjYzMTIwOjE2OTcwNjM0MDAwMDA="
    assert past["events"][0]["status"] == "past" and past["events"][0]["venue"] is None
    none = parsers.parse_group_events(data("group_events_none.json"))
    assert none["events"] == [] and none["total_count"] == 0 and none["next_cursor"] is None
    assert parsers.parse_group_events(data("group_events_not_found.json")) is None


# ---- an event page -------------------------------------------------------------------

def test_event_page_physical():
    page = next_data((FIXTURES / "event_page_physical.html").read_text())
    event = parsers.parse_event(page, data("event_extras_physical.json"), data("event_attendees_physical.json"))
    assert_clean(event)
    assert event["id"] == "317383946" and event["token"] == "sfnhctyjcqblb"
    assert event["status"] == "active" and event["time_status"] == "upcoming" and event["event_type"] == "in_person"
    assert event["starts_at"] == "2026-12-08T23:30:00Z" and event["ends_at"] == "2026-12-09T01:30:00Z"
    assert event["going_count"] == 5 and event["waitlist_count"] == 0 and event["attendee_count"] == 5
    assert event["max_attendees"] == 23 and event["max_guests_per_member"] == 5 and event["is_guests_allowed"] is True
    assert event["venue"]["lat"] == 40.729628 and event["venue"]["lng"] == -73.957911 and event["venue"]["id"] == "28473594"
    assert event["series"] == {"description": "Every 2nd Tuesday of the month"}
    assert event["hosts"] == [{"name": "Devon M.", "is_super_organizer": False,
                               "photo": "https://secure.meetupstatic.com/photos/member/a/5/3/9/highres_298242297.jpeg"}]
    assert [topic["key"] for topic in event["topics"]] == ["mathematics", "ui-ux-design", "software-development", "algorithms"]
    assert event["group"]["member_count"] == 340 and event["group"]["category"]["key"] == "technology"
    assert event["group"]["rating"] == 4.78 and event["group"]["rating_count"] == 126 and event["group"]["status"] == "paid"
    # 5 loaded: three cards, the photos of the other two
    assert [a["shown_as"] for a in event["attendees"]] == ["card", "card", "card", "photo", "photo"]
    assert event["attendees"][0] == {"name": "Devon McCormick", "role": "organizer", "is_host": True, "guests_count": 0,
                                     "photo": "https://secure.meetupstatic.com/photos/member/a/5/3/9/highres_298242297.jpeg",
                                     "shown_as": "card"}
    assert event["attendees"][1]["name"] == "Dan"       # a locked RSVP shows the first word only


def test_event_page_online_shows_six_attendees_as_the_page_does():
    """Checked against the live page on 2026-11-21: cards PyMC Labs (Super
    Organizer), NumFOCUS, Inc. (Co-organizer), Aaron (Member), then the
    photos of three more attendees, which the page prints no name for."""
    event = parsers.parse_event(load("event_online.next_data.json"), None, data("event_attendees_online.json"))
    shown = event["attendees"]
    assert [(a["name"], a["role"], a["shown_as"]) for a in shown] == [
        ("PyMC Labs", "super_organizer", "card"), ("NumFOCUS, Inc.", "co_organizer", "card"),
        ("Aaron", "member", "card"), (None, None, "photo"), (None, None, "photo"), (None, None, "photo")]
    assert all(a["photo"] for a in shown[3:])
    assert shown[0]["photo"] == "https://secure.meetupstatic.com/photos/member/1/7/7/c/highres_310146012.jpeg"
    assert event["attendee_count"] == 19 and event["venue"] is None and event["is_online"] is True
    assert event["external_chat"] == {"platform": "discord", "link": "https://discord.gg/kJDhGh23Am"}
    assert [host["name"] for host in event["hosts"]] == ["PyMC L.", "NumFOCUS, I."]
    every = parsers.parse_event(load("event_online.next_data.json"), None, data("event_attendees_online.json"),
                                every_loaded_attendee=True)["attendees"]
    assert len(every) == 19 and {a["shown_as"] for a in every} == {"loaded"}
    assert every[3]["name"] == "Artur" and every[3]["role"] == "member"


def test_an_attendee_shown_as_a_photo_has_no_name_even_when_the_rsvp_is_unlocked():
    """The owner's decision (2026-11-24): a photo is all the page shows of
    these attendees; the whole name in its image label stays out."""
    rsvp = {"isRsvpUnlocked": True, "isHost": True, "guestsCount": 0,
            "member": {"id": "1", "name": "Jane Q. Example"}, "membership": {"role": "COORGANIZER"}}
    for unlocked in (True, False):
        photo = parsers._attendee({**rsvp, "isRsvpUnlocked": unlocked}, "photo")
        assert photo == {"name": None, "role": None, "is_host": None, "guests_count": None,
                         "photo": None, "shown_as": "photo"}
    # a card still prints what it always printed: the whole name when unlocked, else the first word
    assert parsers._attendee(rsvp, "card")["name"] == "Jane Q. Example"
    assert parsers._attendee({**rsvp, "isRsvpUnlocked": False}, "card")["name"] == "Jane"


def test_event_page_kinds():
    paid = parsers.parse_event(load("event_paid.next_data.json"))
    assert paid["is_free"] is False
    assert paid["fee"] == {"amount": 5, "currency": "USD", "payment_method": "paypal", "is_required": True,
                           "has_promo_codes": True, "early_bird_discount": None}
    assert paid["group"]["pro_network"]["url_name"] == "web-performance-meetups"
    assert paid["rsvp_opens_at"] == "2026-10-27T15:28:00Z" and paid["attendees"] == []
    assert paid["venue"]["google_maps_link"].startswith("https://www.google.com/maps/")
    hybrid = parsers.parse_event(load("event_hybrid.next_data.json"))
    assert hybrid["event_type"] == "hybrid" and hybrid["is_online"] is False and hybrid["venue"]["city"] == "New York"
    assert hybrid["interested_count"] == 27 and hybrid["waitlist_mode"] == "off"
    assert "Gustavo" not in json.dumps(hybrid)                  # the "interested" sample is not shown
    series_date = parsers.parse_event(load("event_series_date.next_data.json"))
    assert series_date["id"] == "sfnhctykccbqb" and series_date["link"].endswith("/events/sfnhctykccbqb/")
    for name in ("event_paid", "event_hybrid", "event_series_date", "event_cancelled", "event_past"):
        assert_clean(parsers.parse_event(load(name + ".next_data.json")))


def test_event_of_a_private_group_is_sparse():
    event = parsers.parse_event(load("event_private_group.next_data.json"))
    assert event["description"] is None and event["venue"] is None and event["group"]["is_private"] is True
    assert event["hosts"][0]["name"] is None and event["title"]


def test_ended_event_keeps_only_what_the_public_list_shows():
    for name, status in (("event_past.next_data.json", "past"), ("event_cancelled.next_data.json", "cancelled")):
        page = load(name)
        assert parsers.is_ended(page) is True
        full = parsers.parse_event(page)
        assert full["status"] == status and full["time_status"] == "ended" and full["hosts"]
        public = parsers.public_part_of_ended(full)
        assert public["hosts"] == [] and public["attendees"] == [] and public["topics"] == []
        assert public["token"] is None and public["venue"]["lat"] is None and public["venue"]["name"]
        assert public["title"] == full["title"] and public["going_count"] == full["going_count"]
        assert list(public) == list(full)
    assert parsers.is_ended(load("event_online.next_data.json")) is False


def test_event_page_without_an_event():
    page = next_data((FIXTURES / "event_page_not_found.html").read_text())
    assert parsers.page_event(page) is None and parsers.parse_event(page) is None
    assert parsers.parse_event(None) is None and parsers.parse_event({}) is None


def test_page_order_and_short_lists():
    def rsvp(member_id, host=False, photo=True):
        return {"node": {"isHost": host, "isRsvpUnlocked": True, "membership": {"role": "MEMBER"}, "guestsCount": 0,
                         "member": {"id": member_id, "name": f"M {member_id}", "memberPhoto": {"id": "5"} if photo else None}}}
    loaded = {"event": {"rsvps": {"totalCount": 4, "edges": [rsvp("1"), rsvp("2", photo=False), rsvp("3", host=True), rsvp("4")]}}}
    shown = parsers.shown_attendees(loaded)
    assert [a["name"] for a in shown] == ["M 3", "M 4", "M 1", "M 2"]       # host, then photos (reversed), then the rest
    assert {a["shown_as"] for a in shown} == {"card"}                       # four or fewer: a card each
    assert parsers.shown_attendees(None) == [] and parsers.shown_attendees({"event": None}) == []
    former = {"event": {"rsvps": {"edges": [{"node": {"isRsvpUnlocked": True, "membership": None,
                                                      "member": {"id": "9", "name": "Gone Person"}}}]}}}
    assert parsers.shown_attendees(former)[0]["name"] is None
    assert parsers.shown_attendees(former)[0]["role"] == "former_member"


# ---- groups --------------------------------------------------------------------------

def test_group_lists():
    search = parsers.parse_group_list(data("groups_search_python.json"))
    assert len(search["groups"]) == 15 and search["has_next"] is True
    row = search["groups"][0]
    assert row["id"] == "31668164" and row["url_name"] == "Artificial-Intelligence-in-Finance-Algorithmic-Trading"
    assert row["member_count"] == 1039 and row["rating"] == 4.61 and row["rating_count"] == 54
    assert row["country"] == "US" and "<p>" not in row["description"] and row["status"] == "paid"
    assert_clean(search)
    assert "Yves" not in json.dumps(search)                     # the sample members are not shown
    browse = parsers.parse_group_list(data("groups_browse_london.json"))
    assert len(browse["groups"]) == 16 and browse["groups"][0]["country"] == "GB"
    assert parsers.parse_group_list(data("groups_search_past_end.json")) == {"groups": [], "has_next": False}


def test_group_details():
    group = parsers.parse_group(data("group_nycpython.json"), data("group_rating_nycpython.json"))
    assert_clean(group)
    assert group["id"] == "263790" and group["link"] == "https://www.meetup.com/nycpython/"
    assert group["description"] == "Meet other local Python Programming Language enthusiasts!"
    assert group["founded_at"] == "2006-06-13T11:20:45Z" and group["member_count"] == 17375 and group["leader_count"] == 9
    assert group["website"] == "http://nycpython.org"
    assert group["social"][0] == {"service": "twitter", "identifier": "@nycpython", "link": "http://twitter.com/nycpython/"}
    assert group["rating"]["average"] == 4.66 and group["rating"]["review_count"] == 3425
    assert group["rating"]["breakdown"][0] == {"stars": 5, "count": 2216}
    assert group["rating"]["disliked"] == [{"topic": "not_engaging", "count": 1}, {"topic": "not_as_described", "count": 2}]
    assert group["organizer"]["name"] == "James Powell" and "id" not in group["organizer"]
    assert group["upcoming_event_count"] == 0 and group["past_event_count"] == 907 and len(group["past_events"]) == 4
    assert group["upcoming_events"] == [] and group["featured_event"] is None
    assert list(group).index("website") < list(group).index("social")
    # the member sample and the leader list are not shown by name
    text = json.dumps(group)
    assert '"Bill"' not in text and "64072142" not in text


def test_group_details_without_the_rating_call():
    group = parsers.parse_group(data("group_ccccc_nyc.json"))
    assert group["rating"]["average"] == 4.57 and group["rating"]["rating_count"] == 729
    assert group["rating"]["breakdown"] == [] and group["rating"]["review_count"] is None
    assert group["video"] == {"provider": "youtube", "link": "https://youtu.be/3vM0TT7f57E"}
    assert group["website"] == "http://www.socialfundation.com" and len(group["social"]) == 1   # "http://" alone is no link
    assert group["upcoming_event_count"] == 78 and len(group["upcoming_events"]) == 4
    assert_clean(group)


def test_group_website_is_not_a_link_back_to_the_site():
    raw = {"groupByUrlname": {"id": "1", "urlname": "x", "socialNetworks": [
        {"service": "OTHER", "identifier": "https://www.meetup.com/x/", "url": "https://www.meetup.com/x/"}]}}
    assert parsers.parse_group(raw)["website"] is None
    raw["groupByUrlname"]["socialNetworks"].append({"service": "OTHER", "identifier": "", "url": "https://x.org"})
    assert parsers.parse_group(raw)["website"] == "https://x.org"


def test_group_pro_network_has_its_link():
    """The group page's call selects no `link` for the network (queries.GROUP_HOME)."""
    raw = {"groupByUrlname": {"id": "1", "urlname": "web-performance-ny", "proNetwork": {
        "id": "573453903050895360", "urlname": "web-performance-meetups", "name": "Web Performance Meetups"}}}
    assert parsers.parse_group(raw)["pro_network"] == {
        "id": "573453903050895360", "name": "Web Performance Meetups", "url_name": "web-performance-meetups",
        "link": "https://www.meetup.com/pro/web-performance-meetups/"}
    # the same link the event page's own data carries for that network
    assert parsers.parse_event(load("event_paid.next_data.json"))["group"]["pro_network"]["link"] == \
        "https://www.meetup.com/pro/web-performance-meetups/"


@pytest.mark.parametrize("link", [
    "https://www.youtube.com/channel/UC51aOZF5nnderbuar5D5ifw/playlists", "https://youtu.be/3vM0TT7f57E",
    "https://discord.gg/ffnmygKf4T", "https://discord.com/invite/abc", "https://chat.whatsapp.com/AbCdEf",
    "https://t.me/mygroup", "https://www.instagram.com/mygroup/", "https://m.facebook.com/mygroup",
    "https://x.com/mygroup", "https://www.linkedin.com/company/mygroup", "https://linktr.ee/mygroup",
    "https://bit.ly/3abc", "https://mygroup.slack.com/", "https://lu.ma/mygroup", "https://mygroup.eventbrite.co.uk/",
    "https://www.patreon.com/mygroup", "https://docs.google.com/forms/d/abc", "https://github.com/mygroup",
    "https://www.meetup.com/mygroup/",
])
def test_group_website_is_not_a_social_or_chat_link(link):
    other = {"service": "OTHER", "identifier": link, "url": link}
    raw = {"groupByUrlname": {"id": "1", "urlname": "x", "socialNetworks": [other]}}
    group = parsers.parse_group(raw)
    assert group["website"] is None
    assert group["social"] == [{"service": "other", "identifier": link, "link": link}]      # it stays there


@pytest.mark.parametrize("link", [
    "http://nycpython.org", "http://startupgrind.com/new-york-city", "https://gdg.community.dev/gdg-sunnyvale/",
    "https://sites.google.com/a/amorc.rosicrucian.org/texas-rosicrucian/Home/sa-ankh-pronaos",
    "https://pydata.github.io/meetup", "https://laurarodben.substack.com/", "https://gcncmeditates.wixsite.com/home",
    "https://netflix.com/", "https://boxing.me/", "https://discordia.org/",
])
def test_group_website_keeps_a_site_of_its_own(link):
    raw = {"groupByUrlname": {"id": "1", "urlname": "x", "socialNetworks": [
        {"service": "OTHER", "identifier": link, "url": link}]}}
    assert parsers.parse_group(raw)["website"] == link


def test_group_website_skips_a_platform_link_for_the_next_one():
    raw = {"groupByUrlname": {"id": "1", "urlname": "x", "socialNetworks": [
        {"service": "OTHER", "identifier": "", "url": "https://discord.gg/abc"},
        {"service": "OTHER", "identifier": "", "url": "https://x.org"},
        {"service": "OTHER", "identifier": "", "url": "http://[broken"}]}}
    assert parsers.parse_group(raw)["website"] == "https://x.org"
    assert parsers._is_platform_link("http://[broken") is True


def test_group_private_and_unknown():
    private = parsers.parse_group(data("group_private.json"))
    assert private["is_private"] is True and private["upcoming_events"] == [] and private["website"] is None
    assert parsers.parse_group(data("group_not_found.json")) is None
    assert parsers.parse_group_rating(data("group_not_found.json")) is None


# ---- topics / locations --------------------------------------------------------------

def test_topics_page():
    categories = parsers.parse_topics_page(load("topics_page.next_data.json"))
    assert len(categories) == 20 and all(category["id"] and category["key"] for category in categories)
    assert categories[0]["name"] == "Art & Culture" and categories[0]["id"] == "521" and len(categories[0]["topics"]) == 43
    assert categories[0]["topics"][0] == {"id": "24147", "name": "3D Artists", "key": "3d-artists",
                                          "link": "https://www.meetup.com/topics/3d-artists/"}
    assert parsers.parse_topics_page({}) == []


def test_topic_page():
    topic = parsers.parse_topic_page(load("topic_python.next_data.json"))
    assert topic["id"] == "1064" and topic["key"] == "python" and topic["link"] == "https://www.meetup.com/topics/python/"
    assert topic["group_count"] == 1534 and topic["member_count"] == 2221274
    assert len(topic["related_topics"]) == 10 and topic["related_topics"][0]["key"] == "mysql"
    assert len(topic["largest_groups"]) == 10 and topic["largest_groups"][0]["member_count"] == 24617
    assert len(topic["newest_groups"]) == 6 and topic["newest_groups"][0]["member_label"] == "Builders"
    assert "venkatesh" not in json.dumps(topic)
    assert_clean(topic)
    assert parsers.parse_topic_page({}) is None and parsers.parse_topic_page(None) is None


def test_topic_counts_are_the_worldwide_stats():
    page = load("topic_hiking.next_data.json")
    assert page["props"]["pageProps"]["topic"]["countryStats"]["groupCount"] == 0       # what the page itself holds
    topic = parsers.parse_topic_page(page, data("topic_stats_hiking.json"))
    assert topic["group_count"] == 1937 and topic["member_count"] == 4442971
    assert_clean(topic)
    # the stats call failed or knows no such topic: no count, rather than the page's 0
    for stats in (None, {}, data("topic_stats_unknown.json")):
        topic = parsers.parse_topic_page(page, stats)
        assert topic["group_count"] is None and topic["member_count"] is None and topic["name"] == "Hiking"
    # where the page has a figure, it stands in
    assert parsers.parse_topic_page(load("topic_python.next_data.json"))["group_count"] == 1534
    # a real 0 from the stats stays 0
    zero = {"topicByUrlkey": {"id": "1", "stats": {"groupCount": 0, "memberCount": 0}}}
    assert parsers.parse_topic_page(page, zero)["group_count"] == 0


def test_topic_groups_and_suggestions():
    groups = parsers.parse_topic_groups(data("topic_groups_python.json"))
    assert groups["topic_id"] == "1064" and len(groups["groups"]) == 22 and groups["has_more"] is True
    assert groups["groups"][0] == {"name": "AI/ML Group", "url_name": "pano-aqil-ai-meetup-group",
                                   "link": "https://www.meetup.com/pano-aqil-ai-meetup-group/",
                                   "city": "Pano Aqil", "state": None, "country": "PK"}
    assert parsers.parse_topic_groups(data("topic_groups_not_found.json")) is None
    repeated = {"topicByUrlkey": {"id": "1", "groups": {"edges": [{"node": {"urlname": "a"}}, {"node": {"urlname": "A"}}]}}}
    assert len(parsers.parse_topic_groups(repeated)["groups"]) == 1
    topics = parsers.parse_topic_suggestions(data("topics_suggestions_python.json"))
    assert len(topics) == 5 and topics[0]["key"] == "machine-learning-with-python"
    assert parsers.parse_topic_suggestions(data("topics_suggestions_none.json")) == []


def test_locations():
    new_york = parsers.parse_locations(data("locations_new_york.json"))
    assert new_york[0] == {"name": "New York, NY, USA", "city": "New York", "borough": None, "neighborhood": None,
                           "state": "NY", "country": "US", "postal_code": "10001", "lat": 40.75, "lng": -73.99,
                           "timezone": "US/Eastern"}
    assert new_york[1]["borough"] == "Bronx"
    raw = parsers.first_place(data("locations_new_york.json"))
    assert raw["lon"] == -73.98999786376953 and raw["zip"] == "10001" and raw["country"] == "us" and "__typename" not in raw
    assert parsers.parse_locations(data("locations_by_point_london.json"))[0]["city"] == "London"
    assert parsers.parse_locations(data("locations_none.json")) == [] and parsers.first_place(data("locations_none.json")) is None
    assert parsers.parse_locations({"result": [{"name": "Paris, France", "zip": "meetup1", "lat": 48.86, "lon": 2.34}]})[0]["postal_code"] is None


# ---- values --------------------------------------------------------------------------

def test_photo_link():
    assert parsers.photo_link({"id": "310146012"}, "member") == \
        "https://secure.meetupstatic.com/photos/member/1/7/7/c/highres_310146012.jpeg"
    assert parsers.photo_link({"id": "537091633", "baseUrl": "https://x/"}) == \
        "https://secure.meetupstatic.com/photos/event/7/b/9/1/highres_537091633.jpeg"
    assert parsers.photo_link({"id": "1", "highResUrl": "https://a/b.jpeg"}) == "https://a/b.jpeg"
    assert parsers.photo_link(None) is None and parsers.photo_link({"id": "0"}) is None


# ---- refs ----------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("317383946", "317383946"),
    ("sfnhctykccbqb", "sfnhctykccbqb"),
    ("https://www.meetup.com/nycpython/events/317383946/", "317383946"),
    ("https://www.meetup.com/en-AU/nycpython/events/317383946/?eventOrigin=x", "317383946"),
    ("meetup.com/x/events/sfnhctykccbqb", "sfnhctykccbqb"),
])
def test_resolve_event(value, expected):
    assert refs.resolve_event(value) == expected


@pytest.mark.parametrize("value", ["", "abc", "NYCPython", "https://www.meetup.com/nycpython/",
                                   "https://example.com/x/events/317383946/", "12 34"])
def test_resolve_event_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_event(value)


@pytest.mark.parametrize("value,expected", [
    ("nycpython", "nycpython"), ("NYCPython", "NYCPython"), ("elevate_social", "elevate_social"),
    ("https://www.meetup.com/nycpython/", "nycpython"),
    ("https://www.meetup.com/fr-FR/nycpython/events/317383946/", "nycpython"),
    ("www.meetup.com/ccccc-nyc/members/", "ccccc-nyc"),
])
def test_resolve_group(value, expected):
    assert refs.resolve_group(value) == expected


@pytest.mark.parametrize("value", ["", "find", "a b", "https://www.meetup.com/find/?keywords=x",
                                   "https://www.meetup.com/topics/python/", "https://example.com/nycpython/"])
def test_resolve_group_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_group(value)


def test_resolve_topic_and_location():
    assert refs.resolve_topic("Python") == "python"
    assert refs.resolve_topic("https://www.meetup.com/topics/Python/all/") == "python"
    for bad in ("", "a b", "https://www.meetup.com/nycpython/"):
        with pytest.raises(ValueError):
            refs.resolve_topic(bad)
    assert refs.resolve_location("New York") == {"query": "New York"}
    assert refs.resolve_location("London, gb") == {"query": "London, gb"}
    assert refs.resolve_location(" 40.75 , -73.99 ") == {"lat": 40.75, "lng": -73.99}
    assert refs.resolve_location("10001") == {"query": "10001"}
    for bad in ("", "!!", "95,10", "x" * 101):
        with pytest.raises(ValueError):
            refs.resolve_location(bad)


def test_names_and_links():
    assert refs.short_name("Devon McCormick") == "Devon M." and refs.short_name("NumFOCUS, Inc.") == "NumFOCUS, I."
    assert refs.short_name("lpoug") == "lpoug" and refs.short_name(None) is None
    assert refs.first_word("Artur Posluszny") == "Artur" and refs.first_word("") is None
    assert refs.urlname_of("https://www.meetup.com/nj-code-coffee/events/317213249/") == "nj-code-coffee"
    assert refs.urlname_of("https://www.meetup.com/find/") is None and refs.urlname_of(None) is None
    assert refs.find_link("EVENTS", "data science", "us--ny--New York") == \
        "https://www.meetup.com/find/?keywords=data%20science&location=us--ny--New%20York&source=EVENTS"
    assert len(refs.CATEGORIES) == 20 and refs.CATEGORY_IDS["technology"] == "546"


# ---- time windows --------------------------------------------------------------------

SATURDAY = datetime(2026, 11, 21, 12, 53, 43, tzinfo=timezone.utc)      # 07:53 in New York


@pytest.mark.parametrize("date_range,expected", [
    # the windows the site's own page sent on that Saturday (samples/find_range_*)
    (None, ("2026-11-21T07:53:43-05:00", None, False)),
    ("starting_soon", ("2026-11-21T07:53:43-05:00", None, True)),
    ("today", ("2026-11-21T07:53:43-05:00", "2026-11-21T23:59:59-05:00", False)),
    ("tomorrow", ("2026-11-22T00:00:00-05:00", "2026-11-22T23:59:59-05:00", False)),
    ("this_week", ("2026-11-21T07:53:43-05:00", "2026-11-21T23:59:59-05:00", False)),
    ("this_weekend", ("2026-11-21T07:53:43-05:00", "2026-11-22T23:59:59-05:00", False)),
    ("next_week", ("2026-11-22T00:00:00-05:00", "2026-11-29T23:59:59-05:00", False)),
    ("next_weekend", ("2026-11-27T16:59:59-05:00", "2026-11-29T23:59:59-05:00", False)),
])
def test_windows_match_the_site(date_range, expected):
    assert timeframes.window(date_range, zone_name="US/Eastern", now=SATURDAY) == expected


@pytest.fixture
def without_old_zone_names(monkeypatch):
    """The pod's time zone database: Debian 13's tzdata without tzdata-legacy,
    where ZoneInfo("US/Eastern") raises and ZoneInfo("America/New_York") works."""
    import zoneinfo
    real = zoneinfo.ZoneInfo

    def current_names_only(key):
        if key in timeframes.OLD_ZONE_NAMES:
            raise zoneinfo.ZoneInfoNotFoundError(f"No time zone found with key {key}")
        return real(key)
    monkeypatch.setattr(zoneinfo, "ZoneInfo", current_names_only)


@pytest.mark.parametrize("name,offset", [
    ("US/Eastern", "-05:00"), ("US/Central", "-06:00"), ("US/Mountain", "-07:00"), ("US/Pacific", "-08:00"),
    ("US/Arizona", "-07:00"), ("US/Alaska", "-09:00"), ("US/Hawaii", "-10:00"), ("US/Samoa", "-11:00"),
    ("Canada/Atlantic", "-04:00"), ("Canada/Eastern", "-05:00"), ("Canada/Newfoundland", "-03:30"),
    ("Asia/Calcutta", "+05:30"), ("Asia/Katmandu", "+05:45"), ("Asia/Rangoon", "+06:30"), ("Asia/Saigon", "+07:00"),
    ("Asia/Macao", "+08:00"), ("Africa/Asmera", "+03:00"), ("America/Buenos_Aires", "-03:00"),
    ("Europe/Kiev", "+02:00"), ("Pacific/Ponape", "+11:00"),
])
def test_day_filters_use_the_real_clock_without_the_old_zone_names(without_old_zone_names, name, offset):
    start, end, _ = timeframes.window("next_week", zone_name=name, now=SATURDAY)
    assert start.endswith("T00:00:00" + offset) and end.endswith("T23:59:59" + offset)


def test_every_old_zone_name_resolves_without_the_old_files(without_old_zone_names, capsys):
    for old, current in timeframes.OLD_ZONE_NAMES.items():
        assert timeframes.zone_of(old).key == current
    assert capsys.readouterr().out == ""        # none fell back to UTC


def test_old_zone_names_follow_summer_time_without_the_files(without_old_zone_names):
    july = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)                    # a Wednesday, 05:00 in San Francisco
    assert timeframes.window("tomorrow", zone_name="US/Pacific", now=july) == \
        ("2026-07-16T00:00:00-07:00", "2026-07-16T23:59:59-07:00", False)
    assert timeframes.window("today", zone_name="Canada/Eastern", now=july)[1] == "2026-07-15T23:59:59-04:00"
    assert timeframes.day_bound("2026-07-16", "US/Pacific") == "2026-07-16T07:00:00.000Z"
    # the evening in San Francisco is still that day there, though it is already tomorrow in UTC
    evening = datetime(2026, 11, 24, 3, 30, tzinfo=timezone.utc)                # Monday Nov 23, 19:30 in San Francisco
    assert timeframes.window("today", zone_name="US/Pacific", now=evening) == \
        ("2026-11-23T19:30:00-08:00", "2026-11-23T23:59:59-08:00", False)


def test_every_old_zone_name_points_at_the_same_clock():
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    moments = [datetime(2026, 1, 15, 12, tzinfo=timezone.utc), datetime(2026, 7, 15, 12, tzinfo=timezone.utc)]
    assert len(timeframes.OLD_ZONE_NAMES) == 31
    for old, current in timeframes.OLD_ZONE_NAMES.items():
        assert current not in timeframes.OLD_ZONE_NAMES
        try:
            old_zone = ZoneInfo(old)
        except ZoneInfoNotFoundError:           # a machine with the current names only
            continue
        assert [m.astimezone(old_zone).utcoffset() for m in moments] == \
            [m.astimezone(ZoneInfo(current)).utcoffset() for m in moments], old


def test_an_unknown_zone_is_utc_and_logged(capsys):
    assert timeframes.zone_of("no/such-zone") == timezone.utc
    assert "no/such-zone" in capsys.readouterr().out
    assert timeframes.zone_of(None) == timezone.utc and capsys.readouterr().out == ""


def test_windows_other_days_and_custom():
    wednesday = datetime(2026, 11, 18, 15, 0, tzinfo=timezone.utc)
    assert timeframes.window("this_weekend", zone_name="Europe/London", now=wednesday) == \
        ("2026-11-20T16:59:59+00:00", "2026-11-22T23:59:59+00:00", False)
    assert timeframes.window("this_week", zone_name="Europe/London", now=wednesday)[1] == "2026-11-21T23:59:59+00:00"
    sunday = datetime(2026, 11, 22, 15, 0, tzinfo=timezone.utc)
    assert timeframes.window("this_weekend", zone_name="Europe/London", now=sunday)[1] == "2026-11-22T23:59:59+00:00"
    assert timeframes.window("this_week", zone_name="Europe/London", now=sunday)[1] == "2026-11-28T23:59:59+00:00"
    assert timeframes.window(None, "2026-12-10", "2026-12-12", "US/Eastern", SATURDAY) == \
        ("2026-12-10T00:00:00-05:00", "2026-12-12T23:59:59-05:00", False)
    assert timeframes.window(None, "2026-11-01", None, "US/Eastern", SATURDAY)[0] == "2026-11-21T07:53:43-05:00"
    assert timeframes.window(None, None, "2026-11-30", "no/such-zone", SATURDAY) == \
        ("2026-11-21T12:53:43+00:00", "2026-11-30T23:59:59+00:00", False)
    assert timeframes.day_bound("2026-12-01", "US/Eastern") == "2026-12-01T05:00:00.000Z"
    assert timeframes.day_bound("2026-12-01", None, end=True) == "2026-12-01T23:59:59.000Z"
    assert timeframes.now_utc(SATURDAY) == "2026-11-21T12:53:43.000Z"
