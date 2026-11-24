"""Offline tests for the Meetup transport: the request it sends and how it
reads an answer. No network: the session is a stand-in."""
import json
from pathlib import Path

import pytest

from meetup import fetch, queries

FIXTURES = Path(__file__).parent / "fixtures"
UNKNOWN_ID = json.loads((FIXTURES / "error_unknown_saved_id.json").read_text())
VALIDATION = {"errors": [{"message": "Validation error (FieldUndefined@[event/gone]) : Field 'gone' in type 'Event' is undefined",
                          "extensions": {"classification": "ValidationError"}}], "data": None}


class Answer:
    def __init__(self, payload=None, status=200, text=None, url="https://www.meetup.com/x"):
        self.status_code, self.headers, self.url = status, {}, url
        self.text = text if text is not None else json.dumps(payload)

    def json(self):
        return json.loads(self.text)


class Session:
    def __init__(self, answers):
        self.answers, self.sent = list(answers), []

    def post(self, url, data=None, headers=None, timeout=None):
        self.sent.append({"url": url, "body": json.loads(data), "headers": headers})
        return self.answers.pop(0)

    def get(self, url, headers=None, timeout=None, allow_redirects=True):
        self.sent.append({"url": url, "headers": headers})
        return self.answers.pop(0)

    def close(self):
        pass


@pytest.fixture
def session(monkeypatch):
    def install(*answers):
        sess = Session(answers)
        monkeypatch.setattr(fetch, "_session", lambda: sess)
        monkeypatch.setattr(fetch, "_drop_session", lambda: None)
        monkeypatch.setattr(fetch.config, "RETRY_BACKOFF", 0)
        return sess
    fetch._text_only.clear()
    yield install
    fetch._text_only.clear()


def test_every_operation_has_an_id_and_a_text():
    assert len(queries.OPERATIONS) == 15
    assert [name for name, (saved_id, _) in queries.OPERATIONS.items() if saved_id is None] == ["getTopicStats"]
    for name, (saved_id, text) in queries.OPERATIONS.items():
        assert saved_id is None or (len(saved_id) == 64 and int(saved_id, 16) >= 0)
        assert text.lstrip().startswith(f"query {name}(") and "${" not in text
        for spread in set(__import__("re").findall(r"\.\.\.\s*(\w+)", text)) - {"on"}:
            assert f"fragment {spread} on " in text, f"{name} spreads {spread}"


def test_request_goes_out_as_the_page_sends_it(session):
    sess = session(Answer({"data": {"suggestTopics": {"edges": []}}}))
    assert fetch.fetch_topic_suggestions("yoga") == {"suggestTopics": {"edges": []}}
    sent = sess.sent[0]
    assert sent["url"] == "https://www.meetup.com/gql2"
    assert sent["body"] == {"operationName": "getSuggestedTopics", "variables": {"query": "yoga"},
                            "extensions": {"persistedQuery": {"version": 1,
                                                              "sha256Hash": queries.OPERATIONS["getSuggestedTopics"][0]}}}
    headers = sent["headers"]
    assert headers["apollographql-client-name"] == "nextjs-web" and headers["content-type"] == "application/json"
    assert headers["origin"] == "https://www.meetup.com" and headers["referer"] == "https://www.meetup.com/find/"
    assert headers["sec-fetch-site"] == "same-origin" and headers["accept"] == "*/*"
    trace_id = headers["sentry-trace"].split("-")[0]
    assert len(trace_id) == 32 and f"sentry-trace_id={trace_id}" in headers["baggage"]
    assert "accept-language" not in headers and "user-agent" not in headers       # the session's own


