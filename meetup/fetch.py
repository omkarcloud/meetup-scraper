"""Meetup transport: plain curl_cffi with chrome TLS on the calls
www.meetup.com's own pages make. No browser, no login, no cookie and no
token. One session per request thread on the exit config.MEETUP_EXIT names
(the server's own IP in production); a retryable failure drops the session,
so the retry rides a fresh connection.

Two upstreams (every surface answered 200 on 2026-11-21):

  the data API   POST https://www.meetup.com/gql2  (GraphQL)
    The pages send an operation by name, variables and a saved id
    (queries.py); the server answers {"data": ...}. An id the server no
    longer knows answers HTTP 200 with a PersistedQueryNotFound error:
    the operation's text is sent instead (and for the next
    TEXT_ONLY_SECONDS, without asking by id first).
    Operations used (each sent as its page sends it):
      eventSearchWithSeries / recommendedEventsWithSeries
                      the find page's event list, with / without keywords
      groupSearch / getRecommendedGroups
                      the find page's group list, with / without keywords
      groupHome, getGroupFeedbackInfo
                      a group's page: the group, and its rating summary
      getUpcomingGroupEvents / getPastGroupEvents
                      a group's events page (30 / 10 rows a page, fixed by
                      the operation)
      getEventHomeClientOnly, getEventByIdForAttendees
                      what an event page loads after its HTML: how to find
                      it and the RSVP questions; the first 20 attendees
      groupSimilarEventsByEvent
                      "you may also like" of an event page (10 at most)
      getAllTopicGroupsByUrlkey
                      every group of a topic
      getSuggestedTopics, getLocationSearch
                      the search boxes' suggestions: topics, places
      getTopicStats   a topic's worldwide group and member counts (ours,
                      sent as text: the topic page's own figure is 0 for
                      most topics)
    A list asked for more than MAX_FIRST rows answers an EMPTY list with
    HTTP 200 (no error) on the two searches and the keyword-less event
    list, so `first` never passes it.

  the pages      GET https://www.meetup.com/...  (server-rendered HTML)
    /<group>/events/<id>/   an event: everything about it sits in the
                            page's __NEXT_DATA__ (no data call returns the
                            whole record). A wrong group part redirects to
                            the right one. Unknown id: HTTP 404.
    /topics/                the topic directory (20 categories)
    /topics/<key>/          one topic. Unknown key: HTTP 500 (the site's
                            own error page), which this module reads as
                            not found only after the data API says the
                            topic does not exist.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  MeetupUpstreamError   transport failure / 5xx / unexpected body   retryable
  MeetupBlocked         401 / 403 / 429 / a challenge page          retryable
  MeetupSchemaChanged   the server rejected an operation's text     not retried
  MeetupBadRequest      the site rejected the parameters            never retried
  MeetupNotFound        unknown event / group / topic               never retried
"""
import json
import secrets
import threading
import time

import config
import egress
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from meetup import queries
from meetup.refs import SITE, ascii_link, group_link
from scraper_utils import pages, retry, sessions

IMPERSONATE = "chrome"
API_TIMEOUT = 30            # the largest answers (200 events) took 12 s on 2026-11-21
PAGE_TIMEOUT = 25

GQL = SITE + "/gql2"
MAX_FIRST = 200             # 201 answers an empty list with HTTP 200 (measured 2026-11-21)
TEXT_ONLY_SECONDS = 6 * 3600        # after a PersistedQueryNotFound, how long an operation goes out as text

# What the site's own JavaScript sends with every data call (samples of
# 2026-11-21). The session adds user-agent, the sec-ch-ua hints,
# accept-language, accept-encoding and the cookies by itself; `referer`,
# `baggage` and `sentry-trace` are added per call (_gql_headers).
GQL_HEADERS = {
    "accept": "*/*",
    "apollographql-client-name": "nextjs-web",
    "content-type": "application/json",
    "origin": SITE,
    "priority": "u=1, i",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}

# The page's error tracker tags every data call with the page's trace: a
# random trace id per page load, shared by `sentry-trace` and `baggage`,
# and a span id per call. The release is the site build the samples came
# from; the public key and org id are the site's own tracker settings.
SENTRY_RELEASE = "49c0734fc933ebd9f147e96038f608ad12d30e9e"     # site build of 2026-11-21
SENTRY_PUBLIC_KEY = "5d12cd2317664353456ab4c40d079af2"
SENTRY_ORG_ID = "6787"
SENTRY_SAMPLE_RATE = "0.01"

