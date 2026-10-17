"""Offline stand-in for the fictional Lantern CLI v3 `scan` command. Assessment fixture only.

It never touches the network and reads no file except the scenario JSON. The scenario describes what the
Lantern service would return; this script applies the CLI rules from product.md and exits 0, 1, 2 or 3.

    python3 inputs/lantern_mock.py --scenario SCENARIO.json scan mobile --file PATH --plan PLAN
        [--wait] [--fail-on SEVERITY] [--baseline SCAN_ID]
    python3 inputs/lantern_mock.py --scenario SCENARIO.json scan web --target URL --auth PROFILE
        [--openapi PATH] [--wait] [--fail-on SEVERITY] [--baseline SCAN_ID]

The API key is read from the LANTERN_API_KEY environment variable, as the real CLI does. One JSON result object
is printed on stdout; a one-line human summary is printed on stderr.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import typing

SEVERITIES = ["info", "low", "medium", "high", "critical"]
COUNTED_STATUSES = {"open", "confirmed"}
MOBILE_PLANS = {"mobile-full", "mobile-static"}
WAIT_LIMIT_MIN = 60

EXIT_COMPLETED = 0
EXIT_THRESHOLD = 1
EXIT_SCAN_ERROR = 2
EXIT_CONFIG_ERROR = 3


class ConfigError(Exception):
    """Raised for problems the CLI detects before a scan is submitted."""


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> typing.NoReturn:
        # The real CLI reports bad arguments as configuration errors, never as scan errors.
        finish({"status": "config_error", "message": f"invalid arguments: {message}"}, EXIT_CONFIG_ERROR)


def finish(result: dict[str, typing.Any], code: int) -> typing.NoReturn:
    result = {"cli": "lantern-mock 3.0", **result, "exit_code": code}
    print(json.dumps(result, indent=2))
    print(f"lantern: {result['status']}: {result.get('message', '')} (exit {code})", file=sys.stderr)
    sys.exit(code)


def build_parser() -> Parser:
    parser = Parser(prog="lantern_mock.py")
    parser.add_argument("--scenario", required=True)
    commands = parser.add_subparsers(dest="command", required=True, parser_class=Parser)
    scan = commands.add_parser("scan")
    kinds = scan.add_subparsers(dest="kind", required=True, parser_class=Parser)
    mobile = kinds.add_parser("mobile")
    mobile.add_argument("--file", required=True)
    mobile.add_argument("--plan", required=True)
    web = kinds.add_parser("web")
    web.add_argument("--target", required=True)
    web.add_argument("--auth", required=True)
    web.add_argument("--openapi")
    for sub in (mobile, web):
        sub.add_argument("--wait", action="store_true")
        sub.add_argument("--fail-on", choices=SEVERITIES)
        sub.add_argument("--baseline")
    return parser


def validate(args: argparse.Namespace, service: dict[str, typing.Any]) -> None:
    if not os.environ.get("LANTERN_API_KEY"):
        raise ConfigError("LANTERN_API_KEY is not set")
    if not service.get("api_key_valid", True):
        raise ConfigError("API key rejected by tenant (revoked or unknown)")
    files = set(service.get("workspace_files", []))
    if args.kind == "mobile":
        if args.plan not in MOBILE_PLANS:
            raise ConfigError(f"unknown scan plan {args.plan!r}")
        if args.file not in files:
            raise ConfigError(f"file not found: {args.file}")
    else:
        if args.auth not in service.get("auth_profiles", []):
            raise ConfigError(f"unknown auth profile {args.auth!r}")
        if args.openapi is not None and args.openapi not in files:
            raise ConfigError(f"file not found: {args.openapi}")
    if args.baseline is not None and args.baseline not in service.get("baselines", {}):
        raise ConfigError(f"baseline scan {args.baseline!r} not found as a completed scan in this tenant")


def coverage(args: argparse.Namespace, service: dict[str, typing.Any]) -> dict[str, str]:
    if args.kind == "web":
        return {"dast": "done", "api_operations": "openapi import" if args.openapi else "crawl only (no OpenAPI import)"}
    if args.plan == "mobile-static":
        return {"static": "done", "dynamic": "not requested"}
    if args.file.endswith(".ipa") and service.get("ios_signing") == "app_store":
        return {"static": "done", "dynamic": "skipped: App Store-encrypted IPA (static only)"}
    return {"static": "done", "dynamic": "done"}


def main() -> None:
    args = build_parser().parse_args()
    scenario = json.loads(pathlib.Path(args.scenario).read_text(encoding="utf-8"))
    service = scenario["lantern"]
    base = {"scan_id": None, "kind": args.kind, "fail_on": args.fail_on, "baseline": args.baseline}
    try:
        validate(args, service)
    except ConfigError as error:
        finish({**base, "status": "config_error", "message": str(error)}, EXIT_CONFIG_ERROR)

    base["scan_id"] = service["scan_id"]
    if not args.wait:
        finish({**base, "status": "submitted", "message": "scan submitted; results not evaluated without --wait"}, EXIT_COMPLETED)
    if args.kind == "web" and not service.get("target_reachable", True):
        finish({**base, "status": "error", "message": "Lantern scanners could not reach the target (check allowlist for Lantern egress ranges)"}, EXIT_SCAN_ERROR)
    if service["duration_min"] > WAIT_LIMIT_MIN:
        finish({**base, "status": "timeout", "message": f"stopped waiting after {WAIT_LIMIT_MIN} min; scan continues server-side"}, EXIT_SCAN_ERROR)
    if service.get("outcome", "completed") != "completed":
        finish({**base, "status": "error", "message": service.get("error_message", "scan failed")}, EXIT_SCAN_ERROR)

    known = set(service.get("baselines", {}).get(args.baseline, [])) if args.baseline else set()
    threshold = SEVERITIES.index(args.fail_on) if args.fail_on else None
    findings, excluded = [], []
    for finding in service.get("findings", []):
        if finding["fingerprint"] in known:
            excluded.append(finding["id"])
            continue
        counted = threshold is not None and finding["status"] in COUNTED_STATUSES and SEVERITIES.index(finding["severity"]) >= threshold
        findings.append({**finding, "counts_toward_exit": counted})
    code = EXIT_THRESHOLD if any(f["counts_toward_exit"] for f in findings) else EXIT_COMPLETED
    blocking = [f["id"] for f in findings if f["counts_toward_exit"]]
    message = f"{len(blocking)} open finding(s) at or above {args.fail_on}" if args.fail_on else "completed; no --fail-on threshold set"
    finish(
        {
            **base,
            "status": "completed",
            "duration_min": service["duration_min"],
            "coverage": coverage(args, service),
            "findings": findings,
            "excluded_by_baseline": excluded,
            "message": message,
        },
        code,
    )


if __name__ == "__main__":
    main()
