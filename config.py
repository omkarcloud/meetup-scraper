"""Configuration for the Meetup Scraper. Everything can be set with an environment
variable; the defaults work out of the box.

    PORT           port the API listens on (default 8000)
    MEETUP_PROXY   proxy URL for every request, e.g. http://user:pass@host:port
                   (default: none. Meetup answers your own connection, so you
                   don't need one)

Everything else below is a plain constant with a working default.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

MEETUP_PROXY = os.environ.get("MEETUP_PROXY") or None


# ---- what the code reads off config: defaults for a direct run ----
MAX_RETRIES = 3
MEETUP_ALL_LOADED_ATTENDEES = False
MEETUP_ENDED_EVENT_PAGES = False
MEETUP_EXIT = MEETUP_PROXY      # the exit every session leaves through: your proxy, or direct
RETRY_BACKOFF = 2
