"""Reference resolvers, link builders and the choice tables for /meetup/*.

ONE param per input: `event` accepts an event id OR an event link; `group`
a group's url name OR a group link; `topic` a topic's url key OR a topic
link; `location` a place as text OR "lat,lng". Resolvers raise ValueError
with a user-facing message (RefField turns it into a 400).

Identifier shapes (www.meetup.com, 2026-11-21):
  * event   digits (317383946) once the event exists; a date of a
            recurring series that has not been created yet has a letter
            id (sfnhctykccbqb), which the site accepts in the same place.
            The link is /<group url name>/events/<id>/; the group part is
            not checked (a wrong one redirects to the right one), so the
            id alone finds the event.
  * group   its url name, the first segment of its link
            (https://www.meetup.com/nycpython/). Case-insensitive
            upstream. The numeric group id is NOT accepted by the page's
            calls.
  * topic   its url key (python), the segment after /topics/.
            Case-insensitive upstream.
A link may carry a locale as its first segment (/en-AU/nycpython/).
"""
import re
from urllib.parse import quote, unquote, urlparse

SITE = "https://www.meetup.com"
HOSTS = ("meetup.com",)

EVENT_ID_RE = re.compile(r"^(?:[0-9]{1,12}|[a-z]{6,20})$")
GROUP_URLNAME_RE = re.compile(r"^[\w][\w.-]{0,99}$")
TOPIC_URLKEY_RE = re.compile(r"^[\w][\w.-]{0,99}$")
_LOCALE_RE = re.compile(r"^[a-z]{2}(?:-[A-Za-z]{2})?$")

# first path segments of the site that are not a group's url name
RESERVED_SEGMENTS = frozenset((
    "find", "topics", "cities", "pro", "members", "lp", "blog", "apps", "about", "help", "login", "register",
    "home", "api", "meetup_api", "account", "messages", "notifications", "your-events", "groups", "events",
    "start", "create", "careers", "media", "sitemap", "privacy", "terms", "cookie-policy", "subscription",
    "dues", "gql", "gql2", "graphql", "intl", "orion", "files", "fb", "preview", "n", "ics", "images",
    "refresh-token", "logout", "onboarding", "payment", "checkout", "legal", "community", "online",
))

_EVENT_HELP = ("Must be a Meetup event id (317383946) or an event link "
               "(https://www.meetup.com/<group>/events/317383946/).")
_GROUP_HELP = "Must be a Meetup group's url name (nycpython) or a group link (https://www.meetup.com/nycpython/)."
_TOPIC_HELP = "Must be a Meetup topic's url key (python) or a topic link (https://www.meetup.com/topics/python/)."

MAX_LOCATION_LENGTH = 100

# ---- the site's own filter values (its find page, 2026-11-21) --------------------------

# The find page's category filter: 20 categories. The page sends the id as
# `topicCategoryId` (the `categoryId` variable answers no rows).
CATEGORIES = (
    ("art-culture", "521", "Art & Culture"),
    ("career-business", "405", "Career & Business"),
    ("community-environment", "604", "Community & Environment"),
    ("dancing", "612", "Dancing"),
    ("games", "535", "Games"),
    ("health-wellbeing", "511", "Health & Wellbeing"),
    ("hobbies-passions", "571", "Hobbies & Passions"),
    ("identity-language", "622", "Identity & Language"),
    ("movements-politics", "642", "Movements & Politics"),
    ("music", "395", "Music"),
    ("parents-family", "673", "Parents & Family"),
    ("pets-animals", "701", "Pets & Animals"),
    ("religion-spirituality", "593", "Religion & Spirituality"),
    ("science-education", "436", "Science & Education"),
    ("social-activities", "652", "Social Activities"),
    ("sports-fitness", "482", "Sports & Fitness"),
    ("support-coaching", "449", "Support & Coaching"),
    ("technology", "546", "Technology"),
    ("travel-outdoor", "684", "Travel & Outdoor"),
    ("writing", "467", "Writing"),
)
CATEGORY_IDS = {slug: cid for slug, cid, _ in CATEGORIES}
CATEGORY_BY_ID = {cid: {"id": cid, "key": slug, "name": name} for slug, cid, name in CATEGORIES}
CATEGORY_BY_NAME = {name: {"id": cid, "key": slug, "name": name} for slug, cid, name in CATEGORIES}

# public value -> the EventType the page sends
EVENT_TYPES = {"in_person": "PHYSICAL", "online": "ONLINE", "hybrid": "HYBRID"}
EVENT_TYPE_NAMES = {token: name for name, token in EVENT_TYPES.items()}

# public value -> the sort field the page sends (both event lists)
EVENT_SORTS = {"relevance": "RELEVANCE", "date": "DATETIME"}

# the find page's "day" filter
DATE_RANGES = ("starting_soon", "today", "tomorrow", "this_week", "this_weekend", "next_week", "next_weekend")

# the find page's "distance" filter, in miles (the search radius)
DISTANCES = (2, 5, 10, 25, 50, 100)

# the find page's "size" filter -> the RsvpCountRange it sends
ATTENDEES = {
    "1-9": {"min": 1, "max": 9},
    "10-20": {"min": 10, "max": 20},
    "20-50": {"min": 20, "max": 50},
    "50-100": {"min": 50, "max": 100},
    "over-100": {"min": 100},
}

GROUP_EVENT_STATUSES = ("upcoming", "past")


# ---- links ---------------------------------------------------------------------------

def group_link(urlname):
    return f"{SITE}/{quote(str(urlname), safe='-_.~')}/" if urlname else None