# What Chrome sends when a page is opened from the address bar.
PAGE_HEADERS = {
    "accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,image/jxl,image/avif,image/webp,"
               "image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"),
    "priority": "u=0, i",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
}

NEXT_DATA_OPEN = '<script id="__NEXT_DATA__" type="application/json">'


class MeetupUpstreamError(UpstreamError):
    """Transport failure, 5xx or an unexpected payload — retryable."""


class MeetupBlocked(MeetupUpstreamError, Blocked):
    """401 / 403 / 429, or a challenge page — retryable."""


class MeetupSchemaChanged(UpstreamError):
    """The server rejected an operation's text (the site changed its
    schema): the same request cannot pass, so it is not retried."""


class MeetupBadRequest(BadRequest):
    """The site rejected the parameters — never retried."""


class MeetupNotFound(NotFound):
    """No such event, group or topic — never retried."""


# ---- sessions ------------------------------------------------------------------------

# One curl session per request thread (a curl handle must not be shared
# across threads). The calls are stateless: no cookie or token is needed.
_local = threading.local()


def _session():
    return sessions.thread_session(
        _local, lambda: egress.exit_session(config.MEETUP_EXIT, impersonate=IMPERSONATE))


def _drop_session():
    """Close the thread's session so the retry rides a fresh connection / exit."""
    sessions.drop(_local)


def _retrying(fn):
    """fn() under the shared retry policy: only MeetupUpstreamError
    (MeetupBlocked included) is retried; the others surface at once."""
    return retry.run(fn, config, MeetupUpstreamError, lambda e: _drop_session())


# ---- the data API --------------------------------------------------------------------

# Operations whose saved id the server no longer knows -> until when they
# go out as text. Shared by every thread: one refusal moves them all.
_text_only = {}
_text_only_lock = threading.Lock()


def _as_text(operation):
    if queries.OPERATIONS[operation][0] is None:        # no page sends it: it has no saved id
        return True
    with _text_only_lock:
        until = _text_only.get(operation)
        if until and until > time.time():
            return True
        _text_only.pop(operation, None)
        return False


def _mark_text_only(operation):
    with _text_only_lock:
        _text_only[operation] = time.time() + TEXT_ONLY_SECONDS


def _gql_headers(referer):
    trace_id, span_id = secrets.token_hex(16), secrets.token_hex(8)
    sample_rand = f"0.{secrets.randbelow(10 ** 17):017d}".rstrip("0") or "0.1"
    return {
        **GQL_HEADERS,
        # a group or event page whose name is not ASCII goes out percent-encoded, as Chrome sends it
        "referer": ascii_link(referer) or SITE + "/",
        "baggage": (f"sentry-environment=production,sentry-release={SENTRY_RELEASE},"
                    f"sentry-public_key={SENTRY_PUBLIC_KEY},sentry-trace_id={trace_id},sentry-org_id={SENTRY_ORG_ID},"
                    f"sentry-sampled=false,sentry-sample_rand={sample_rand},sentry-sample_rate={SENTRY_SAMPLE_RATE}"),
        "sentry-trace": f"{trace_id}-{span_id}-0",
    }


def request_body(operation, variables, as_text=False):
    """The JSON body of one data call: by saved id, as the page sends it, or
    with the operation's text."""
    saved_id, text = queries.OPERATIONS[operation]
    if as_text:
        return {"operationName": operation, "variables": variables, "query": text}
    return {"operationName": operation, "variables": variables,
            "extensions": {"persistedQuery": {"version": 1, "sha256Hash": saved_id}}}


def _check_status(resp, label):
    status = resp.status_code
    if status == 200:
        return
    if pages.is_challenged(status, resp.headers, resp.text[:4000]) or status in (401, 403, 429):
        raise MeetupBlocked(f"HTTP {status} for {label}")
    raise MeetupUpstreamError(f"HTTP {status} for {label}")


def _error_kind(errors):
    """'not_saved' for a PersistedQueryNotFound, 'validation' when the
    server rejected the document or its variables, else 'other'."""
    kinds = set()
    for error in errors if isinstance(errors, list) else []:
        if not isinstance(error, dict):
            continue
        classification = str((error.get("extensions") or {}).get("classification") or "")
        message = str(error.get("message") or "")
        if "PersistedQueryNotFound" in (classification, message):
            kinds.add("not_saved")
        elif classification == "ValidationError" or message.startswith("Validation error"):
            kinds.add("validation")
        else:
            kinds.add("other")
    for kind in ("not_saved", "validation"):
        if kind in kinds:
            return kind
    return "other"


