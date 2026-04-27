"""
Web-Search Test Scenarios — 50 production-grade scenarios for the web-search
skill that lives at moltbot-gateway/skills/web-search/SKILL.md.

This file is intentionally SEPARATE from scenarios.py (calendar/reminders/email,
193 cases). It is run by run_web_search_tests.py and saves results to
results/web_search_results.json. The two suites do not share state.

Test user defaults to usr_9aadeaf0 (city: "Pune, India") — the only user
currently configured with a city in tbl_clawdbot_users at the time of writing.
Override via the WEB_SEARCH_USER_ID env var.

Verification types (richer than the response_only checks in scenarios.py):
  V_SEARCH    — query MUST trigger search; reply must be grounded (cites URL,
                contains specific facts) AND must NOT contain a knowledge-cutoff
                disclaimer.
  V_NEARME    — V_SEARCH + reply must reference the user's city or a local
                landmark (Koregaon Park, FC Road, Aundh, Hinjewadi, etc. for
                Pune).
  V_NO_SEARCH — query SHOULD NOT trigger search; reply should not cite a URL.
                Latency is captured as a soft signal but does not gate the
                verdict (cache state varies).
  V_RESPONSE  — fallback for things we cannot mechanically grade beyond a
                non-empty 200 response.

The categories below reflect the realistic shape of senior-tester traffic on
an Indian, Pune-based playground user. There is no padding — every case here
is something an actual user could plausibly type into Peppi.
"""

import os

API_URL = "https://moltbot-fastapi.onrender.com/api/v1"
USER_ID = os.environ.get("WEB_SEARCH_USER_ID", "usr_9aadeaf0")
DEFAULT_TZ = os.environ.get("WEB_SEARCH_TZ", "Asia/Kolkata")
# Used by the V_NEARME verifier for primary-city detection. Read from env so
# this file does not need editing if you want to test with a different city.
USER_CITY = os.environ.get("WEB_SEARCH_USER_CITY", "Pune, India")

# Verification types
V_SEARCH = "search_grounded"      # Reply must cite + be grounded
V_NEARME = "near_me_localized"    # Reply must reference USER_CITY context
V_NO_SEARCH = "no_search"         # Reply should NOT cite a URL
V_RESPONSE = "response_only"      # Non-empty 200

SCENARIOS = []