def event_link(urlname, event_id):
    return f"{SITE}/{quote(str(urlname), safe='-_.~')}/events/{event_id}/" if urlname and event_id else None


def topic_link(urlkey):
    return f"{SITE}/topics/{quote(str(urlkey), safe='-_.~')}/" if urlkey else None


# every printable ASCII character but the space: a link keeps these as they are
_PRINTABLE_ASCII = "".join(chr(code) for code in range(0x21, 0x7F))


def ascii_link(link):
    """A link as a browser sends it in a header: each character outside
    printable ASCII percent-encoded as UTF-8 (a header carries ASCII only),
    the rest, `%` escapes included, as it is."""
    return quote(str(link), safe=_PRINTABLE_ASCII) if link else None


def pro_network_link(urlname):
    """A Pro network's page, as the event pages' own data writes it."""
    return f"{SITE}/pro/{quote(str(urlname), safe='-_.~')}/" if urlname else None


def member_link(member_id):
    return f"{SITE}/members/{member_id}/" if member_id else None


def find_link(source, keywords=None, location=None):
    """The find page a search call is sent from (its Referer)."""
    parts = []
    if keywords:
        parts.append("keywords=" + quote(keywords, safe=""))
    if location:
        parts.append("location=" + quote(location, safe="-"))
    parts.append("source=" + source)
    return f"{SITE}/find/?" + "&".join(parts)


def urlname_of(link):
    """A group or event link -> the group's url name; None for anything else."""
    try:
        segments = _segments(_site_path(str(link or "")) or "")
    except ValueError:
        return None
    if segments and segments[0].lower() not in RESERVED_SEGMENTS and GROUP_URLNAME_RE.match(segments[0]):
        return segments[0]
    return None


# ---- resolvers -----------------------------------------------------------------------

def _site_path(value):
    """The path of a meetup.com link (None when the value is not a link); a
    link to another host raises ValueError."""
    if not value.startswith(("http://", "https://", "//", "www.meetup.com/", "meetup.com/")):
        return None
    url = value
    if url.startswith("//"):
        url = "https:" + url
    elif not url.startswith("http"):
        url = "https://" + url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not any(host == h or host.endswith("." + h) for h in HOSTS):
        raise ValueError("Must be a meetup.com link.")
    return unquote(parsed.path or "/")


def _segments(path):
    """Path segments, without a leading locale (/en-AU/nycpython/ -> [nycpython])."""
    segments = [s for s in path.split("/") if s]
    if len(segments) > 1 and _LOCALE_RE.match(segments[0]) and segments[0].lower() not in RESERVED_SEGMENTS:
        segments = segments[1:]
    return segments


def resolve_event(value):
    """Event id or event link -> the event id."""
    value = (value or "").strip()
    path = _site_path(value)
    if path is not None:
        segments = _segments(path)
        if len(segments) >= 3 and segments[1] == "events" and EVENT_ID_RE.match(segments[2]):
            return segments[2]
        raise ValueError(_EVENT_HELP)
    if EVENT_ID_RE.match(value):
        return value
    raise ValueError(_EVENT_HELP)


def resolve_group(value):
    """Group url name or group link -> the url name, as given."""
    value = (value or "").strip()
    path = _site_path(value)
    if path is not None:
        segments = _segments(path)
        if segments and segments[0].lower() not in RESERVED_SEGMENTS and GROUP_URLNAME_RE.match(segments[0]):
            return segments[0]
        raise ValueError(_GROUP_HELP)
    if GROUP_URLNAME_RE.match(value) and value.lower() not in RESERVED_SEGMENTS:
        return value
    raise ValueError(_GROUP_HELP)


def resolve_topic(value):
    """Topic url key or topic link -> the url key, lower-cased."""
    value = (value or "").strip()
    path = _site_path(value)
    if path is not None:
        segments = _segments(path)
        if len(segments) >= 2 and segments[0] == "topics" and TOPIC_URLKEY_RE.match(segments[1]):
            return segments[1].lower()
        raise ValueError(_TOPIC_HELP)
    if TOPIC_URLKEY_RE.match(value):
        return value.lower()
    raise ValueError(_TOPIC_HELP)


def resolve_location(value):
    """'40.75,-73.99' -> {"lat", "lng"}; anything else -> {"query"} (a city,
    a US zip code, "London gb": the site's own place search resolves it)."""
    value = (value or "").strip()
    if len(value) > MAX_LOCATION_LENGTH:
        raise ValueError(f"Longer than maximum length {MAX_LOCATION_LENGTH}.")
    parts = [p.strip() for p in value.split(",")]
    if len(parts) == 2:
        try:
            lat, lng = float(parts[0]), float(parts[1])
        except ValueError:
            lat = lng = None
        if lat is not None:
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                raise ValueError("Latitude must be -90..90 and longitude -180..180.")
            return {"lat": lat, "lng": lng}
    if not re.search(r"\w", value):
        raise ValueError("Must be a place (New York, 10001, London gb) or lat,lng (40.75,-73.99).")
    return {"query": value}


# ---- names as the site prints them -----------------------------------------------------

def short_name(name):
    """A member's name as the site prints it for visitors: the last word cut
    to its initial ("Devon McCormick" -> "Devon M."); one word stays."""
    if not name:
        return None
    words = str(name).split(" ")
    if len(words) > 1:
        words[-1] = words[-1][:1] + "."
    return " ".join(words).strip() or None


def first_word(name):
    """What a visitor reads of a locked attendee's name: the page prints the
    first word and blurs the rest."""
    if not name:
        return None
    return str(name).split(" ", 1)[0].strip() or None
