"""Raw answers of www.meetup.com -> clean dicts for every /meetup/* endpoint.
Pure functions, no I/O.

Fixtures (fixtures/, captured from the live site on 2026-11-21, each the
raw answer as the site sent it):
  events_search_*.json, events_browse_*.json   the find page's event lists
  groups_search_*.json, groups_browse_*.json   the find page's group lists
  group_*.json, group_rating_*.json            a group page's two data calls
  group_events_*.json                          a group's events page
  event_page_*.html, event_*.next_data.json    event pages (the page, or the
                                               data it carries)
  event_extras_*.json, event_attendees_*.json  what an event page loads next
  events_similar*.json                         "you may also like"
  topics_page / topic_python .next_data.json   topic pages' data
  topic_groups_*.json, topics_suggestions_*.json, locations_*.json

What the site's data holds and its pages do not show a visitor who is not
signed in is left out: member ids, the sample attendees and members inside
list rows and group data, RSVP and join questions. An event's attendees
are the ones its page shows (shown_attendees), unless the caller of
parse_event asks for every one the page loaded.

Forms: a time is given twice, in UTC (`starts_at`) and as the site writes
it, on the event's own clock (`starts_at_local`). A fee is in whole units
of its currency. Event descriptions are Markdown as the organizer wrote
it; group descriptions are HTML upstream and plain text here. Country
codes are upper case.
"""
import html
import re
from urllib.parse import urlparse

from meetup import refs
from scraper_utils.dates import iso_utc
from scraper_utils.text import clean, html_to_text, multiline
from scraper_utils.values import as_dict, as_list, g, rating as _rating, to_int

CARDS_SHOWN = 3         # attendee cards an event page shows on a desktop screen
PHOTOS_SHOWN = 3        # attendee photos in the page's "+N more" card
_ZONE_SUFFIX_RE = re.compile(r"\[[^\]]*\]$")
_TAG_RE = re.compile(r"</?(p|br|a|b|i|u|ul|ol|li|strong|em|span|div|img|font|h[1-6])\b[^>]*>", re.I)
_FAKE_ZIP_RE = re.compile(r"^meetup\d+$", re.I)
_PHOTO_BUCKETS = 60000  # the site files a photo under hex(id % 60000), one digit per folder


# ---- small values --------------------------------------------------------------------

def _lower(value):
    """An upstream token (JOIN_OPEN, PHYSICAL) -> join_open."""
    text = clean(value)
    return text.lower() if text else None


def _upper(value):
    text = clean(value)
    return text.upper() if text else None


def _count(value):
    """A count; None when the site gives none."""
    number = to_int(value)
    return number if number is not None and number >= 0 else None


def _limit(value):
    """A limit where the site writes 0 for "none"."""
    number = to_int(value)
    return number if number else None


def _text(value):
    """Organizer text: HTML -> plain text, anything else with its line breaks."""
    if not isinstance(value, str) or not value.strip():
        return None
    value = html.unescape(value)            # some groups store their tags escaped (&lt;br&gt;)
    if _TAG_RE.search(value):
        return html_to_text(value)
    return multiline(value)


def _local_time(value):
    """The site's own time text, without the "[US/Eastern]" some answers add."""
    text = clean(value)
    return _ZONE_SUFFIX_RE.sub("", text) if text else None


def _utc(value):
    return iso_utc(_local_time(value)) if value else None


def photo_link(photo, kind="event"):
    """A PhotoInfo -> the link of its full-size picture. The answer's own
    link when it carries one, else the link the site's pages build from the
    photo id (kind: "event" for event and group pictures, "member")."""
    photo = as_dict(photo)
    for key in ("highResUrl", "source", "standardUrl"):
        if clean(photo.get(key)):
            return clean(photo.get(key))
    photo_id = to_int(photo.get("id"))
    if not photo_id:
        return None
    folders = "/".join(format(photo_id % _PHOTO_BUCKETS, "x"))
    return f"https://secure.meetupstatic.com/photos/{kind}/{folders}/highres_{photo_id}.jpeg"


def _edges(connection):
    """The nodes of a GraphQL connection."""
    return [as_dict(edge.get("node")) for edge in as_list(as_dict(connection).get("edges"))
            if isinstance(edge, dict) and isinstance(edge.get("node"), dict)]


def _total(connection):
    return _count(as_dict(connection).get("totalCount"))


# ---- pieces of an event ----------------------------------------------------------------

def _topic(node):
    node = as_dict(node)
    key = clean(node.get("urlkey"))
    return {"id": clean(node.get("id")), "name": clean(node.get("name")), "key": key, "link": refs.topic_link(key)}


def _category(node):
    node = as_dict(node)
    if not node:
        return None
    return {"id": clean(node.get("id")), "name": clean(node.get("name")), "key": clean(node.get("urlkey"))}


