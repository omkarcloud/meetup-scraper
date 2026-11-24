# 🚀 Meetup Scraper

Meetup Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Meetup data for free.

## ✨ What Can I Get?

- 📅 **Full details of 100K+ events a week** — time, venue with map link, fee, RSVP and waitlist counts, hosts, attendees & topics
- 👥 **Profiles of 300K+ groups with 52M+ members** — member count, star rating with breakdown, organizer, website, socials, next & past events
- 🌍 **Search in 193 countries and 10,000 cities** — keywords, date range, distance, category, event type and event size
- 🏷️ **936 popular topics in 20 categories** — worldwide group and member counts, related topics, largest and newest groups

## 📅 Example: A Full Meetup Event

```json
{
  "id": "317486502",
  "title": "Stripe Developer Meetup Seattle January 2027",
  "link": "https://www.meetup.com/stripe-seattle/events/317486502/",
  "status": "active",
  "event_type": "in_person",
  "starts_at": "2027-01-13T02:00:00Z",
  "ends_at": "2027-01-13T04:00:00Z",
  "starts_at_local": "2027-01-12T18:00:00-08:00",
  "timezone": "America/Los_Angeles",
  "going_count": 14,
  "waitlist_count": 0,
  "max_attendees": 200,
  "is_free": true,
  "venue": { "name": "Seattle", "address": "920 5th Ave #150, Seattle, WA 98104, United States", "city": "Seattle", "state": "WA", "country": "US", "lat": 47.606655, "lng": -122.33125 },
  "hosts": [{ "name": "Ben", "is_super_organizer": true }],
  "attendees": [
    { "name": "Ben", "role": "super_organizer", "is_host": true },
    { "name": "Chris", "role": "member", "is_host": false }
  ],
  "topics": [{ "name": "FinTech", "key": "fintech" }, { "name": "Cloud Services", "key": "cloud-services" }],
  "group": { "name": "Stripe Seattle", "link": "https://www.meetup.com/stripe-seattle/", "member_count": 413, "rating": 4.61, "pro_network": { "name": "Stripe meetups" } }
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Meetup Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/meetup-scraper
cd meetup-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

Meetup answers your own connection, so you don't need a proxy.

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/events/details?event=317486502"
```

```json
{
  "id": "317486502",
  "title": "Stripe Developer Meetup Seattle January 2027",
  "link": "https://www.meetup.com/stripe-seattle/events/317486502/",
  "status": "active",
  "event_type": "in_person",
  "starts_at": "2027-01-13T02:00:00Z",
  "starts_at_local": "2027-01-12T18:00:00-08:00",
  "timezone": "America/Los_Angeles",
  "going_count": 14,
  "max_attendees": 200,
  "is_free": true,
  "venue": { "name": "Seattle", "address": "920 5th Ave #150, Seattle, WA 98104, United States", "lat": 47.606655, "lng": -122.33125 },
  "hosts": [{ "name": "Ben", "is_super_organizer": true }],
  "topics": [{ "name": "FinTech", "key": "fintech" }],
  "group": { "name": "Stripe Seattle", "member_count": 413, "rating": 4.61 }
}
```

All 11 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

11 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Event Details | `/events/details` | The whole event in one call: time, venue, fee, RSVPs, hosts, attendees |
| Search Events | `/events/search` | Events near any place, with keyword, date, distance and category filters |
| Similar Events | `/events/similar` | Up to 10 events like this one |
| Group Details | `/groups/details` | Members, rating, organizer, website, socials, topics (website contacts: hosted API only) |
| Search Groups | `/groups/search` | Groups near any place, by keyword, distance and category |
| Group Events | `/groups/events` | A group's upcoming and past events, with title and date filters |
| Topic Details | `/topics/details` | Worldwide counts, related topics, largest and newest groups |
| Topic Groups | `/topics/groups` | A topic's groups worldwide, 200 per page |
| Topic Suggestions | `/topics/suggestions` | Topic keys from a few typed letters |
| Topics | `/topics/list` | 20 categories with their popular topics |
| Location Suggestions | `/locations/suggestions` | Places with coordinates and time zone |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-meetup-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-meetup-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-meetup-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/events/details",
    params={"event": "317486502"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Meetup Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://www.omkar.cloud/l/meetup-scraper-github-whatsapp)

[![Ask Us by Email about Meetup Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Meetup%20Scraper%20API&body=I%20need%20help%20using%20the%20Meetup%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/meetup-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/meetup-scraper)