def test_unknown_saved_id_falls_back_to_the_text(session):
    sess = session(Answer(UNKNOWN_ID), Answer({"data": {"suggestTopics": {"edges": []}}}),
                   Answer({"data": {"suggestTopics": {"edges": []}}}))
    assert fetch.fetch_topic_suggestions("yoga") == {"suggestTopics": {"edges": []}}
    assert "extensions" in sess.sent[0]["body"]
    assert sess.sent[1]["body"] == {"operationName": "getSuggestedTopics", "variables": {"query": "yoga"},
                                    "query": queries.OPERATIONS["getSuggestedTopics"][1]}
    fetch.fetch_topic_suggestions("pilates")            # the next call goes out as text at once
    assert "query" in sess.sent[2]["body"] and len(sess.sent) == 3
    assert fetch._as_text("getSuggestedTopics") and not fetch._as_text("groupHome")


def test_topic_stats_go_out_as_text_from_the_first_call(session):
    answer = json.loads((FIXTURES / "topic_stats_hiking.json").read_text())
    sess = session(Answer(answer))
    assert fetch.fetch_topic_stats("hiking") == answer["data"]
    assert sess.sent[0]["body"] == {"operationName": "getTopicStats", "variables": {"urlkey": "hiking"},
                                    "query": queries.OPERATIONS["getTopicStats"][1]}
    assert sess.sent[0]["headers"]["referer"] == "https://www.meetup.com/topics/hiking/"
    session(Answer(json.loads((FIXTURES / "topic_stats_unknown.json").read_text())))
    assert fetch.fetch_topic_stats("zzqxjvkwpl") == {"topicByUrlkey": None}


def test_errors(session):
    session(Answer(VALIDATION))
    with pytest.raises(fetch.MeetupSchemaChanged):
        fetch.fetch_topic_suggestions("yoga")
    sess = session(Answer(status=403, text="Forbidden"), Answer(status=429, text=""), Answer(status=403, text=""))
    with pytest.raises(fetch.MeetupBlocked):
        fetch.fetch_topic_suggestions("yoga")
    assert len(sess.sent) == fetch.config.MAX_RETRIES
    session(*[Answer(status=502, text="bad gateway")] * fetch.config.MAX_RETRIES)
    with pytest.raises(fetch.MeetupUpstreamError):
        fetch.fetch_topic_suggestions("yoga")
    session(*[Answer(text="<html>Just a moment...</html>")] * fetch.config.MAX_RETRIES)
    with pytest.raises(fetch.MeetupBlocked):
        fetch.fetch_topic_suggestions("yoga")
    session(*[Answer({"errors": [{"message": "boom"}]})] * fetch.config.MAX_RETRIES)
    with pytest.raises(fetch.MeetupUpstreamError):
        fetch.fetch_topic_suggestions("yoga")


def test_not_found_answers(session):
    session(Answer({"data": {"groupByUrlname": None}}))
    with pytest.raises(fetch.MeetupNotFound):
        fetch.fetch_group("zz-no-such-group")
    session(Answer({"data": {"groupByUrlname": None}}))
    with pytest.raises(fetch.MeetupNotFound):
        fetch.fetch_group_events("zz-no-such-group", "past")
    session(Answer({"data": {"topicByUrlkey": None}}))
    with pytest.raises(fetch.MeetupNotFound):
        fetch.fetch_topic_groups("zzqx", 1)
    session(Answer(status=404, text=(FIXTURES / "event_page_not_found.html").read_text()))
    with pytest.raises(fetch.MeetupNotFound):
        fetch.fetch_event_page("999999999")
    session(Answer(status=500, text="<html><title>Meetup | Internal server error</title></html>"))
    assert fetch.fetch_topic_page("zzqx") is None


def test_pages(session):
    html = (FIXTURES / "event_page_physical.html").read_text()
    final = "https://www.meetup.com/j-dynamic-functional-programming/events/317383946/"
    sess = session(Answer(text=html, url=final))
    link, data = fetch.fetch_event_page("317383946")
    assert link == final and data["props"]["pageProps"]["event"]["id"] == "317383946"
    assert sess.sent[0]["url"] == "https://www.meetup.com/events/events/317383946/"
    assert sess.sent[0]["headers"]["sec-fetch-mode"] == "navigate" and "referer" not in sess.sent[0]["headers"]
    assert fetch.next_data("<html></html>") is None
    assert fetch.next_data(fetch.NEXT_DATA_OPEN + "{not json</script>") is None
    session(*[Answer(text="<html><title>Something else</title></html>")] * fetch.config.MAX_RETRIES)
    with pytest.raises(fetch.MeetupUpstreamError):
        fetch.fetch_topics_page()