def _post(operation, variables, referer, as_text):
    label = f"{operation}{' (text)' if as_text else ''}"
    try:
        resp = _session().post(GQL, data=json.dumps(request_body(operation, variables, as_text)),
                               headers=_gql_headers(referer), timeout=API_TIMEOUT)
    except Exception as e:
        raise MeetupUpstreamError(f"request failed for {label}: {type(e).__name__}: {e}")
    _check_status(resp, label)
    try:
        payload = resp.json()
    except Exception:
        raise MeetupBlocked(f"non-JSON answer for {label}: {resp.text[:120]!r}")
    if not isinstance(payload, dict):
        raise MeetupUpstreamError(f"unexpected payload for {label}: {resp.text[:120]!r}")
    return payload


def gql(operation, variables, referer=None):
    """One operation -> its `data` object. Sent by saved id, as the page
    sends it; an id the server no longer knows is answered by the text."""
    def once():
        as_text = _as_text(operation)
        payload = _post(operation, variables, referer, as_text)
        errors = payload.get("errors")
        if errors and not as_text and _error_kind(errors) == "not_saved":
            _mark_text_only(operation)
            print(f"meetup: the saved id of {operation} is unknown to the server; sending its text for "
                  f"{TEXT_ONLY_SECONDS // 3600} h")
            payload = _post(operation, variables, referer, True)
            errors = payload.get("errors")
        data = payload.get("data")
        if errors and not isinstance(data, dict):
            message = str((errors[0] or {}).get("message") if isinstance(errors, list) and errors else errors)[:300]
            kind = _error_kind(errors)
            if kind == "validation":
                raise MeetupSchemaChanged(f"the site rejected {operation}: {message}")
            if kind == "not_saved":
                raise MeetupUpstreamError(f"{operation}: the server knows neither its id nor its text")
            raise MeetupUpstreamError(f"{operation} answered an error: {message}")
        if not isinstance(data, dict):
            raise MeetupUpstreamError(f"{operation} answered no data: {str(payload)[:160]!r}")
        return data
    return _retrying(once)


# ---- the pages -----------------------------------------------------------------------

def next_data(html):
    """The JSON a Next.js page carries in its HTML, or None."""
    start = html.find(NEXT_DATA_OPEN)
    if start < 0:
        return None
    start += len(NEXT_DATA_OPEN)
    end = html.find("</script>", start)
    try:
        return json.loads(html[start:end])
    except ValueError:
        return None


def _page(url, label, not_found=(404,)):
    """GET a page -> (final URL, its __NEXT_DATA__). A status listed in
    `not_found` answers (final URL, None)."""
    def once():
        try:
            resp = _session().get(url, headers=PAGE_HEADERS, timeout=PAGE_TIMEOUT, allow_redirects=True)
        except Exception as e:
            raise MeetupUpstreamError(f"request failed for {label}: {type(e).__name__}: {e}")
        if resp.status_code in not_found:
            return str(resp.url), None
        _check_status(resp, label)
        data = next_data(resp.text)
        if not isinstance(data, dict):
            if pages.is_challenged(resp.status_code, resp.headers, resp.text[:4000]):
                raise MeetupBlocked(f"challenge page for {label}")
            raise MeetupUpstreamError(f"{label}: the page carries no data ({pages.page_title(resp.text)[:80]!r})")
        return str(resp.url), data
    return _retrying(once)


# ---- events --------------------------------------------------------------------------

def fetch_event_search(variables, referer):
    """One page of the find page's event list for keywords."""
    return gql("eventSearchWithSeries", variables, referer)


def fetch_event_browse(variables, referer):
    """One page of the find page's event list without keywords."""
    return gql("recommendedEventsWithSeries", variables, referer)


def fetch_event_page(event_id):
    """An event page -> (its link, its __NEXT_DATA__). The group part of
    the address is not checked by the site (it redirects to the right
    one), so the id alone is enough. Unknown id -> MeetupNotFound."""
    url, data = _page(f"{SITE}/events/events/{event_id}/", f"event {event_id}")
    if data is None:
        raise MeetupNotFound(f"event {event_id} not found")
    return url, data


def fetch_event_extras(event_id, referer):
    """What the event page loads after its HTML: how to find the venue,
    the RSVP questions, the venue's RSVP limits."""
    return gql("getEventHomeClientOnly", {"eventId": str(event_id)}, referer)


def fetch_event_attendees(event_id, referer):
    """The first 20 attendees, as the event page loads them for a visitor
    who is not signed in."""
    variables = {"eventId": str(event_id), "first": 20,
                 "filter": {"rsvpStatus": ["YES", "ATTENDED", "NO_SHOW", "EXCUSED_ABSENCE"]}, "sort": None}
    return gql("getEventByIdForAttendees", variables, referer)


