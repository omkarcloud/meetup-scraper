"""The time windows of the find page's "day" filter, on the clock of the
place searched. Pure functions.

What the site's own page sends for each choice (read from its pages on
2026-11-21, a Saturday, for New York):

  any day        from now, no end
  starting_soon  from now, no end, plus the site's own "starting soon" flag
  today          now                     -> today 23:59:59
  tomorrow       tomorrow 00:00:00       -> tomorrow 23:59:59
  this_week      now                     -> Saturday 23:59:59 (a week runs Sunday to Saturday)
  this_weekend   Friday 16:59:59, or now once the weekend has begun
                                         -> Sunday 23:59:59
  next_week      next Sunday 00:00:00    -> the Sunday after, 23:59:59
  next_weekend   next week's Friday 16:59:59 -> its Sunday 23:59:59

A custom range runs from the first day 00:00:00 (or from now, when that
day is today or earlier) to the last day 23:59:59. Times are written as
the page writes them: local time with its UTC offset.
"""
from datetime import datetime, time, timedelta, timezone

WEEKEND_STARTS = time(16, 59, 59)       # Friday, as the page sends it
DAY_ENDS = time(23, 59, 59)

# The site's place records keep old zone names, and a slim image has only the
# current ones (Debian 13 moved the old ones to tzdata-legacy: ZoneInfo refuses
# "US/Eastern" there). So an old name is looked up by its current name. These are
# the US and Canada families whole and every other old name the place search
# answered for 189 cities (2026-11-23).
OLD_ZONE_NAMES = {
    "US/Alaska": "America/Anchorage", "US/Aleutian": "America/Adak", "US/Arizona": "America/Phoenix",
    "US/Central": "America/Chicago", "US/East-Indiana": "America/Indiana/Indianapolis",
    "US/Eastern": "America/New_York", "US/Hawaii": "Pacific/Honolulu", "US/Indiana-Starke": "America/Indiana/Knox",
    "US/Michigan": "America/Detroit", "US/Mountain": "America/Denver", "US/Pacific": "America/Los_Angeles",
    "US/Samoa": "Pacific/Pago_Pago",
    "Canada/Atlantic": "America/Halifax", "Canada/Central": "America/Winnipeg", "Canada/Eastern": "America/Toronto",
    "Canada/Mountain": "America/Edmonton", "Canada/Newfoundland": "America/St_Johns",
    "Canada/Pacific": "America/Vancouver", "Canada/Saskatchewan": "America/Regina", "Canada/Yukon": "America/Whitehorse",
    "Asia/Calcutta": "Asia/Kolkata", "Asia/Katmandu": "Asia/Kathmandu", "Asia/Macao": "Asia/Macau",
    "Asia/Rangoon": "Asia/Yangon", "Asia/Saigon": "Asia/Ho_Chi_Minh", "Africa/Asmera": "Africa/Asmara",
    "America/Buenos_Aires": "America/Argentina/Buenos_Aires", "America/Cordoba": "America/Argentina/Cordoba",
    "America/Mendoza": "America/Argentina/Mendoza", "Europe/Kiev": "Europe/Kyiv", "Pacific/Ponape": "Pacific/Pohnpei",
}


def zone_of(name):
    """An IANA zone by the name the site gives ("US/Eastern"), old names
    included; UTC for a missing or unknown one (an unknown one is logged:
    the day filters then run on the UTC clock)."""
    if name:
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(OLD_ZONE_NAMES.get(str(name), str(name)))
        except Exception:
            print(f"meetup: unknown time zone {name!r}: the day filters run on UTC")
    return timezone.utc


def stamp(moment):
    """2026-11-22T00:00:00-05:00"""
    text = moment.replace(microsecond=0).isoformat()
    return text[:-6] + "+00:00" if text.endswith("+00:00") or moment.utcoffset() is None else text


def _at(day, clock, zone):
    return datetime.combine(day, clock, tzinfo=zone)


def _weekend_friday(day):
    """The Friday of the weekend `day` belongs to or looks forward to."""
    weekday = day.weekday()             # Monday = 0 ... Sunday = 6
    if weekday >= 4:
        return day - timedelta(days=weekday - 4)
    return day + timedelta(days=4 - weekday)


def _week_saturday(day):
    """The Saturday that ends the Sunday-to-Saturday week of `day`."""
    return day + timedelta(days=(5 - day.weekday()) % 7)


def window(date_range=None, start_date=None, end_date=None, zone_name=None, now=None):
    """-> (start, end, is_starting_soon): the two time texts the search call
    takes (end may be None) and whether the site's "starting soon" flag
    goes with them. `now` is an aware datetime (tests)."""
    zone = zone_of(zone_name)
    now = (now or datetime.now(timezone.utc)).astimezone(zone)
    today = now.date()
    start, end, soon = now, None, False
    if date_range == "starting_soon":
        soon = True
    elif date_range == "today":
        end = _at(today, DAY_ENDS, zone)
    elif date_range == "tomorrow":
        day = today + timedelta(days=1)
        start, end = _at(day, time.min, zone), _at(day, DAY_ENDS, zone)
    elif date_range == "this_week":
        end = _at(_week_saturday(today), DAY_ENDS, zone)
    elif date_range == "this_weekend":
        friday = _weekend_friday(today)
        start = max(now, _at(friday, WEEKEND_STARTS, zone))
        end = _at(friday + timedelta(days=2), DAY_ENDS, zone)
    elif date_range == "next_week":
        sunday = _week_saturday(today) + timedelta(days=1)
        start, end = _at(sunday, time.min, zone), _at(sunday + timedelta(days=7), DAY_ENDS, zone)
    elif date_range == "next_weekend":
        friday = _weekend_friday(today) + timedelta(days=7)
        start, end = _at(friday, WEEKEND_STARTS, zone), _at(friday + timedelta(days=2), DAY_ENDS, zone)
    elif start_date or end_date:
        if start_date:
            start = max(now, _at(datetime.strptime(start_date, "%Y-%m-%d").date(), time.min, zone))
        if end_date:
            end = _at(datetime.strptime(end_date, "%Y-%m-%d").date(), DAY_ENDS, zone)
    return stamp(start), (stamp(end) if end else None), soon


def day_bound(date_text, zone_name, end=False):
    """A YYYY-MM-DD day -> the UTC instant it starts (or ends) on the clock
    of `zone_name`, as the group events call takes it: 2026-12-01T05:00:00.000Z"""
    zone = zone_of(zone_name)
    moment = _at(datetime.strptime(date_text, "%Y-%m-%d").date(), DAY_ENDS if end else time.min, zone)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def now_utc(now=None):
    """Now, as the group events page sends it: 2026-11-21T11:26:47.258Z"""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