def _fee(fee, currency=None):
    """EventFeeSettings -> {amount, currency, payment_method, ...}; None for
    a free event. The amount is in whole units (5 = USD 5.00)."""
    fee = as_dict(fee)
    if not fee:
        return None
    out = {
        "amount": fee.get("amount") if isinstance(fee.get("amount"), (int, float)) else None,
        "currency": _upper(fee.get("currency")) or _upper(currency),
    }
    if "accepts" in fee:
        out["payment_method"] = _lower(fee.get("accepts"))
    if "required" in fee:
        out["is_required"] = fee.get("required") if isinstance(fee.get("required"), bool) else None
    if "hasPromoCodes" in fee:
        out["has_promo_codes"] = fee.get("hasPromoCodes") if isinstance(fee.get("hasPromoCodes"), bool) else None
    if "earlyBirdDiscount" in fee:
        early = as_dict(fee.get("earlyBirdDiscount"))
        out["early_bird_discount"] = ({_snake(k): v for k, v in early.items() if k != "__typename"} or None)
    return out


def _snake(name):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", str(name)).lower()


def _venue(venue, event_type=None):
    """A Venue -> its address fields; None for an online event (the site
    names its venue "Online event", with no address and a placeholder
    point) and for a venue the site withholds."""
    venue = as_dict(venue)
    if not venue:
        return None
    name, address = clean(venue.get("name")), clean(venue.get("address"))
    if not address and not clean(venue.get("city")) and (event_type == "ONLINE" or (name or "").lower() == "online event"
                                                         or clean(venue.get("venueType")) == "online"):
        return None
    out = {}
    if "id" in venue:
        out["id"] = clean(venue.get("id"))
    out.update({
        "name": name,
        "address": address,
        "city": clean(venue.get("city")),
        "state": clean(venue.get("state")),
    })
    if "postalCode" in venue:
        out["postal_code"] = clean(venue.get("postalCode"))
    out["country"] = _upper(venue.get("country"))
    lng_key = "lng" if "lng" in venue else "lon"
    if "lat" in venue or lng_key in venue:
        out["lat"] = venue.get("lat") if isinstance(venue.get("lat"), (int, float)) else None
        out["lng"] = venue.get(lng_key) if isinstance(venue.get(lng_key), (int, float)) else None
    if "googleMapsUrl" in venue:
        out["google_maps_link"] = clean(venue.get("googleMapsUrl"))
    return out


def _series(series, with_dates=True):
    """A recurring event's series: how it repeats and its next dates."""
    series = as_dict(series)
    if not series:
        return None
    out = {"description": clean(series.get("description"))}
    weekly, monthly = as_dict(series.get("weeklyRecurrence")), as_dict(series.get("monthlyRecurrence"))
    if "weeklyRecurrence" in series or "monthlyRecurrence" in series:
        out["weekly"] = ({"days": [_lower(day) for day in as_list(weekly.get("weeklyDaysOfWeek"))],
                          "every_weeks": _count(weekly.get("weeklyInterval"))} if weekly else None)
        out["monthly"] = ({"day": _lower(monthly.get("monthlyDayOfWeek")),
                           "week_of_month": to_int(monthly.get("monthlyWeekOfMonth"))} if monthly else None)
    if with_dates and "events" in series:
        out["upcoming_dates"] = [
            {"event_id": clean(node.get("id")),
             "link": refs.event_link(g(node, "group", "urlname", default=None), clean(node.get("id"))),
             "starts_at": _utc(node.get("dateTime")),
             "starts_at_local": _local_time(node.get("dateTime"))}
            for node in _edges(series.get("events"))]
    return out


def _row_group(group, event_link=None):
    """The group an event row names."""
    group = as_dict(group)
    if not group:
        return None
    urlname = clean(group.get("urlname")) or refs.urlname_of(group.get("link")) or refs.urlname_of(event_link)
    out = {"id": clean(group.get("id")), "name": clean(group.get("name")), "url_name": urlname,
           "link": refs.group_link(urlname), "timezone": clean(group.get("timezone"))}
    ratings = g(group, "stats", "eventRatings", default=None)
    if isinstance(ratings, dict):
        out["rating"] = _rating(ratings.get("average"))
        out["rating_count"] = _count(ratings.get("totalRatings") if "totalRatings" in ratings else ratings.get("total"))
    if "isNewGroup" in group:
        out["is_new"] = group.get("isNewGroup") if isinstance(group.get("isNewGroup"), bool) else None
    if "keyGroupPhoto" in group:
        out["photo"] = photo_link(group.get("keyGroupPhoto"))
    return out