def test_variables_of_the_page_calls(session):
    sess = session(Answer({"data": {"event": {}}}), Answer({"data": {"groupByUrlname": {"id": "1"}}}),
                   Answer({"data": {"groupByUrlname": {"id": "1"}}}), Answer({"data": {"result": []}}),
                   Answer({"data": {"result": []}}))
    fetch.fetch_event_attendees("317383946", "https://www.meetup.com/x/events/317383946/")
    assert sess.sent[0]["body"]["variables"] == {"eventId": "317383946", "first": 20, "sort": None,
                                                 "filter": {"rsvpStatus": ["YES", "ATTENDED", "NO_SHOW", "EXCUSED_ABSENCE"]}}
    fetch.fetch_group("nycpython")
    assert sess.sent[1]["body"]["variables"] == {"includePrivateInfo": False, "urlname": "nycpython"}
    assert sess.sent[1]["headers"]["referer"] == "https://www.meetup.com/nycpython/"
    fetch.fetch_group_events("nycpython", "past", after="abc", title="pydata", before_time="2026-11-21T11:26:47.258Z")
    assert sess.sent[2]["body"]["operationName"] == "getPastGroupEvents"
    assert sess.sent[2]["body"]["variables"] == {"urlname": "nycpython", "beforeDateTime": "2026-11-21T11:26:47.258Z",
                                                 "title": "pydata", "after": "abc"}
    fetch.fetch_locations(query="New York ny")
    assert sess.sent[3]["body"]["variables"] == {"query": "New York ny", "dataConfiguration": "{}",
                                                 "useImprovedGeoHashIndex": False}
    fetch.fetch_locations(lat=51.5, lng=-0.12)
    assert sess.sent[4]["body"]["variables"] == {"lat": 51.5, "lon": -0.12, "dataConfiguration": "{}",
                                                 "useImprovedGeoHashIndex": False}


def test_a_group_name_outside_ascii_goes_out_percent_encoded_in_the_referer(session):
    """A header carries ASCII only: the raw name made every group call fail
    (UnicodeEncodeError, 2026-11-23). The variables keep the name as it is."""
    name = "全球華人職場英語培訓-business-english-for-global-professionals"
    page = ("https://www.meetup.com/%E5%85%A8%E7%90%83%E8%8F%AF%E4%BA%BA%E8%81%B7%E5%A0%B4%E8%8B%B1%E8%AA%9E"
            "%E5%9F%B9%E8%A8%93-business-english-for-global-professionals/")
    sess = session(Answer({"data": {"groupByUrlname": {"id": "1"}}}), Answer({"data": {"groupByUrlname": {"id": "1"}}}),
                   Answer({"data": {"groupByUrlname": {"id": "1"}}}), Answer({"data": {"groupByUrlname": {"id": "1"}}}))
    fetch.fetch_group(name)
    fetch.fetch_group_rating(name)
    fetch.fetch_group_events(name, "upcoming")
    fetch.fetch_group_events(name, "past")
    assert [sent["headers"]["referer"] for sent in sess.sent] == [page, page, page + "events/", page + "events/?type=past"]
    assert sess.sent[0]["body"]["variables"]["urlname"] == name


def test_every_referer_goes_out_as_ascii():
    assert fetch._gql_headers("https://www.meetup.com/全球/events/1/")["referer"] == (
        "https://www.meetup.com/%E5%85%A8%E7%90%83/events/1/")
    # an address that is ASCII already goes out as it is, its escapes included
    search = "https://www.meetup.com/find/?keywords=python&location=us--ny--New%20York&source=EVENTS"
    assert fetch._gql_headers(search)["referer"] == search
    assert fetch._gql_headers(None)["referer"] == "https://www.meetup.com/"