def fetch_similar_events(event_id, limit, referer):
    variables = {"takeEvents": int(limit), "eventId": str(event_id),
                 "dataConfiguration": EVENTS_DATA_CONFIGURATION}
    return gql("groupSimilarEventsByEvent", variables, referer)


# the fixed values the find page sends with its lists
EVENTS_DATA_CONFIGURATION = '{"isSimplifiedSearchEnabled": true, "include_events_from_user_chapters": true}'
GROUPS_DATA_CONFIGURATION = '{ "isSimplifiedGroupSearchEnabled": true }'
EVENTS_INDEX_ALIAS = '"{\\"filterOutWrongLanguage\\": \\"true\\",\\"modelVersion\\": \\"split_offline_online\\"}"'
GROUPS_INDEX_ALIAS = "popular_groups_nearby_current"
SERIES_EVENTS = 5           # numberOfEventsForSeries: upcoming dates listed under a recurring event


# ---- groups --------------------------------------------------------------------------

def fetch_group_search(variables, referer):
    return gql("groupSearch", variables, referer)


def fetch_group_browse(variables, referer):
    return gql("getRecommendedGroups", variables, referer)


def fetch_group(urlname):
    """A group, as its page loads it. Unknown url name -> MeetupNotFound."""
    data = gql("groupHome", {"includePrivateInfo": False, "urlname": urlname}, group_link(urlname))
    if not isinstance(data.get("groupByUrlname"), dict):
        raise MeetupNotFound(f"group {urlname} not found")
    return data


def fetch_group_rating(urlname):
    """The group page's rating summary (average, star breakdown, what
    members liked)."""
    return gql("getGroupFeedbackInfo", {"groupUrlname": urlname, "first": 10}, group_link(urlname))


def fetch_group_events(urlname, status, after=None, title=None, after_time=None, before_time=None):
    """One page of a group's events: upcoming (soonest first, 30 a page) or
    past (latest first, 10 a page). Unknown url name -> MeetupNotFound."""
    operation = "getUpcomingGroupEvents" if status == "upcoming" else "getPastGroupEvents"
    variables = {"urlname": urlname}
    if after_time:
        variables["afterDateTime"] = after_time
    if before_time:
        variables["beforeDateTime"] = before_time
    if title:
        variables["title"] = title
    if after:
        variables["after"] = after
    suffix = "events/" if status == "upcoming" else "events/?type=past"
    data = gql(operation, variables, f"{group_link(urlname)}{suffix}")
    if not isinstance(data.get("groupByUrlname"), dict):
        raise MeetupNotFound(f"group {urlname} not found")
    return data


# ---- topics --------------------------------------------------------------------------

def fetch_topics_page():
    """The topic directory page's __NEXT_DATA__."""
    _, data = _page(f"{SITE}/topics/", "the topics page", not_found=())
    return data


def fetch_topic_page(urlkey):
    """A topic page's __NEXT_DATA__; None when the site answers its error
    page for it (HTTP 404 or 500: an unknown key answers 500)."""
    _, data = _page(f"{SITE}/topics/{urlkey}/", f"topic {urlkey}", not_found=(404, 500))
    return data


def fetch_topic_groups(urlkey, first, after=None):
    """A batch of a topic's groups. Unknown key -> MeetupNotFound."""
    variables = {"urlkey": urlkey, "first": int(first)}
    if after:
        variables["after"] = after
    data = gql("getAllTopicGroupsByUrlkey", variables, f"{SITE}/topics/{urlkey}/all/")
    if not isinstance(data.get("topicByUrlkey"), dict):
        raise MeetupNotFound(f"topic {urlkey} not found")
    return data


def fetch_topic_stats(urlkey):
    """A topic's worldwide counts; `topicByUrlkey` is None for an unknown key."""
    return gql("getTopicStats", {"urlkey": urlkey}, f"{SITE}/topics/{urlkey}/")


def fetch_topic_suggestions(query):
    return gql("getSuggestedTopics", {"query": query}, f"{SITE}/find/")


# ---- locations -----------------------------------------------------------------------

def fetch_locations(query=None, lat=None, lng=None):
    """The location box's suggestions for a text, or the places nearest to
    a point."""
    variables = {"dataConfiguration": "{}", "useImprovedGeoHashIndex": False}
    if query is not None:
        variables = {"query": query, **variables}
    else:
        variables = {"lat": lat, "lon": lng, **variables}
    return gql("getLocationSearch", variables, f"{SITE}/find/")