def parse_event_row(node):
    """One event of a list (a search result, a group's event, a similar
    event) -> a row. A list's rows all carry the same keys: the ones its
    upstream call asks for."""
    node = as_dict(node)
    event_type = clean(node.get("eventType"))
    link = clean(node.get("eventUrl"))
    row = {"id": clean(node.get("id")), "title": clean(node.get("title")), "link": link,
           "description": _text(node.get("description"))}
    if "status" in node:
        row["status"] = _lower(node.get("status"))
    row["event_type"] = refs.EVENT_TYPE_NAMES.get(event_type, _lower(event_type))
    row["is_online"] = node.get("isOnline") if isinstance(node.get("isOnline"), bool) else (
        event_type == "ONLINE" if event_type else None)
    row["starts_at"] = _utc(node.get("dateTime"))
    if "endTime" in node:
        row["ends_at"] = _utc(node.get("endTime"))
    row["starts_at_local"] = _local_time(node.get("dateTime"))
    if "endTime" in node:
        row["ends_at_local"] = _local_time(node.get("endTime"))
    row["timezone"] = clean(g(node, "group", "timezone", default=None))
    if "createdTime" in node:
        row["created_at"] = _utc(node.get("createdTime"))
    if "going" in node:
        row["going_count"] = _total(node.get("going"))
    elif "rsvps" in node:
        row["going_count"] = _total(node.get("rsvps"))
    if "maxTickets" in node:
        row["max_attendees"] = _limit(node.get("maxTickets"))
    if "socialProofInsights" in node:
        insights = as_dict(node.get("socialProofInsights"))
        row["interested_count"] = _count(insights.get("totalInterestedUsers"))
        row["is_trending"] = insights.get("isTrendingEvent") if isinstance(insights.get("isTrendingEvent"), bool) else None
    if "rsvpState" in node:
        row["rsvp_state"] = _lower(node.get("rsvpState"))
    if "rsvpSettings" in node:
        closed = g(node, "rsvpSettings", "rsvpsClosed", default=None)
        row["is_rsvp_closed"] = closed if isinstance(closed, bool) else None
    if "isFeatured" in node:
        row["is_featured"] = node.get("isFeatured") if isinstance(node.get("isFeatured"), bool) else None
    if "isNetworkEvent" in node:
        row["is_network_event"] = node.get("isNetworkEvent") if isinstance(node.get("isNetworkEvent"), bool) else None
    row["is_free"] = not as_dict(node.get("feeSettings"))
    row["fee"] = _fee(node.get("feeSettings"))
    row["photo"] = photo_link(node.get("featuredEventPhoto")) or photo_link(node.get("displayPhoto"))
    row["venue"] = _venue(node.get("venue"), event_type)
    row["group"] = _row_group(node.get("group"), link)
    if "series" in node:
        row["series"] = _series(node.get("series"))
    return row


# ---- event lists -----------------------------------------------------------------------

def _connection(data, *names):
    for name in names:
        if isinstance(as_dict(data).get(name), dict):
            return data[name]
    return {}


def parse_event_list(data):
    """The answer of either find-page event list -> {events, has_next}.
    The site's own totalCount is only the size of the page, so no total is
    given."""
    connection = _connection(data, "results", "result")
    return {"events": [parse_event_row(node) for node in _edges(connection)],
            "has_next": bool(g(connection, "pageInfo", "hasNextPage", default=False))}


def parse_similar_events(data):
    """The "you may also like" events of an event page."""
    return [parse_event_row(node) for node in _edges(as_dict(data).get("similarEvents"))]


def parse_group_events(data):
    """One page of a group's events -> {events, total_count, next_cursor}
    (None when the group does not exist)."""
    group = as_dict(data).get("groupByUrlname")
    if not isinstance(group, dict):
        return None
    connection = as_dict(group.get("events"))
    info = as_dict(connection.get("pageInfo"))
    return {"group_id": clean(group.get("id")),
            "total_count": _total(connection),
            "next_cursor": clean(info.get("endCursor")) if info.get("hasNextPage") else None,
            "events": [parse_event_row(node) for node in _edges(connection)]}


# ---- an event page ---------------------------------------------------------------------

def _host(host):
    """An event host as the page prints it: the name with its last word cut
    to an initial ("Devon M."), and the photo."""
    host = as_dict(host)
    is_super = g(host, "member", "isSuperOrganizer", default=None)
    return {"name": refs.short_name(clean(host.get("name"))),
            "is_super_organizer": is_super if isinstance(is_super, bool) else None,
            "photo": photo_link(host.get("memberPhoto"), "member")}


def _page_group(group):
    """The group block of an event page."""
    group = as_dict(group)
    if not group:
        return None
    urlname = clean(group.get("urlname")) or refs.urlname_of(group.get("link"))
    network = as_dict(group.get("proNetwork"))
    sponsors = [{"name": clean(node.get("name")), "description": _text(node.get("description")),
                 "link": clean(node.get("url")), "logo": photo_link(node.get("logoPhoto"))}
                for node in _edges(group.get("sponsors"))]
    return {
        "id": clean(group.get("id")),
        "name": clean(group.get("name")),
        "url_name": urlname,
        "link": refs.group_link(urlname),
        "city": clean(group.get("city")),
        "state": clean(group.get("state")),
        "country": _upper(group.get("country")),
        "timezone": clean(group.get("timezone")),
        "is_private": group.get("isPrivate") if isinstance(group.get("isPrivate"), bool) else None,
        "join_mode": _lower(group.get("joinMode")),
        "status": _lower(group.get("status")),
        "member_count": _count(g(group, "stats", "memberCounts", "all", default=None)),
        "rating": None,
        "rating_count": None,
        "category": _category(group.get("topicCategory")),
        "topics": [_topic(node) for node in as_list(group.get("topics") or group.get("activeTopics"))],
        "pro_network": ({"id": clean(network.get("id")), "name": clean(network.get("name")),
                         "url_name": clean(network.get("urlname")), "link": clean(network.get("link"))}
                        if network else None),
        "sponsors": sponsors,
        "photo": photo_link(group.get("groupPhoto") or group.get("keyGroupPhoto")),
    }


