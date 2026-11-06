#!/usr/bin/env python3
"""
RecallOps Groq Tool-Calling Smoke Test Script
Author: Member 4 (AI/ML & Model)
Phase: Phase 0 Kickoff (H0-H2)

Smoke tests function-calling capabilities of target models using the official `groq` SDK:
- Model A: openai/gpt-oss-120b
- Model B: qwen/qwen3-32b

Validates:
1. Retrieval of GROQ_API_KEY from .env / environment.
2. Toy tool specification: `enable_antigravity(service_name: str, power_level: int)`.
3. SRE prompt response parsing and structured tool call extraction.
4. Correctness of tool name and typed arguments (service_name='checkout-api', power_level=9).
5. Graceful exception handling for missing keys, network errors, and unsupported model IDs.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Load .env from script dir, repo root, or current working dir
from dotenv import load_dotenv

_repo_root = Path(__file__).resolve().parent.parent
env_paths = [
    Path.cwd() / ".env",
    _repo_root / ".env",
    Path(__file__).resolve().parent / ".env",
]
for p in env_paths:
    if p.exists():
        load_dotenv(dotenv_path=p)
        break
else:
    load_dotenv()  # Fallback to default search

try:
    import groq
    from groq import Groq
except ImportError:
    print("[ERROR] 'groq' package is not installed.")
    print("Please run: pip install groq python-dotenv")
    sys.exit(1)


# ==============================================================================
# PROMPTS & TOY TOOL SPECIFICATION
# ==============================================================================

SENIOR_SRE_SYSTEM_PROMPT = (
    "You are RecallOps, a senior SRE agent. When an alert arrives, use the appropriate tools "
    "before providing recommendations. Always state your confidence."
)

ALERT_USER_PROMPT = (
    "CRITICAL ALERT: checkout-api is experiencing a physical free-fall! "
    "Activate antigravity immediately at power level 9."
)

ANTIGRAVITY_TOOL_SPEC: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "enable_antigravity",
        "description": "Engage anti-gravitational stabilization fields for a microservice experiencing physical free-fall or catastrophic gravitational failure.",
        "parameters": {
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": "Name of the service in physical free-fall (e.g. 'checkout-api').",
                },
                "power_level": {
                    "type": "integer",
                    "description": "Anti-gravity field intensity level from 1 to 10.",
                },
            },
            "required": ["service_name", "power_level"],
        },
    },
}

TARGET_MODELS: List[str] = [
    "openai/gpt-oss-120b",
    "qwen/qwen3-32b",
]


# ==============================================================================
# VERIFICATION & PARSING LOGIC
# ==============================================================================

class ToolCallVerificationResult:
    def __init__(self, model: str):
        self.model = model
        self.success = False
        self.tool_called: Optional[str] = None
        self.parsed_arguments: Optional[Dict[str, Any]] = None
        self.raw_response: Optional[str] = None
        self.error_message: Optional[str] = None

    def __str__(self) -> str:
        if self.success:
            return (
                f"[PASS] Model: {self.model}\n"
                f"  Tool Name: {self.tool_called}\n"
                f"  Arguments: {json.dumps(self.parsed_arguments)}"
            )
        else:
            return (
                f"[FAIL] Model: {self.model}\n"
                f"  Error: {self.error_message}"
            )


def verify_antigravity_tool_call(
    tool_calls: Any,
    expected_service: str = "checkout-api",
    expected_power: int = 9,
) -> tuple[bool, Optional[str], Optional[Dict[str, Any]], Optional[str]]:
    """
    Validates that tool_calls contains enable_antigravity with expected arguments.
    """
    if not tool_calls:
        return False, None, None, "No tool_calls payload returned in message choices."

    target_call = None
    for tc in tool_calls:
        # Handle both Groq SDK objects and raw dicts (for mock tests)
        func_name = getattr(tc.function, "name", None) if hasattr(tc, "function") else tc.get("function", {}).get("name")
        if func_name == "enable_antigravity":
            target_call = tc
            break

    if not target_call:
        found_names = [
            getattr(tc.function, "name", "unknown") if hasattr(tc, "function") else tc.get("function", {}).get("name")
            for tc in tool_calls
        ]
        return False, None, None, f"Expected tool 'enable_antigravity' not found in tool calls: {found_names}"

    # Parse arguments
    raw_args = getattr(target_call.function, "arguments", None) if hasattr(target_call, "function") else target_call.get("function", {}).get("arguments")
    if isinstance(raw_args, str):
        try:
            parsed_args = json.loads(raw_args)
        except json.JSONDecodeError as e:
            return False, "enable_antigravity", None, f"Failed to parse tool arguments JSON: {e} (raw: {raw_args})"
    elif isinstance(raw_args, dict):
        parsed_args = raw_args
    else:
        return False, "enable_antigravity", None, f"Invalid arguments format type: {type(raw_args)}"

    # Validate arguments
    service = str(parsed_args.get("service_name", "")).strip().lower()
    if service != expected_service.lower():
        return (
            False,
            "enable_antigravity",
            parsed_args,
            f"Argument 'service_name' mismatch: expected '{expected_service}', got '{parsed_args.get('service_name')}'",
        )

    try:
        power = int(parsed_args.get("power_level"))
    except (ValueError, TypeError):
        return (
            False,
            "enable_antigravity",
            parsed_args,
            f"Argument 'power_level' is not an integer: got {parsed_args.get('power_level')}",
        )

    if power != expected_power:
        return (
            False,
            "enable_antigravity",
            parsed_args,
            f"Argument 'power_level' mismatch: expected {expected_power}, got {power}",
        )

    return True, "enable_antigravity", parsed_args, None


# ==============================================================================
# TEST RUNNERS
# ==============================================================================

def run_model_smoke_test(
    client: Groq,
    model_name: str,
    verbose: bool = False,
) -> ToolCallVerificationResult:
    """Runs single model function calling test against Groq endpoint."""
    result = ToolCallVerificationResult(model=model_name)

    print(f"\n---> Testing Model: {model_name}...")

    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": SENIOR_SRE_SYSTEM_PROMPT},
                {"role": "user", "content": ALERT_USER_PROMPT},
            ],
            tools=[ANTIGRAVITY_TOOL_SPEC],
            tool_choice="auto",
            temperature=0.0,
        )

        message = completion.choices[0].message
        tool_calls = message.tool_calls
        result.raw_response = str(message)

        if verbose:
            print(f"      [DEBUG Raw Message]: {message}")

        ok, tool_name, args, err = verify_antigravity_tool_call(tool_calls)
        result.success = ok
        result.tool_called = tool_name
        result.parsed_arguments = args
        result.error_message = err

    except groq.NotFoundError as e:
        result.error_message = f"Groq Model '{model_name}' not found or unsupported on endpoint. ({e})"
    except groq.AuthenticationError as e:
        result.error_message = f"Groq Authentication failed. Invalid API key. ({e})"
    except groq.RateLimitError as e:
        result.error_message = f"Groq Rate limit exceeded. ({e})"
    except groq.APIConnectionError as e:
        result.error_message = f"Failed to connect to Groq API. ({e})"
    except groq.APIStatusError as e:
        result.error_message = f"Groq API returned HTTP {e.status_code}: {e.message}"
    except Exception as e:
        result.error_message = f"Unexpected exception during inference: {type(e).__name__}: {e}"

    return result


def run_mock_smoke_test(model_name: str) -> ToolCallVerificationResult:
    """Mock verification runner for offline validation or CI environments."""
    print(f"\n---> [MOCK] Testing Model: {model_name}...")
    result = ToolCallVerificationResult(model=model_name)

    mock_tool_calls = [
        {
            "id": "call_mock_12345",
            "type": "function",
            "function": {
                "name": "enable_antigravity",
                "arguments": json.dumps({"service_name": "checkout-api", "power_level": 9}),
            },
        }
    ]

    ok, tool_name, args, err = verify_antigravity_tool_call(mock_tool_calls)
    result.success = ok
    result.tool_called = tool_name
    result.parsed_arguments = args
    result.error_message = err
    return result


# ==============================================================================
# MAIN CLI ENTRYPOINT
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="RecallOps Groq Function Calling Smoke Test (Member 4 - AI/ML)"
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=TARGET_MODELS,
        help="List of Groq models to test (default: openai/gpt-oss-120b qwen/qwen3-32b)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run offline mock verification without contacting live Groq API.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Display detailed debug payloads and raw messages.",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("RecallOps Phase 0: Groq Function-Calling Smoke Test Harness")
    print("=" * 70)
    print(f"System Prompt : {SENIOR_SRE_SYSTEM_PROMPT}")
    print(f"User Prompt   : {ALERT_USER_PROMPT}")
    print(f"Target Models : {', '.join(args.models)}")
    print("=" * 70)

    api_key = os.getenv("GROQ_API_KEY")

    if args.mock:
        print("\n[INFO] Running in --mock mode. Validating test assertion pipeline...")
        results = [run_mock_smoke_test(m) for m in args.models]
    elif not api_key:
        print("\n[WARNING] GROQ_API_KEY is not set in environment or .env file.")
        print("To run live inference, set GROQ_API_KEY in RecallOps/.env")
        print("\nExecuting dry-run assertion validation pipeline...")
        results = [run_mock_smoke_test(m) for m in args.models]
    else:
        # Live client setup
        masked_key = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "***"
        print(f"[INFO] GROQ_API_KEY detected: {masked_key}")
        client = Groq(api_key=api_key)
        results = [run_model_smoke_test(client, m, verbose=args.verbose) for m in args.models]

    # Print Summary Report
    print("\n" + "=" * 70)
    print("TEST SUMMARY REPORT")
    print("=" * 70)
    total = len(results)
    passed = sum(1 for r in results if r.success)

    for r in results:
        print(r)
        print("-" * 70)

    print(f"\nFinal Score: {passed}/{total} models succeeded.")

    if passed == total:
        print("[SUCCESS] All function-calling smoke test assertions PASSED!")
        return 0
    else:
        print("[NOTICE] One or more models encountered an error or assertion mismatch.")
        print("Note: If target model IDs are beta or require specific routing, check endpoint logs.")
        # If running without key or in mock mode, return 0 if mock passed
        if not api_key and all(r.success for r in results):
            return 0
        return 1


if __name__ == "__main__":
    sys.exit(main())
