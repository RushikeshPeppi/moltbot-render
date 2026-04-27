"""
Web-Search Test Runner — Executes the 50 scenarios in web_search_scenarios.py
against the production /execute-action endpoint, with web-search-aware
verification (search/no-search/near-me grounding heuristics).

This is intentionally SEPARATE from run_tests.py. It does not share state,
results, or verifiers with the calendar/reminder/email suite. Results land
in tests/results/web_search_results.json; running this script never touches
tests/results/test_results.json.

Usage:
  python run_web_search_tests.py                        # Run all 50
  python run_web_search_tests.py --category A           # Run "Current Events" (WSA*)
  python run_web_search_tests.py --scenario WSC5        # Run a single scenario
  python run_web_search_tests.py --rerun-failed         # Re-run only failed
  WEB_SEARCH_USER_ID=usr_other python run_web_search_tests.py
"""

import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from web_search_scenarios import (
    SCENARIOS,
    API_URL,
    USER_ID,
    USER_CITY,
    V_SEARCH,
    V_NEARME,
    V_NO_SEARCH,
    V_RESPONSE,
)

RESULTS_FILE = Path(__file__).parent / "results" / "web_search_results.json"
TIMEOUT = 240  # web-search turns can run 80-160s; allow a 4-min ceiling


# ----------------------------------------------------------------------
# API call (mirrors run_tests.py.call_api but keeps the suites independent)
# ----------------------------------------------------------------------

def call_api(message: str, tz: str, _attempt: int = 1) -> dict:
    """POST /execute-action. Single retry on transient non-JSON / network blips."""
    payload = {
        "user_id": USER_ID,
        "message": message,
        "timezone": tz,
        "image_urls": None,
        "num_media": 0,
    }
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(f"{API_URL}/execute-action", json=payload)
        try:
            return resp.json()
        except json.JSONDecodeError as je:
            body_snippet = (resp.text or "")[:500]
            if _attempt < 2:
                time.sleep(1.5)
                return call_api(message, tz, _attempt=_attempt + 1)
            return {
                "code": resp.status_code or 0,
                "error": "INVALID_JSON_RESPONSE",
                "message": f"Non-JSON body ({len(body_snippet)} chars): {body_snippet}",
                "exception": str(je),
                "data": None,
            }
    except httpx.TimeoutException:
        return {"code": 0, "error": "TIMEOUT", "message": "Request timed out", "data": None}
    except httpx.HTTPError as e:
        if _attempt < 2:
            time.sleep(1.5)
            return call_api(message, tz, _attempt=_attempt + 1)
        return {"code": 0, "error": "REQUEST_ERROR", "message": str(e), "data": None}
    except Exception as e:
        return {"code": 0, "error": "REQUEST_ERROR", "message": str(e), "data": None}


# ----------------------------------------------------------------------
# Verifiers
# ----------------------------------------------------------------------

# Knowledge-cutoff disclaimer patterns. If any of these match, the model
# refused to search — that is a failure for V_SEARCH cases.
DISCLAIMER_PATTERNS = [
    r"as of my (training|knowledge)",
    r"as of my last (update|knowledge)",
    r"my (training|knowledge) (data )?cutoff",
    r"i (don'?t|do not) have (real-?time|current|live|access to (real-?time|live))",
    r"i (cannot|can't|am not able to) (browse|search|access the (web|internet))",
    r"i (cannot|can't) provide (real-?time|live|current)",
    r"i don'?t have (the )?ability to (browse|search|access)",
]
DISCLAIMER_RE = re.compile("|".join(DISCLAIMER_PATTERNS), re.I)

# Citation signals — URLs in plain form, "(via domain.com)", "source: domain"
URL_RE = re.compile(
    r"https?://[^\s)>\]]+|"
    r"\(via\s+[a-z0-9.-]+\.[a-z]{2,}[^)]*\)|"
    r"\(source:\s*[a-z0-9.-]+\.[a-z]{2,}[^)]*\)",
    re.I,
)

# Pune-area landmarks for the V_NEARME verifier (when USER_CITY contains "Pune").
# These are real Pune neighborhoods / landmarks the model is likely to surface
# in localised replies. Update this list if you change the test city.
PUNE_LANDMARKS_RE = re.compile(
    r"\b(pune|pcmc|koregaon|kalyani\s*nagar|aundh|baner|hinjewadi|hadapsar|"
    r"camp|fc\s*road|deccan|shivajinagar|shivaji\s*nagar|kothrud|viman\s*nagar|"
    r"bund\s*garden|wakad|magarpatta|kondhwa|undri|sinhagad|katraj|swargate|"
    r"bavdhan|wagholi|pashan|warje|narayan\s*peth|sadashiv\s*peth|kasba\s*peth|"
    r"nashik|mahabaleshwar|lonavala|khandala|lavasa)\b",
    re.I,
)