def _role(rsvp):
    """An attendee's role as the page prints it under the name."""
    role = clean(g(rsvp, "membership", "role", default=None))
    if not as_dict(rsvp.get("membership")):
        return "former_member"
    if role == "ORGANIZER" and g(rsvp, "member", "isSuperOrganizer", default=False) is True:
        return "super_organizer"
    return {"COORGANIZER": "co_organizer"}.get(role, _lower(role))


def _attendee(rsvp, shown_as):
    """One attendee. On a card the page prints the whole name only when the
    answer marks the RSVP as unlocked, else the first word (the rest is
    blurred); a former member's card prints no name. A photo prints no name
    at all (only its image label carries the whole name), so an attendee
    shown as a photo comes back with the photo and no name, whether or not
    the RSVP is unlocked (the owner's decision, 2026-11-24)."""
    member = as_dict(rsvp.get("member"))
    card = shown_as != "photo"
    name = None
    if card:
        name = clean(member.get("name"))
        if rsvp.get("isRsvpUnlocked") is not True:
            name = refs.first_word(name)
        elif not as_dict(rsvp.get("membership")) and shown_as == "card":
            name = None
    return {
        "name": name,
        "role": _role(rsvp) if card else None,
        "is_host": (rsvp.get("isHost") if isinstance(rsvp.get("isHost"), bool) else None) if card else None,
        "guests_count": _count(rsvp.get("guestsCount")) if card else None,
        "photo": photo_link(member.get("memberPhoto"), "member"),
        "shown_as": shown_as,
    }


def page_order(rsvps):
    """The loaded attendees in the order the event page shows them: hosts
    first, then those with a photo, each group in reverse of the loaded
    order; one entry per member."""
    def rank(rsvp):
        return (rsvp.get("isHost") is True, bool(g(rsvp, "member", "memberPhoto", default=None)))
    ordered = sorted(rsvps, key=rank)       # stable, ascending, like the page's sortBy
    ordered.reverse()
    seen, unique = set(), []
    for rsvp in ordered:
        member_id = g(rsvp, "member", "id", default=None)
        if member_id is not None and member_id in seen:
            continue
        seen.add(member_id)
        unique.append(rsvp)
    return unique


def shown_attendees(attendees_data, every_loaded=False):
    """The attendees of an event page for a visitor who is not signed in:
    with more than four, three cards (name, role, host badge, guests) and
    the photos of the next three; with four or fewer, a card each.
    `every_loaded` answers every attendee the page loaded (20 at most), as
    cards."""
    rsvps = page_order(_edges(g(as_dict(attendees_data), "event", "rsvps", default=None)))
    if every_loaded:
        return [_attendee(rsvp, "loaded") for rsvp in rsvps]
    if len(rsvps) <= CARDS_SHOWN + 1:
        return [_attendee(rsvp, "card") for rsvp in rsvps]
    cards = [_attendee(rsvp, "card") for rsvp in rsvps[:CARDS_SHOWN]]
    photos = [_attendee(rsvp, "photo") for rsvp in rsvps[CARDS_SHOWN:CARDS_SHOWN + PHOTOS_SHOWN]]
    return cards + photos


def _attendee_count(attendees_data):
    """The number the page prints beside "Attendees"."""
    rsvps = as_dict(g(as_dict(attendees_data), "event", "rsvps", default=None))
    if not rsvps:
        return None
    going = rsvps.get("yesCount") if rsvps.get("yesCount") is not None else rsvps.get("totalCount")
    return (to_int(going) or 0) + (to_int(rsvps.get("noShowCount")) or 0) + (to_int(rsvps.get("absentCount")) or 0)


def page_event(next_data):
    """The event object an event page carries, or None."""
    event = g(as_dict(next_data), "props", "pageProps", "event", default=None)
    return event if isinstance(event, dict) and event.get("id") else None


