"""
Moltbot Test Runner — Executes all 193 scenarios sequentially.
Usage:
  python run_tests.py                  # Run all
  python run_tests.py --category A     # Run category A only  
  python run_tests.py --rerun-failed   # Re-run only failed
  python run_tests.py --scenario A1    # Run single scenario
"""

import json
import time
import argparse
import httpx
from datetime import datetime, timezone
from pathlib import Path

from scenarios import SCENARIOS, API_URL, USER_ID, V_CAL_READ, V_REM_LIST, V_EMAIL_READ

RESULTS_FILE = Path(__file__).parent / "results" / "test_results.json"
TIMEOUT = 200  # seconds — agent can take 30-60s for complex tasks


def load_existing_results() -> dict:
    """Load previous results to support incremental re-runs."""
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE) as f:
            data = json.load(f)
            return {r["scenario_id"]: r for r in data.get("results", [])}
    return {}


def save_results(results: dict, run_meta: dict):
    """Save results to JSON."""
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "meta": run_meta,
        "results": list(results.values())
    }
    with open(RESULTS_FILE, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\n💾 Results saved to {RESULTS_FILE}")


def call_api(message: str, tz: str, image_urls=None, num_media=0) -> dict:
    """Call the Moltbot execute-action API."""
    payload = {
        "user_id": USER_ID,
        "message": message,
        "timezone": tz,
        "image_urls": image_urls,
        "num_media": num_media
    }
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(f"{API_URL}/execute-action", json=payload)
            return resp.json()
    except httpx.TimeoutException:
        return {"code": 0, "error": "TIMEOUT", "message": "Request timed out", "data": None}
    except Exception as e:
        return {"code": 0, "error": "REQUEST_ERROR", "message": str(e), "data": None}


def verify_calendar(tz: str) -> dict:
    """Cross-verify by reading calendar."""
    resp = call_api("What's on my calendar today and tomorrow?", tz)
    reply = (resp.get("data") or {}).get("response", "")
    return {
        "method": "calendar_read",
        "verified": bool(reply and len(reply) > 20),
        "details": reply[:500] if reply else "No response"
    }


def verify_reminders() -> dict:
    """Cross-verify by listing reminders via API."""
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{API_URL}/reminders/list/{USER_ID}")
            data = resp.json()
            reminders = (data.get("data") or {}).get("reminders", [])
            total = len(reminders)
            # Show latest 3
            latest = reminders[:3] if reminders else []
            summary = "; ".join(
                f"'{r.get('message','?')[:40]}' @ {r.get('trigger_at','?')}"
                for r in latest
            )
            return {
                "method": "reminder_list",
                "verified": total > 0,
                "details": f"{total} reminder(s). Latest: {summary}" if summary else "No reminders found"
            }
    except Exception as e:
        return {"method": "reminder_list", "verified": False, "details": f"Error: {e}"}


def verify_email(tz: str) -> dict:
    """Cross-verify by checking inbox."""
    resp = call_api("Check my inbox for the most recent email", tz)
    reply = (resp.get("data") or {}).get("response", "")
    return {
        "method": "email_inbox",
        "verified": bool(reply and len(reply) > 20),
        "details": reply[:500] if reply else "No response"
    }


def run_scenario(scenario: dict, idx: int, total: int) -> dict:
    """Execute a single test scenario."""
    sid = scenario["id"]
    name = scenario["name"]
    cat = scenario["cat"]
    msg = scenario["msg"]
    tz = scenario.get("tz", "Asia/Kolkata")
    verify_type = scenario.get("verify", "response_only")
    image_urls = scenario.get("image_urls")
    num_media = scenario.get("num_media", 0)

    img_tag = " 🖼️" if image_urls else ""
    print(f"\n[{idx}/{total}] {sid}: {name}{img_tag}")
    print(f"  📤 \"{msg[:80]}{'...' if len(msg)>80 else ''}\"")

    # Call API
    start = time.time()
    api_resp = call_api(msg, tz, image_urls, num_media)
    elapsed = round(time.time() - start, 1)

    code = api_resp.get("code", 0)
    agent_reply = (api_resp.get("data") or {}).get("response", "")
    error = api_resp.get("error")

    print(f"  📥 [{code}] ({elapsed}s) {agent_reply[:120]}{'...' if len(agent_reply or '')>120 else ''}")

    # Determine pass/fail from response
    if code == 200 and agent_reply:
        result = "pass"
    elif code == 200 and not agent_reply:
        result = "warn"
    else:
        result = "fail"

    # Cross-verify if needed
    verification = None
    if result == "pass" and verify_type == V_CAL_READ:
        print(f"  🔍 Verifying calendar...")
        verification = verify_calendar(tz)
        print(f"  {'✅' if verification['verified'] else '⚠️'} {verification['details'][:100]}")
    elif result == "pass" and verify_type == V_REM_LIST:
        print(f"  🔍 Verifying reminders...")
        verification = verify_reminders()
        print(f"  {'✅' if verification['verified'] else '⚠️'} {verification['details'][:100]}")
    elif result == "pass" and verify_type == V_EMAIL_READ:
        print(f"  🔍 Verifying email...")
        verification = verify_email(tz)
        print(f"  {'✅' if verification['verified'] else '⚠️'} {verification['details'][:100]}")

    status_emoji = {"pass": "✅", "fail": "❌", "warn": "⚠️"}
    print(f"  {status_emoji.get(result, '?')} Result: {result.upper()}")

    return {
        "scenario_id": sid,
        "scenario_name": name,
        "category": cat,
        "message": msg,
        "timezone": tz,
        "image_urls": image_urls,
        "num_media": num_media,
        "api_response": api_resp,
        "agent_reply": agent_reply,
        "status_code": code,
        "error": error,
        "verification": verification,
        "result": result,
        "failure_reason": error if result == "fail" else None,
        "elapsed_seconds": elapsed,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def main():
    parser = argparse.ArgumentParser(description="Moltbot Test Runner")
    parser.add_argument("--category", "-c", help="Run only this category prefix (e.g. A, B, JN)")
    parser.add_argument("--scenario", "-s", help="Run single scenario by ID (e.g. A1)")
    parser.add_argument("--rerun-failed", "-r", action="store_true", help="Re-run only failed scenarios")
    parser.add_argument("--skip-verify", action="store_true", help="Skip cross-verification")
    args = parser.parse_args()

    # Filter scenarios
    to_run = SCENARIOS[:]
    if args.scenario:
        to_run = [s for s in to_run if s["id"] == args.scenario]
    elif args.category:
        prefix = args.category.upper()
        to_run = [s for s in to_run if s["id"].startswith(prefix)]

    # Load existing results for rerun-failed
    existing = load_existing_results()
    if args.rerun_failed:
        failed_ids = {sid for sid, r in existing.items() if r.get("result") != "pass"}
        to_run = [s for s in to_run if s["id"] in failed_ids]
        print(f"🔄 Re-running {len(to_run)} failed scenarios")

    if not to_run:
        print("No scenarios to run!")
        return

    total = len(to_run)
    print(f"🚀 Running {total} scenario(s)...")
    print(f"   API: {API_URL}")
    print(f"   User: {USER_ID}")
    print("=" * 60)

    results = existing.copy()  # Preserve passing results
    passed = failed = warned = 0
    start_time = time.time()

    for idx, scenario in enumerate(to_run, 1):
        if args.skip_verify:
            scenario = {**scenario, "verify": "response_only"}
        result = run_scenario(scenario, idx, total)
        results[result["scenario_id"]] = result

        if result["result"] == "pass":
            passed += 1
        elif result["result"] == "fail":
            failed += 1
        else:
            warned += 1

        # Save after each scenario (crash-safe)
        save_results(results, {
            "total_run": idx,
            "passed": passed,
            "failed": failed,
            "warned": warned,
            "last_updated": datetime.now(timezone.utc).isoformat()
        })

    elapsed_total = round(time.time() - start_time, 1)
    print("\n" + "=" * 60)
    print(f"🏁 Done! {total} scenarios in {elapsed_total}s")
    print(f"   ✅ Passed: {passed}")
    print(f"   ❌ Failed: {failed}")
    print(f"   ⚠️  Warned: {warned}")

    if failed > 0:
        print(f"\n💡 Re-run failures: python run_tests.py --rerun-failed")


if __name__ == "__main__":
    main()
