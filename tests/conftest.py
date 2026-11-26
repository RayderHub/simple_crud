"""
Plugin de Pytest para enviar cada prueba individual (Backend y Frontend) con sus logs,
duración y resultado directamente al stream 'playwright_tests' de OpenObserve.
"""

from datetime import datetime, timezone
import os
import requests

_TEST_RESULTS = []


def _classify_category(nodeid: str) -> str:
    lower = nodeid.lower()
    if "backend" in lower or "api" in lower or "health" in lower:
        return "backend"
    return "frontend"


def pytest_runtest_makereport(item, call):
    if call.when != "call":
        return

    nodeid = item.nodeid
    test_name = item.name
    category = _classify_category(nodeid)
    doc = (getattr(item.function, "__doc__", "") or "").strip()
    duration_ms = round(call.duration * 1000, 2)

    if call.excinfo is None:
        status = "PASSED"
        log_msg = f"[PASSED] {test_name} ({duration_ms} ms) | {doc}"
    else:
        status = "FAILED"
        log_msg = f"[FAILED] {test_name} ({duration_ms} ms) | {call.excinfo.exconly()}"

    _TEST_RESULTS.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "test_name": test_name,
        "nodeid": nodeid,
        "category": category,
        "status": status,
        "duration_ms": duration_ms,
        "description": doc,
        "log": log_msg,
        "commit_sha": os.getenv("GITHUB_SHA", "local"),
        "commit_short": os.getenv("GITHUB_SHA", "local")[:7],
        "branch": os.getenv("GITHUB_REF_NAME", "main"),
        "actor": os.getenv("GITHUB_ACTOR", "RayderHub"),
        "run_id": os.getenv("GITHUB_RUN_ID", "local-run"),
    })


def pytest_sessionfinish(session, exitstatus):
    oo_url = os.getenv("OPENOBSERVE_URL", "").strip().rstrip("/")
    oo_user = os.getenv("OPENOBSERVE_USER", "").strip()
    oo_pass = os.getenv("OPENOBSERVE_PASSWORD", "").strip()
    if not (oo_url and oo_user and oo_pass and _TEST_RESULTS):
        return

    endpoint = f"{oo_url}/api/default/playwright_tests/_json"
    try:
        resp = requests.post(
            endpoint,
            json=_TEST_RESULTS,
            auth=(oo_user, oo_pass),
            timeout=10,
        )
        print(f"\n[OpenObserve] {len(_TEST_RESULTS)} pruebas individuales enviadas a 'playwright_tests' -> HTTP {resp.status_code}")
    except Exception as exc:
        print(f"\n[OpenObserve] No se pudieron enviar pruebas individuales: {exc}")