def parse_event(next_data, extras=None, attendees=None, every_loaded_attendee=False):
    """An event page's data (+ the two calls the page makes after loading:
    `extras` = getEventHomeClientOnly, `attendees` =
    getEventByIdForAttendees) -> the event. None when the page carries no
    event."""
    event = page_event(next_data)
    if event is None:
        return None
    extra = as_dict(as_dict(extras).get("event"))
    event_type = clean(event.get("eventType"))
    link = clean(event.get("eventUrl"))
    chat = as_dict(event.get("externalChat"))
    speaker = as_dict(event.get("speakerDetails"))
    insights = as_dict(event.get("socialProofInsights"))
    covid = {key: clean(value) for key, value in as_dict(event.get("covidPrecautions")).items()
             if key != "__typename" and clean(value)}
    rsvp_settings = as_dict(event.get("rsvpSettings"))
    hosts = as_list(event.get("eventHosts") or event.get("hosts"))
    group = _page_group(event.get("group"))
    ratings = g(extra, "group", "stats", "eventRatings", default=None)
    if group and isinstance(ratings, dict):         # the page prints the group's rating from its second call
        group["rating"] = _rating(ratings.get("average"))
        group["rating_count"] = _count(ratings.get("totalRatings") if "totalRatings" in ratings else ratings.get("total"))
    return {
        "id": clean(event.get("id")),
        "token": clean(event.get("token")),
        "title": clean(event.get("title")),
        "link": link,
        "description": _text(event.get("description")),
        "status": _lower(event.get("status")),
        "time_status": _lower(event.get("timeStatus")),
        "event_type": refs.EVENT_TYPE_NAMES.get(event_type, _lower(event_type)),
        "is_online": event_type == "ONLINE" if event_type else None,
        "is_featured": event.get("isFeatured") if isinstance(event.get("isFeatured"), bool) else None,
        "is_network_event": event.get("isNetworkEvent") if isinstance(event.get("isNetworkEvent"), bool) else None,
        "starts_at": _utc(event.get("dateTime")),
        "ends_at": _utc(event.get("endTime")),
        "starts_at_local": _local_time(event.get("dateTime")),
        "ends_at_local": _local_time(event.get("endTime")),
        "timezone": clean(event.get("timezone")) or clean(g(event, "group", "timezone", default=None)),
        "going_count": _total(event.get("goingCount")) if "goingCount" in event else _total(extra.get("going")),
        "waitlist_count": _count(event.get("waiting")) if "waiting" in event else _total(event.get("waitingCount")),
        "attendee_count": _attendee_count(attendees),
        "interested_count": _count(insights.get("totalInterestedUsers")),
        "is_trending": insights.get("isTrendingEvent") if isinstance(insights.get("isTrendingEvent"), bool) else None,
        "max_attendees": _limit(event.get("maxTickets")),
        "waitlist_mode": _lower(event.get("waitlistMode")),
        "is_guests_allowed": event.get("guestsAllowed") if isinstance(event.get("guestsAllowed"), bool) else None,
        "max_guests_per_member": _limit(event.get("numberOfAllowedGuests")),
        "rsvp_opens_at": _utc(rsvp_settings.get("rsvpOpenTime")),
        "rsvp_closes_at": _utc(rsvp_settings.get("rsvpCloseTime")),
        "rsvp_state": _lower(extra.get("rsvpState")),
        "is_free": not as_dict(event.get("feeSettings")),
        "fee": _fee(event.get("feeSettings"), event.get("currency")),
        "has_event_chat": event.get("isEventChatEnabled") if isinstance(event.get("isEventChatEnabled"), bool) else None,
        "external_chat": ({"platform": _lower(chat.get("platform")), "link": clean(chat.get("url"))} if chat else None),
        "how_to_find_us": _text(extra.get("howToFindUs")),
        "komoot_link": clean(event.get("komootUrl")),
        "sponsored_until": _utc(event.get("sponsoredUntil")),
        "covid_precautions": covid or None,
        "photo": photo_link(event.get("featuredEventPhoto")) or photo_link(event.get("displayPhoto")),
        "venue": _venue(event.get("venue"), event_type),
        "series": _series(event.get("series"), with_dates=False),
        "speaker": ({"name": clean(speaker.get("name")), "description": _text(speaker.get("description")),
                     "photo": photo_link(speaker.get("photo"), "member"),
                     "social": _social(speaker.get("socialNetworks"))} if speaker else None),
        "hosts": [_host(host) for host in hosts if isinstance(host, dict)],
        "attendees": shown_attendees(attendees, every_loaded_attendee),
        "topics": [_topic(node) for node in _edges(event.get("topics"))],
        "group": group,
    }


# What an event page adds to the event's row in its group's public event
# list. An ENDED event's page sends a visitor who is not signed in to the
# login page (seen 2026-11-23), so these are sign-in-only for such an event.
ENDED_EVENT_PAGE_ONLY = ("token", "waitlist_count", "attendee_count", "waitlist_mode", "is_guests_allowed",
                         "max_guests_per_member", "rsvp_opens_at", "rsvp_closes_at", "rsvp_state",
                         "has_event_chat", "external_chat", "how_to_find_us", "komoot_link", "sponsored_until",
                         "covid_precautions", "speaker")
ENDED_EVENT_PAGE_ONLY_LISTS = ("hosts", "attendees", "topics")
ENDED_VENUE_PAGE_ONLY = ("lat", "lng", "google_maps_link")


def is_ended(next_data):
    """True for an event whose page a visitor must sign in to see: it has ended."""
    event = page_event(next_data) or {}
    return str(event.get("timeStatus") or "").upper() == "ENDED" or str(event.get("status") or "").upper() == "PAST"


