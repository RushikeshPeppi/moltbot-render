# Web-Search Test Plan — Peppi (50 scenarios)

> Senior-tester suite for the `web-search` skill that ships with the moltbot-gateway as of commit `e29f6be`. **Distinct from** [scenarios.py](scenarios.py) (calendar / reminders / email / image — 193 cases). Runs separately, results saved separately. Designed so it can be referenced from the existing test infrastructure but maintained as an independent target.

## 1. Why a separate suite

The existing 193 scenarios verify deterministic skills (calendar event creation, reminder scheduling, Gmail send) where the agent either does the action or it doesn't, and verification reads back the resulting Google / FastAPI state. **Web search has none of those properties:**

- The "right answer" changes by the second (BTC price, IPL score, news headlines).
- There is no API to read back from — the only artefact is the LLM's reply.
- Pass/fail must be inferred from response shape (citations, grounding signals, presence of cutoff disclaimers), not from a state mutation.

Mixing those two verification models in one runner would dilute the signal of both. Hence: separate scenarios file, separate runner, separate results file. Senior testers read one set of results without having to filter.

## 2. Files

| File | Purpose |
|---|---|
| [`web_search_scenarios.py`](web_search_scenarios.py) | The 50 scenarios. Pure data, no logic. |
| [`run_web_search_tests.py`](run_web_search_tests.py) | Standalone runner with web-search-aware verifiers. Mirrors the API-call shape of `run_tests.py` but does not import from it. |
| `results/web_search_results.json` | Output. Created on first run. **Never overwrites `results/test_results.json`.** |
| `WEB_SEARCH_TESTS.md` | This document. |

## 3. Test user

Default user: **`usr_9aadeaf0`** (Rushi2 / Pune, India). This is the only user who currently has a `city` set in `tbl_clawdbot_users`, which is required for the `V_NEARME` category to verify cleanly.

Override via env:

```sh
WEB_SEARCH_USER_ID=usr_xxx WEB_SEARCH_USER_CITY="Mumbai, India" python run_web_search_tests.py
```

If you change the city away from Pune, the `V_NEARME` localisation regex (Pune neighbourhoods) in [`run_web_search_tests.py`](run_web_search_tests.py) needs to be updated as well — see `PUNE_LANDMARKS_RE`. Otherwise, the city-token fallback alone will still detect localisation, just with weaker confidence.

## 4. Verification types

Stronger than the `response_only` checks in `scenarios.py`. Each scenario declares one of:

| `verify` | Used for | Pass criteria |
|---|---|---|
| `V_SEARCH` | Queries that **must** trigger a web search | Reply ≥ 30 chars, contains a URL citation OR specific facts (numbers / named entities), and contains **no** knowledge-cutoff disclaimer |
| `V_NEARME` | Queries with `near me` / `nearby` semantics that depend on `$USER_CITY` | All of `V_SEARCH` + reply mentions the user's city or a known landmark from that city |
| `V_NO_SEARCH` | Queries the model should answer directly **without** searching | Non-empty reply that does **not** contain a URL citation. Latency captured as a soft signal but does not gate. |
| `V_RESPONSE` | Fallback when no deeper grading is possible | Non-empty 200 |

The disclaimer detector is the load-bearing safety net for `V_SEARCH`. If the model says "as of my training cutoff..." or "I don't have real-time access to..." for a query that requires fresh data, that's a hard fail — proves the model declined to search. See `DISCLAIMER_PATTERNS` in [`run_web_search_tests.py`](run_web_search_tests.py) for the full list.

## 5. How to run

```sh
cd tests/

# Full suite (50 scenarios, ~30-40 min wall-clock on a warm cache)
python run_web_search_tests.py

# A single category (8 dimensions: A B C D E F G H)
python run_web_search_tests.py --category C    # Hyperlocal "Near Me" (12)
python run_web_search_tests.py --category H    # Should-NOT-Search (3)

# A single scenario
python run_web_search_tests.py --scenario WSB1

# Re-run only the rows that failed last time
python run_web_search_tests.py --rerun-failed
```

The runner saves after each scenario, so a Ctrl-C / network blip / Render cold start mid-suite leaves the results file in a consistent state. Re-running picks up where it left off (passing rows preserved, failures retried with `--rerun-failed`).

## 6. Cost expectation

Each scenario triggers one `/execute-action` round-trip. With prompt caching warm, that's ~$0.012-0.020 in Sonnet 4.6 tokens for the search-triggered turns and ~$0.003-0.005 for the no-search turns (lower since the tool_result block is absent). Full suite cost ballpark: **$0.50-1.00**.

Latency: **80-160 s per `V_SEARCH` / `V_NEARME` scenario** (model thinking + skill execution + second-turn answer composition), **<30 s for `V_NO_SEARCH`**. Total suite walltime ≈ **30-45 minutes** running serially.