def _has_specific_facts(reply: str) -> bool:
    """Heuristic: a grounded reply usually contains numbers (prices, scores,
    years, ranks, percentages) or named entities flagged by capitalisation."""
    if not reply:
        return False
    has_number = bool(re.search(r"\d{2,}", reply))
    # Two or more capitalised words in a row often = named entity.
    has_named_entity = bool(re.search(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b", reply))
    return has_number or has_named_entity


def verify_search(reply: str, *, expect_localised: bool = False, city: str = "") -> dict:
    """Common grounding check. Used for both V_SEARCH and as the base for
    V_NEARME. Returns a dict suitable for embedding in the result row.
    """
    reply = reply or ""
    if len(reply.strip()) < 30:
        return {
            "method": V_SEARCH,
            "verified": False,
            "reason": "Reply too short (<30 chars)",
            "signals": {"length": len(reply)},
        }

    has_url = bool(URL_RE.search(reply))
    has_disclaimer = bool(DISCLAIMER_RE.search(reply))
    grounded_facts = _has_specific_facts(reply)

    # Pass condition: reply has either a URL or specific facts, AND has no
    # cutoff disclaimer. Disclaimers are a hard fail because they prove the
    # model declined to search.
    verified = (has_url or grounded_facts) and not has_disclaimer
    reason_parts = []
    if has_disclaimer:
        reason_parts.append("knowledge-cutoff disclaimer detected")
    if not has_url and not grounded_facts:
        reason_parts.append("no URL or grounded facts in reply")
    reason = "; ".join(reason_parts) if reason_parts else "Grounded reply"

    signals = {
        "has_url": has_url,
        "has_grounded_facts": grounded_facts,
        "has_disclaimer": has_disclaimer,
        "length": len(reply),
    }

    if expect_localised:
        # NEARME extension: at least one of (USER_CITY token in reply, known
        # Pune landmark) must appear. Without this, the model probably ignored
        # USER_CITY entirely.
        city_token = (city.split(",")[0].strip().lower() if city else "")
        has_city_token = (
            bool(re.search(rf"\b{re.escape(city_token)}\b", reply, re.I))
            if city_token else False
        )
        has_landmark = bool(PUNE_LANDMARKS_RE.search(reply))
        localised = has_city_token or has_landmark
        signals["has_city_token"] = has_city_token
        signals["has_pune_landmark"] = has_landmark

        if verified and not localised:
            verified = False
            reason = f"Grounded but no '{city_token}' / Pune-landmark reference"
        elif not verified:
            pass  # already failed grounding
        else:
            reason = "Grounded + localised reply"

        return {"method": V_NEARME, "verified": verified, "reason": reason, "signals": signals}

    return {"method": V_SEARCH, "verified": verified, "reason": reason, "signals": signals}


def verify_no_search(reply: str, elapsed: float) -> dict:
    """For SHOULD-NOT-SEARCH cases. The reply should not cite a URL. Latency
    is captured as a signal but does NOT gate the verdict — cache state
    varies across runs and a slow direct reply is still a direct reply."""
    reply = reply or ""
    if not reply.strip():
        return {
            "method": V_NO_SEARCH,
            "verified": False,
            "reason": "Empty reply",
            "signals": {"elapsed_seconds": elapsed},
        }

    has_url = bool(URL_RE.search(reply))
    verified = not has_url
    return {
        "method": V_NO_SEARCH,
        "verified": verified,
        "reason": "Direct answer (no URL)" if verified else "URL detected — search likely triggered",
        "signals": {
            "has_url": has_url,
            "elapsed_seconds": elapsed,
            "length": len(reply),
        },
    }


# ----------------------------------------------------------------------
# Result IO
# ----------------------------------------------------------------------

def load_existing_results() -> dict:
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE) as f:
            data = json.load(f)
            return {r["scenario_id"]: r for r in data.get("results", [])}
    return {}


def save_results(results: dict, run_meta: dict) -> None:
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    out = {"meta": run_meta, "results": list(results.values())}
    with open(RESULTS_FILE, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\n💾 Results saved to {RESULTS_FILE}")


# ----------------------------------------------------------------------
# Per-scenario execution
# ----------------------------------------------------------------------

def run_scenario(scenario: dict, idx: int, total: int) -> dict:
    sid = scenario["id"]
    name = scenario["name"]
    cat = scenario["cat"]
    msg = scenario["msg"]
    tz = scenario.get("tz", "Asia/Kolkata")
    verify_type = scenario.get("verify", V_RESPONSE)

    print(f"\n[{idx}/{total}] {sid} — {cat} — {name}")
    print(f"  📤 \"{msg[:90]}{'...' if len(msg) > 90 else ''}\"")

    start = time.time()
    api_resp = call_api(msg, tz)
    elapsed = round(time.time() - start, 1)

    code = api_resp.get("code", 0)
    reply = (api_resp.get("data") or {}).get("response", "") or ""
    error = api_resp.get("error")
    print(f"  📥 [{code}] ({elapsed}s) {reply[:130]}{'...' if len(reply) > 130 else ''}")

    # Base pass/fail from HTTP/agent layer
    if code != 200 or not reply:
        verification = {
            "method": verify_type,
            "verified": False,
            "reason": f"API failed: code={code} error={error or 'no reply'}",
            "signals": {},
        }
        result = "fail"
    else:
        if verify_type == V_SEARCH:
            verification = verify_search(reply)
        elif verify_type == V_NEARME:
            verification = verify_search(reply, expect_localised=True, city=USER_CITY)
        elif verify_type == V_NO_SEARCH:
            verification = verify_no_search(reply, elapsed)
        else:
            verification = {
                "method": V_RESPONSE,
                "verified": True,
                "reason": "Non-empty reply (no deeper check)",
                "signals": {"length": len(reply)},
            }
        result = "pass" if verification["verified"] else "fail"

    icon = {"pass": "✅", "fail": "❌"}.get(result, "?")
    print(f"  {icon} {verification['method']} — {verification['reason']}")

    return {
        "scenario_id": sid,
        "scenario_name": name,
        "category": cat,
        "message": msg,
        "timezone": tz,
        "verify_type": verify_type,
        "api_response_code": code,
        "agent_reply": reply,
        "error": error,
        "verification": verification,
        "result": result,
        "elapsed_seconds": elapsed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Web-search test runner")
    parser.add_argument(
        "--category", "-c",
        help="Run only scenarios whose ID starts with WS<letter> (e.g. 'A' → WSA*)",
    )
    parser.add_argument("--scenario", "-s", help="Run single scenario by full ID (e.g. WSC5)")
    parser.add_argument("--rerun-failed", "-r", action="store_true", help="Re-run only failed")
    args = parser.parse_args()

    to_run = SCENARIOS[:]
    if args.scenario:
        to_run = [s for s in to_run if s["id"] == args.scenario]
    elif args.category:
        prefix = "WS" + args.category.upper()
        to_run = [s for s in to_run if s["id"].startswith(prefix)]

    existing = load_existing_results()
    if args.rerun_failed:
        failed_ids = {sid for sid, r in existing.items() if r.get("result") != "pass"}
        to_run = [s for s in to_run if s["id"] in failed_ids]
        print(f"🔄 Re-running {len(to_run)} failed scenarios")

    if not to_run:
        print("No scenarios to run.")
        return

    total = len(to_run)
    print(f"🌐 Running {total} web-search scenario(s)")
    print(f"   API:  {API_URL}")
    print(f"   User: {USER_ID}  (city expected: {USER_CITY!r})")
    print(f"   Out:  {RESULTS_FILE}")
    print("=" * 64)

    results = existing.copy()  # preserve passing rows
    passed = failed = 0
    start_time = time.time()

    for idx, scenario in enumerate(to_run, 1):
        row = run_scenario(scenario, idx, total)
        results[row["scenario_id"]] = row

        if row["result"] == "pass":
            passed += 1
        else:
            failed += 1

        save_results(
            results,
            {
                "suite": "web_search",
                "user_id": USER_ID,
                "user_city": USER_CITY,
                "api_url": API_URL,
                "total_run": idx,
                "passed": passed,
                "failed": failed,
                "last_updated": datetime.now(timezone.utc).isoformat(),
            },
        )

    elapsed_total = round(time.time() - start_time, 1)
    print("\n" + "=" * 64)
    print(f"🏁 {total} scenarios in {elapsed_total}s")
    print(f"   ✅ Passed: {passed}")
    print(f"   ❌ Failed: {failed}")
    if failed:
        print(f"\n💡 Re-run failures: python run_web_search_tests.py --rerun-failed")


if __name__ == "__main__":
    main()