def public_part_of_ended(event):
    """An ended event with what only its page shows set to null / empty:
    what is left is what the group's public list of past events shows."""
    event = dict(event)
    for key in ENDED_EVENT_PAGE_ONLY:
        event[key] = None
    for key in ENDED_EVENT_PAGE_ONLY_LISTS:
        event[key] = []
    if isinstance(event.get("venue"), dict):
        event["venue"] = {key: (None if key in ENDED_VENUE_PAGE_ONLY else value) for key, value in event["venue"].items()}
    return event


# ---- groups ----------------------------------------------------------------------------

def _social(networks):
    """[{service, identifier, url}] -> the ones that are filled in."""
    out = []
    for network in as_list(networks):
        network = as_dict(network)
        link = clean(network.get("url"))
        if link in ("http://", "https://"):
            link = None
        identifier = clean(network.get("identifier"))
        if not link and not identifier:
            continue
        out.append({"service": _lower(network.get("service")), "identifier": identifier, "link": link})
    return out


# Where a group's "other" link is a page on someone else's platform, not a site
# of its own. Read off the 1,110 such links of 4,005 groups (2026-11-23). The
# link stays in `social`. A site built on a host (*.wixsite.com, *.github.io, a
# Substack, Google Sites) is the group's own.
_PLATFORM_HOSTS = (
    "meetup.com", "meetu.ps",
    # social networks and video
    "facebook.com", "fb.com", "fb.me", "instagram.com", "twitter.com", "x.com", "threads.com", "threads.net",
    "linkedin.com", "lnkd.in", "tiktok.com", "pinterest.com", "reddit.com", "snapchat.com", "bsky.app",
    "mastodon.social", "nextdoor.com", "tumblr.com", "flickr.com", "vk.com", "strava.com", "goodreads.com",
    "ravelry.com", "chess.com", "github.com", "youtube.com", "youtu.be", "vimeo.com", "twitch.tv",
    # chat and community apps
    "discord.gg", "discord.com", "discordapp.com", "t.me", "telegram.me", "telegram.org", "whatsapp.com", "wa.me",
    "slack.com", "skool.com", "heylo.com", "heylo.group", "heartbeat.chat",
    # event and donation pages
    "eventbrite.com", "eventbrite.co.uk", "eventbrite.ca", "eventbrite.com.au", "eventbrite.de", "lu.ma", "luma.com",
    "partiful.com", "sessionize.com", "patreon.com", "ko-fi.com", "buymeacoffee.com", "givebutter.com", "gofundme.com",
    # link pages, short links, forms, sign-ups, app stores
    "linktr.ee", "bit.ly", "tinyurl.com", "rb.gy", "is.gd", "t.ly", "goo.gl", "aka.ms", "onelink.me", "forms.gle",
    "eepurl.com", "mailchi.mp", "google.com", "apps.apple.com",
)