## 7. The 50 scenarios

### A. Current Events & News (8) — `V_SEARCH`
Post-cutoff data; tests recency triggering.

| ID | Query |
|---|---|
| `WSA1` | what happened in indian politics this week |
| `WSA2` | any latest update on monsoon arrival in maharashtra |
| `WSA3` | have there been any major tech layoffs in indian companies recently |
| `WSA4` | what did the RBI announce this week, anything on rates? |
| `WSA5` | what's the latest on chandrayaan or any ISRO mission |
| `WSA6` | any major releases from anthropic or openai this week |
| `WSA7` | what's the status of india us trade talks right now |
| `WSA8` | give me the top 3 international news headlines today, briefly |

### B. Live Market Data (7) — `V_SEARCH`
Prices / rates that change continuously; reply must include a numeric figure.

| ID | Query |
|---|---|
| `WSB1` | what is the current price of bitcoin in INR |
| `WSB2` | where did sensex and nifty close today |
| `WSB3` | gold rate in pune today per 10 gram |
| `WSB4` | petrol price in pune today, per litre |
| `WSB5` | usd to inr exchange rate today |
| `WSB6` | reliance industries share price right now |
| `WSB7` | tcs vs infosys stock price comparison today |

### C. Hyperlocal "Near Me" (12) — `V_NEARME`
Verifies `$USER_CITY` plumbing end-to-end. The reply must reference Pune, a Pune neighbourhood, or local detail proving the search was location-aware.

| ID | Query |
|---|---|
| `WSC1` | best vada pav near me right now |
| `WSC2` | where can I get authentic south indian breakfast nearby |
| `WSC3` | good gym with monthly pass under 2000 near me |
| `WSC4` | 24 hour pharmacy near me |
| `WSC5` | best biryani places in koregaon park |
| `WSC6` | any indian classical music concerts in pune this weekend |
| `WSC7` | movie theatres in my area playing the latest tamil movies |
| `WSC8` | roughly what is the auto fare from FC road to hinjewadi |
| `WSC9` | good vegetarian restaurants near me with parking |
| `WSC10` | any farmers market or organic produce store nearby |
| `WSC11` | weekend trekking groups or hikes from pune |
| `WSC12` | good dentists in aundh or baner |

### D. Real Place / Business Info (6) — `V_SEARCH`
Hours, contact, address — tests structured-data extraction from SERP knowledge panels.

| ID | Query |
|---|---|
| `WSD1` | phoenix marketcity pune opening hours today |
| `WSD2` | pune airport main contact number for lost baggage |
| `WSD3` | is there an apple authorized service center in pune, where |
| `WSD4` | sbi aundh branch ifsc code |
| `WSD5` | what time does inox bund garden close on sundays |
| `WSD6` | domino's pizza koregaon park phone number |

### E. Product Research (6) — `V_SEARCH`
Comparisons, prices, recent releases — multi-source synthesis.

| ID | Query |
|---|---|
| `WSE1` | iphone 17 pro max price in india now |
| `WSE2` | oneplus 13 vs samsung s25 which is better in 2026 |
| `WSE3` | best laptops under 80000 inr for college students right now |
| `WSE4` | are tesla cars officially available in india yet |
| `WSE5` | what notable AI products were launched this month |
| `WSE6` | compare top 3 smart watches under 30000 inr right now |

### F. Sports & Entertainment (4) — `V_SEARCH`
High-freshness, snippet-quality dependent.

| ID | Query |
|---|---|
| `WSF1` | mumbai indians vs csk last match score and result |
| `WSF2` | any new bollywood movies releasing this friday |
| `WSF3` | f1 race results from the most recent grand prix |
| `WSF4` | indian premier league points table right now |

### G. Compound / Synthesis (4) — `V_SEARCH`
Multiple sub-questions in one prompt; the reply must address each.

| ID | Query |
|---|---|
| `WSG1` | compare iphone 17 pro max and pixel 10 pro on price in india and camera quality |
| `WSG2` | planning a trip to mahabaleshwar next weekend — what's the weather forecast and any festivals or events happening there |
| `WSG3` | summarize the latest rbi policy and how it might affect home loan rates |
| `WSG4` | between tcs and infosys which had better q4 results and which one are analysts favoring |

### H. Should-NOT-Search (3) — `V_NO_SEARCH`
Verifies the agent's skip logic in `<web_search_protocol>`. The model must answer directly with no URL citation.

| ID | Query |
|---|---|
| `WSH1` | what's 17 percent of 4500 |
| `WSH2` | explain the difference between rest and graphql apis briefly |
| `WSH3` | suggest 5 unique names for a black labrador puppy |

## 8. Pass / fail heuristics in detail