# ============================================================
# A. CURRENT EVENTS & NEWS (8)
#    Post-cutoff data; tests the agent's recency triggering.
# ============================================================
SCENARIOS += [
    {"id": "WSA1",  "cat": "Current Events", "name": "Indian politics this week",
     "msg": "what happened in indian politics this week",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSA2",  "cat": "Current Events", "name": "Monsoon arrival in Maharashtra",
     "msg": "any latest update on monsoon arrival in maharashtra",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSA3",  "cat": "Current Events", "name": "Major Indian tech layoffs",
     "msg": "have there been any major tech layoffs in indian companies recently",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSA4",  "cat": "Current Events", "name": "RBI announcement this week",
     "msg": "what did the RBI announce this week, anything on rates?",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSA5",  "cat": "Current Events", "name": "ISRO mission update",
     "msg": "what's the latest on chandrayaan or any ISRO mission",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSA6",  "cat": "Current Events", "name": "Anthropic / OpenAI releases",
     "msg": "any major releases from anthropic or openai this week",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSA7",  "cat": "Current Events", "name": "India-US trade talks",
     "msg": "what's the status of india us trade talks right now",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSA8",  "cat": "Current Events", "name": "Top 3 international headlines",
     "msg": "give me the top 3 international news headlines today, briefly",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
]

# ============================================================
# B. LIVE MARKET DATA (7)
#    Prices change by the second; reply must include a numeric figure.
# ============================================================
SCENARIOS += [
    {"id": "WSB1",  "cat": "Live Market", "name": "Bitcoin price in INR",
     "msg": "what is the current price of bitcoin in INR",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSB2",  "cat": "Live Market", "name": "Sensex / Nifty closing",
     "msg": "where did sensex and nifty close today",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSB3",  "cat": "Live Market", "name": "Gold rate in Pune (10g)",
     "msg": "gold rate in pune today per 10 gram",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSB4",  "cat": "Live Market", "name": "Petrol price in Pune",
     "msg": "petrol price in pune today, per litre",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSB5",  "cat": "Live Market", "name": "USD-INR rate today",
     "msg": "usd to inr exchange rate today",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSB6",  "cat": "Live Market", "name": "Reliance share price",
     "msg": "reliance industries share price right now",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSB7",  "cat": "Live Market", "name": "TCS vs Infosys today",
     "msg": "tcs vs infosys stock price comparison today",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
]

# ============================================================
# C. HYPERLOCAL "NEAR ME" — USER_CITY=Pune (12)
#    Verifies $USER_CITY plumbing end-to-end. Reply must reference Pune,
#    a Pune neighborhood, or local detail that proves the search was
#    location-aware.
# ============================================================
SCENARIOS += [
    {"id": "WSC1",  "cat": "Near Me",    "name": "Best vada pav near me",
     "msg": "best vada pav near me right now",
     "tz": DEFAULT_TZ, "verify": V_NEARME},
    {"id": "WSC2",  "cat": "Near Me",    "name": "South Indian breakfast nearby",
     "msg": "where can I get authentic south indian breakfast nearby",
     "tz": DEFAULT_TZ, "verify": V_NEARME},
    {"id": "WSC3",  "cat": "Near Me",    "name": "Gym under 2k near me",
     "msg": "good gym with monthly pass under 2000 near me",
     "tz": DEFAULT_TZ, "verify": V_NEARME},
    {"id": "WSC4",  "cat": "Near Me",    "name": "24h pharmacy near me",
     "msg": "24 hour pharmacy near me",
     "tz": DEFAULT_TZ, "verify": V_NEARME},
    {"id": "WSC5",  "cat": "Near Me",    "name": "Biryani in Koregaon Park",
     "msg": "best biryani places in koregaon park",
     "tz": DEFAULT_TZ, "verify": V_NEARME},
    {"id": "WSC6",  "cat": "Near Me",    "name": "Classical music concerts this weekend",
     "msg": "any indian classical music concerts in pune this weekend",
     "tz": DEFAULT_TZ, "verify": V_NEARME},
    {"id": "WSC7",  "cat": "Near Me",    "name": "Tamil movies near me",
     "msg": "movie theatres in my area playing the latest tamil movies",
     "tz": DEFAULT_TZ, "verify": V_NEARME},
    {"id": "WSC8",  "cat": "Near Me",    "name": "Auto fare FC Road to Hinjewadi",
     "msg": "roughly what is the auto fare from FC road to hinjewadi",
     "tz": DEFAULT_TZ, "verify": V_NEARME},
    {"id": "WSC9",  "cat": "Near Me",    "name": "Veg restaurants with parking",
     "msg": "good vegetarian restaurants near me with parking",
     "tz": DEFAULT_TZ, "verify": V_NEARME},
    {"id": "WSC10", "cat": "Near Me",    "name": "Farmers/organic market nearby",
     "msg": "any farmers market or organic produce store nearby",
     "tz": DEFAULT_TZ, "verify": V_NEARME},
    {"id": "WSC11", "cat": "Near Me",    "name": "Weekend treks from Pune",
     "msg": "weekend trekking groups or hikes from pune",
     "tz": DEFAULT_TZ, "verify": V_NEARME},
    {"id": "WSC12", "cat": "Near Me",    "name": "Dentists in Aundh/Baner",
     "msg": "good dentists in aundh or baner",
     "tz": DEFAULT_TZ, "verify": V_NEARME},
]

# ============================================================
# D. REAL PLACE / BUSINESS INFO (6)
#    Hours, contact, address. Tests structured-data extraction from
#    SERP knowledge panels via SearXNG snippets.
# ============================================================
SCENARIOS += [
    {"id": "WSD1",  "cat": "Place Info", "name": "Phoenix Marketcity hours",
     "msg": "phoenix marketcity pune opening hours today",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSD2",  "cat": "Place Info", "name": "Pune airport baggage contact",
     "msg": "pune airport main contact number for lost baggage",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSD3",  "cat": "Place Info", "name": "Apple service center in Pune",
     "msg": "is there an apple authorized service center in pune, where",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSD4",  "cat": "Place Info", "name": "SBI Aundh IFSC",
     "msg": "sbi aundh branch ifsc code",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSD5",  "cat": "Place Info", "name": "Inox Bund Garden Sunday timing",
     "msg": "what time does inox bund garden close on sundays",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSD6",  "cat": "Place Info", "name": "Domino's Koregaon Park phone",
     "msg": "domino's pizza koregaon park phone number",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
]

# ============================================================
# E. PRODUCT RESEARCH (6)
#    Comparisons, prices, recent releases. Multi-source synthesis.
# ============================================================
SCENARIOS += [
    {"id": "WSE1",  "cat": "Product",    "name": "iPhone 17 Pro Max India price",
     "msg": "iphone 17 pro max price in india now",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSE2",  "cat": "Product",    "name": "OnePlus 13 vs Samsung S25",
     "msg": "oneplus 13 vs samsung s25 which is better in 2026",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSE3",  "cat": "Product",    "name": "Best laptops under 80k INR",
     "msg": "best laptops under 80000 inr for college students right now",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSE4",  "cat": "Product",    "name": "Tesla in India yet?",
     "msg": "are tesla cars officially available in india yet",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSE5",  "cat": "Product",    "name": "New AI launches this month",
     "msg": "what notable AI products were launched this month",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSE6",  "cat": "Product",    "name": "Top 3 smart watches under 30k",
     "msg": "compare top 3 smart watches under 30000 inr right now",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
]

# ============================================================
# F. SPORTS & ENTERTAINMENT (4)
#    Scores and showtimes — high-freshness, snippet-quality dependent.
# ============================================================
SCENARIOS += [
    {"id": "WSF1",  "cat": "Sports/Ent", "name": "MI vs CSK last match",
     "msg": "mumbai indians vs csk last match score and result",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSF2",  "cat": "Sports/Ent", "name": "Bollywood releases this Friday",
     "msg": "any new bollywood movies releasing this friday",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSF3",  "cat": "Sports/Ent", "name": "Latest F1 GP results",
     "msg": "f1 race results from the most recent grand prix",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSF4",  "cat": "Sports/Ent", "name": "IPL points table",
     "msg": "indian premier league points table right now",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
]

# ============================================================
# G. COMPOUND / SYNTHESIS (4)
#    Multiple sub-questions in one prompt; reply must address each.
# ============================================================
SCENARIOS += [
    {"id": "WSG1",  "cat": "Compound",   "name": "Phone comparison: price+camera",
     "msg": "compare iphone 17 pro max and pixel 10 pro on price in india and camera quality",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSG2",  "cat": "Compound",   "name": "Mahabaleshwar weekend trip",
     "msg": ("planning a trip to mahabaleshwar next weekend — what's the weather "
             "forecast and any festivals or events happening there"),
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSG3",  "cat": "Compound",   "name": "RBI policy + home loan rates",
     "msg": "summarize the latest rbi policy and how it might affect home loan rates",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
    {"id": "WSG4",  "cat": "Compound",   "name": "TCS vs Infosys Q4 + analyst view",
     "msg": "between tcs and infosys which had better q4 results and which one are analysts favoring",
     "tz": DEFAULT_TZ, "verify": V_SEARCH},
]

# ============================================================
# H. SHOULD-NOT-SEARCH (3)
#    Verifies the agent's skip logic in <web_search_protocol>. The model
#    must answer directly — no URL citation. Latency typically <30s on a
#    warm cache.
# ============================================================
SCENARIOS += [
    {"id": "WSH1",  "cat": "No-Search",  "name": "Math: 17% of 4500",
     "msg": "what's 17 percent of 4500",
     "tz": DEFAULT_TZ, "verify": V_NO_SEARCH},
    {"id": "WSH2",  "cat": "No-Search",  "name": "Stable tech: REST vs GraphQL",
     "msg": "explain the difference between rest and graphql apis briefly",
     "tz": DEFAULT_TZ, "verify": V_NO_SEARCH},
    {"id": "WSH3",  "cat": "No-Search",  "name": "Creative: dog name suggestions",
     "msg": "suggest 5 unique names for a black labrador puppy",
     "tz": DEFAULT_TZ, "verify": V_NO_SEARCH},
]

# Sanity check: this file is a 50-scenario suite by design.
assert len(SCENARIOS) == 50, f"Expected 50 scenarios, got {len(SCENARIOS)}"