def _is_platform_link(link):
    """True for a link to a page on someone else's platform (_PLATFORM_HOSTS)."""
    try:
        host = (urlparse(link).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return True
    if host == "sites.google.com":
        return False                        # a site built on Google Sites
    return any(host == domain or host.endswith("." + domain) for domain in _PLATFORM_HOSTS)


def _website(networks):
    """The group's own website: the link it filed under "other", unless that
    is a page on a social, chat or event platform (those stay in `social`)."""
    for network in as_list(networks):
        network = as_dict(network)
        link = clean(network.get("url")) or clean(network.get("identifier"))
        if clean(network.get("service")) == "OTHER" and link and re.match(r"^https?://[^/\s]+\.[^/\s]+", link):
            if not _is_platform_link(link):
                return link
    return None


def parse_group_row(node):
    """One group of a find-page list."""
    node = as_dict(node)
    urlname = clean(node.get("urlname")) or refs.urlname_of(node.get("link"))
    ratings = as_dict(g(node, "stats", "eventRatings", default=None))
    return {
        "id": clean(node.get("id")),
        "name": clean(node.get("name")),
        "url_name": urlname,
        "link": refs.group_link(urlname),
        "description": _text(node.get("description")),
        "city": clean(node.get("city")),
        "state": clean(node.get("state")),
        "country": _upper(node.get("country")),
        "member_count": _count(g(node, "stats", "memberCounts", "all", default=None)),
        "rating": _rating(ratings.get("average")),
        "rating_count": _count(ratings.get("totalRatings")),
        "is_private": node.get("isPrivate") if isinstance(node.get("isPrivate"), bool) else None,
        "is_new": node.get("isNewGroup") if isinstance(node.get("isNewGroup"), bool) else None,
        "status": _lower(node.get("status")),
        "photo": photo_link(node.get("groupPhoto") or node.get("keyGroupPhoto")),
    }


def parse_group_list(data):
    """The answer of either find-page group list -> {groups, has_next}."""
    connection = _connection(data, "results", "result")
    return {"groups": [parse_group_row(node) for node in _edges(connection)],
            "has_next": bool(g(connection, "pageInfo", "hasNextPage", default=False))}


def parse_group_rating(data):
    """The group page's rating summary (getGroupFeedbackInfo) -> the
    `rating` block, or None."""
    ratings = g(as_dict(data), "groupByUrlname", "stats", "eventRatings", default=None)
    if not isinstance(ratings, dict):
        return None
    details = as_dict(ratings.get("details"))

    def topics(rows):
        return [{"topic": _lower(row.get("topic")), "count": _count(row.get("count"))}
                for row in as_list(rows) if isinstance(row, dict)]
    return {
        "average": _rating(ratings.get("average")),
        "rating_count": _count(ratings.get("totalRatings") if "totalRatings" in ratings else ratings.get("total")),
        "review_count": _count(ratings.get("totalReviews")),
        "breakdown": [{"stars": to_int(row.get("rating")), "count": _count(row.get("count"))}
                      for row in as_list(ratings.get("breakdown")) if isinstance(row, dict)],
        "would_attend_again_count": _count(details.get("membersWouldAttendAgain")),
        "liked": topics(details.get("membersLiked")),
        "disliked": topics(details.get("membersDisliked")),
    }


def parse_group(data, rating_data=None):
    """A group page's data (groupHome, + getGroupFeedbackInfo for the rating
    summary) -> the group; None when the group does not exist."""
    group = as_dict(data).get("groupByUrlname")
    if not isinstance(group, dict):
        return None
    urlname = clean(group.get("urlname"))
    organizer = as_dict(group.get("organizer"))
    counts = as_dict(g(group, "stats", "memberCounts", default=None))
    ratings = as_dict(g(group, "stats", "eventRatings", default=None))
    rating = parse_group_rating(rating_data) or {
        "average": _rating(ratings.get("average")),
        "rating_count": _count(ratings.get("totalRatings") if "totalRatings" in ratings else ratings.get("total")),
        "review_count": None, "breakdown": [], "would_attend_again_count": None, "liked": [], "disliked": [],
    }
    video = as_dict(group.get("video"))
    network = as_dict(group.get("proNetwork"))
    dues = {_snake(key): value for key, value in as_dict(group.get("duesSettings")).items() if key != "__typename"}
    featured = group.get("featuredEvent")
    return {
        "id": clean(group.get("id")),
        "name": clean(group.get("name")),
        "url_name": urlname,
        "link": refs.group_link(urlname),
        "description": _text(group.get("description")),
        "city": clean(group.get("city")),
        "state": clean(group.get("state")),
        "country": _upper(group.get("country")),
        "lat": group.get("lat") if isinstance(group.get("lat"), (int, float)) else None,
        "lng": group.get("lon") if isinstance(group.get("lon"), (int, float)) else None,
        "timezone": clean(group.get("timezone")),
        "founded_at": _utc(group.get("foundedDate")),
        "is_private": group.get("isPrivate") if isinstance(group.get("isPrivate"), bool) else None,
        "join_mode": _lower(group.get("joinMode")),
        "is_photo_required_to_join": group.get("needsPhoto") if isinstance(group.get("needsPhoto"), bool) else None,
        "has_join_questions": group.get("needsQuestions") if isinstance(group.get("needsQuestions"), bool) else None,
        "status": _lower(group.get("status")),
        "website": _website(group.get("socialNetworks")),
        "social": _social(group.get("socialNetworks")),
        "member_count": _count(counts.get("all")),
        "leader_count": _count(counts.get("leadership")),
        "upcoming_event_count": _total(group.get("upcomingEvents")),
        "past_event_count": _total(group.get("pastEvents")),
        "rating": rating,
        "organizer": ({"name": clean(organizer.get("name")),
                       "is_super_organizer": (organizer.get("isSuperOrganizer")
                                              if isinstance(organizer.get("isSuperOrganizer"), bool) else None),
                       "photo": photo_link(organizer.get("memberPhoto"), "member")} if organizer else None),
        "category": _category(group.get("topicCategory")),
        "topics": [_topic(node) for node in as_list(group.get("activeTopics"))],
        "membership_dues": dues or None,
        # the group page's call asks for no `link` of the network: it is built from the url name
        "pro_network": ({"id": clean(network.get("id")), "name": clean(network.get("name")),
                         "url_name": clean(network.get("urlname")),
                         "link": clean(network.get("link")) or refs.pro_network_link(clean(network.get("urlname")))}
                        if network else None),
        "sponsors": [{"name": clean(node.get("name")), "description": _text(node.get("description")),
                      "link": clean(node.get("url")), "logo": photo_link(node.get("logoPhoto"))}
                     for node in _edges(group.get("sponsors"))],
        "video": ({"provider": _lower(video.get("provider")), "link": clean(video.get("url"))} if video else None),
        "photo": photo_link(group.get("groupPhoto") or group.get("keyGroupPhoto")),
        "featured_event": parse_event_row(featured) if isinstance(featured, dict) else None,
        "upcoming_events": [parse_event_row(node) for node in _edges(group.get("upcomingEvents"))],
        "past_events": [parse_event_row(node) for node in _edges(group.get("pastEvents"))],
    }


# ---- topics ----------------------------------------------------------------------------

def parse_topics_page(next_data):
    """The topic directory page -> its categories, each with its topics."""
    categories = []
    for category in as_list(g(as_dict(next_data), "props", "pageProps", "topicsCategories", default=None)):
        category = as_dict(category)
        name = clean(category.get("name"))
        known = refs.CATEGORY_BY_NAME.get(name, {})
        categories.append({"id": known.get("id"), "key": known.get("key"), "name": name,
                           "topics": [_topic(node) for node in as_list(category.get("topics"))]})
    return categories


def _topic_group(node):
    node = as_dict(node)
    urlname = clean(node.get("urlname"))
    row = {"id": clean(node.get("id")), "name": clean(node.get("name")), "url_name": urlname,
           "link": refs.group_link(urlname), "city": clean(node.get("city")), "state": clean(node.get("state")),
           "country": _upper(node.get("country")), "member_label": clean(node.get("customMemberLabel")),
           "member_count": _total(node.get("memberships")), "photo": photo_link(node.get("keyGroupPhoto"))}
    if "id" not in node:
        row.pop("id")
    return row


def parse_topic_page(next_data, stats_data=None):
    """A topic page (+ `stats_data` = getTopicStats, its worldwide counts) ->
    the topic; None when the page carries none. Without `stats_data` the
    counts are the page's own where it has them: its 0 means "not counted"
    for most topics, so that is null."""
    topic = g(as_dict(next_data), "props", "pageProps", "topic", default=None)
    if not isinstance(topic, dict) or not topic.get("urlkey"):
        return None
    key = clean(topic.get("urlkey"))
    stats = as_dict(g(as_dict(stats_data), "topicByUrlkey", "stats", default=None))
    if not stats:
        stats = {name: value for name, value in as_dict(topic.get("countryStats")).items() if value}
    related = []
    for node in _edges(topic.get("relatedTopics")):
        related_key = clean(node.get("urlkey"))
        related.append({"name": clean(node.get("name")), "key": related_key, "link": refs.topic_link(related_key)})
    return {
        "id": clean(topic.get("id")),
        "name": clean(topic.get("name")),
        "key": key,
        "link": refs.topic_link(key),
        "description": _text(topic.get("description")),
        "group_count": _count(stats.get("groupCount")),
        "member_count": _count(stats.get("memberCount")),
        "related_topics": related,
        "largest_groups": [_topic_group(node) for node in _edges(topic.get("largestGroup"))],
        "newest_groups": [_topic_group(node) for node in _edges(topic.get("newestGroup"))],
    }


def parse_topic_groups(data):
    """A topic's groups (getAllTopicGroupsByUrlkey) -> {topic_id, groups,
    has_more}; None when the topic does not exist. One row per group: the
    site repeats a group now and then."""
    topic = as_dict(data).get("topicByUrlkey")
    if not isinstance(topic, dict):
        return None
    seen, groups = set(), []
    for node in _edges(topic.get("groups")):
        urlname = clean(node.get("urlname"))
        if not urlname or urlname.lower() in seen:
            continue
        seen.add(urlname.lower())
        groups.append({"name": clean(node.get("name")), "url_name": urlname, "link": refs.group_link(urlname),
                       "city": clean(node.get("city")), "state": clean(node.get("state")),
                       "country": _upper(node.get("country"))})
    return {"topic_id": clean(topic.get("id")), "groups": groups,
            "has_more": bool(g(topic, "groups", "pageInfo", "hasNextPage", default=False))}


def parse_topic_suggestions(data):
    return [_topic(node) for node in _edges(as_dict(data).get("suggestTopics"))]


# ---- locations -------------------------------------------------------------------------

def first_place(data):
    """The first place of the place search's answer, as the site sent it
    (the search calls take its fields unchanged), or None."""
    for place in as_list(as_dict(data).get("result")):
        if isinstance(place, dict) and isinstance(place.get("lat"), (int, float)):
            return {key: value for key, value in place.items() if key != "__typename"}
    return None


def parse_locations(data):
    """The place search's answer -> places. Outside the countries with
    postcodes in the site's index, the site writes a placeholder
    ("meetup1") where the postcode goes: that is None here."""
    places = []
    for place in as_list(as_dict(data).get("result")):
        if not isinstance(place, dict):
            continue
        zip_code = clean(place.get("zip"))
        lat, lng = place.get("lat"), place.get("lon")
        places.append({
            "name": clean(place.get("name")),
            "city": clean(place.get("city")),
            "borough": clean(place.get("borough")),
            "neighborhood": clean(place.get("neighborhood")),
            "state": clean(place.get("state")),
            "country": _upper(place.get("country")),
            "postal_code": None if zip_code and _FAKE_ZIP_RE.match(zip_code) else zip_code,
            "lat": round(lat, 5) if isinstance(lat, (int, float)) else None,
            "lng": round(lng, 5) if isinstance(lng, (int, float)) else None,
            "timezone": clean(place.get("timeZone")),
        })
    return places