The suite uses regex-based heuristics, not LLM judges, so the verdicts are reproducible. The trade-off is that a well-grounded reply with no URL **and** no numbers (rare in practice) will fail `V_SEARCH`. That trade is intentional — false positives on grounding are far more dangerous than false negatives, given the prompt-injection surface in untrusted snippets.

### `V_SEARCH` pass requires all of:
1. `len(reply.strip()) >= 30`
2. **Either** a URL-shaped citation (regex: `https?://...`, `(via domain.com)`, or `(source: domain.com)`) **or** a "specific fact" (a 2+ digit number OR two consecutive capitalised words suggesting a named entity).
3. **No** knowledge-cutoff disclaimer (`as of my training cutoff`, `I don't have real-time access`, `I cannot browse`, etc. — see `DISCLAIMER_PATTERNS`).

### `V_NEARME` pass requires all of `V_SEARCH` plus:
4. The reply mentions either (a) the user's city token (e.g. `pune`) or (b) a Pune neighbourhood / landmark from `PUNE_LANDMARKS_RE`.

### `V_NO_SEARCH` pass requires:
1. Non-empty reply.
2. **No** URL citation in the reply.

Latency is recorded for analysis but does not affect the verdict — cache state and Render cold-starts make latency too noisy a signal to gate on.

## 9. Known limitations (read before reporting failures)

These are honest, not excuses. Senior testers should mentally subtract these from any failure count.

1. **Engine flakiness shows up as failures.** SearXNG's `unresponsive_engines` rotates day-to-day; if the day's lineup is bad (DuckDuckGo timing out, Brave rate-limited), result quality drops and grounding heuristics fail. Re-run the failed scenarios with `--rerun-failed` an hour later before treating it as a real regression.
2. **`V_NEARME` Pune-landmark regex is finite.** The list at `PUNE_LANDMARKS_RE` covers the obvious neighbourhoods; an answer that says "near you in MG Road" with no Pune token would false-fail. Add to the regex if you see this in practice.
3. **No-search latency is not gated.** A cold-cache no-search reply can take 60+ s due to model loading, even though no SearXNG call happened. Latency is captured in `signals.elapsed_seconds` so you can see it, but the verdict only checks for a URL.
4. **Compound queries (G) are graded the same as single-fact queries.** The runner does NOT verify that the reply addresses each sub-question — only that it's grounded. A model that ignores half the prompt would still pass `V_SEARCH`. Read `agent_reply` for those rows manually.
5. **Pricing in INR / business hours change daily.** A correctly-grounded reply can still be factually stale. The verifier confirms grounding, not accuracy. For the prices in Section B, eyeball `agent_reply` to spot suspicious figures.
6. **Snippet prompt injection.** Indirectly tested — the agent.md tells the model to treat snippet content as untrusted. This suite does NOT contain prompt-injection test cases. That's a separate security suite, intentionally.

## 10. Reading the results

`results/web_search_results.json` is JSON of the form:

```jsonc
{
  "meta": {
    "suite": "web_search",
    "user_id": "usr_9aadeaf0",
    "user_city": "Pune, India",
    "passed": 47,
    "failed": 3,
    "last_updated": "2026-04-27T..."
  },
  "results": [
    {
      "scenario_id": "WSC5",
      "category": "Near Me",
      "verify_type": "near_me_localized",
      "agent_reply": "...",
      "verification": {
        "method": "near_me_localized",
        "verified": true,
        "reason": "Grounded + localised reply",
        "signals": {
          "has_url": true,
          "has_grounded_facts": true,
          "has_disclaimer": false,
          "has_city_token": false,
          "has_pune_landmark": true,
          "length": 612
        }
      },
      "result": "pass",
      "elapsed_seconds": 89.4
    }
    // ... 49 more
  ]
}
```

For a quick at-a-glance summary, jq it:

```sh
jq '[.results[] | {id: .scenario_id, cat: .category, result, reason: .verification.reason}] |
    group_by(.cat) | map({category: .[0].cat, total: length,
      passed: (map(select(.result=="pass")) | length),
      failed: (map(select(.result=="fail")) | length)})' \
    results/web_search_results.json
```

## 11. Maintenance contract

- **Adding scenarios:** append to the appropriate category block in `web_search_scenarios.py` and bump the `assert len(SCENARIOS) == 50` to the new total. Keep IDs sequential (`WSA9`, `WSC13`, etc.).
- **Changing the test city:** update both `WEB_SEARCH_USER_CITY` env default and `PUNE_LANDMARKS_RE` in the runner.
- **Disabling a scenario:** comment it out in `web_search_scenarios.py` and decrement the assertion. Don't reuse the ID later — that confuses results diffing.
- **Adding a new verifier:** add a constant in `web_search_scenarios.py`, implement it in `run_web_search_tests.py`'s `run_scenario`, and document the pass criteria in this file's section 8.
