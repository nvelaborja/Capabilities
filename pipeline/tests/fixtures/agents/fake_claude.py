"""A stand-in for the `claude` command, so agent tests never use anyone's Claude plan or the network.

`claude auth status` prints $FAKE_CLAUDE_AUTH (a Claude Pro login by default). `claude -p …` reads the prompt from
stdin, logs the call (its arguments, prompt, and whether an API key was in its environment) to $FAKE_CLAUDE_LOG, and
plays the next scripted answer for its role from $FAKE_CLAUDE_SCRIPT: the proposer (given web tools) or the reviewer
(given none). An answer is one of:

    {"output": {...}, "searches": ["…"], "fetches": ["https://…"], "five_hour": 0.5}
    {"limit": true}        the plan's usage limit is reached
    {"error": "max_turns"} out of turns, no answer

The events printed are shaped like those of `claude -p --output-format stream-json --verbose` (Claude Code 2.1.330).
"""

import json
import os
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if argv[:2] == ["auth", "status"]:
        print(os.environ.get("FAKE_CLAUDE_AUTH") or json.dumps({
            "loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "pro", "email": "someone@example.com"}))
        return 0
    prompt = sys.stdin.read()
    role = "reviewer" if argv[argv.index("--tools") + 1] == "" else "proposer"
    with open(os.environ["FAKE_CLAUDE_LOG"], "a", encoding="utf-8") as log:
        log.write(json.dumps({"role": role, "argv": argv, "prompt": prompt,
                              "api_key": "ANTHROPIC_API_KEY" in os.environ}) + "\n")
    state_path = Path(os.environ["FAKE_CLAUDE_SCRIPT"] + ".state")
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    script = json.loads(Path(os.environ["FAKE_CLAUDE_SCRIPT"]).read_text())
    turn = state.get(role, 0)
    state[role] = turn + 1
    state_path.write_text(json.dumps(state))
    answer = script[role][turn]
    for event in events(answer):
        print(json.dumps(event))
    return 1 if answer.get("limit") and answer.get("exit") else 0


def events(answer: dict) -> list[dict]:
    model = "claude-opus-5-5"
    printed = [{"type": "system", "subtype": "init", "session_id": "fake-session", "model": model}]
    tools = [{"type": "tool_use", "name": "WebSearch", "input": {"query": query}} for query in answer.get("searches", [])]
    tools += [{"type": "tool_use", "name": "WebFetch", "input": {"url": url, "prompt": "Quote it."}}
              for url in answer.get("fetches", [])]
    if tools:
        printed.append({"type": "assistant", "message": {"model": model, "content": tools}})
    five_hour = 1.0 if answer.get("limit") else answer.get("five_hour", 0.25)
    status = "rejected" if answer.get("limit") else "allowed"
    printed.append({"type": "rate_limit_event", "rate_limit_info": {"status": status, "unifiedWindows": {
        "five_hour": {"utilization": five_hour, "status": status},
        "seven_day": {"utilization": answer.get("seven_day", 0.1), "status": "allowed"},
    }}})
    usage = {"input_tokens": 10, "output_tokens": 100, "cache_read_input_tokens": 1000,
             "cache_creation_input_tokens": 2000}
    if answer.get("limit"):
        printed.append({"type": "result", "subtype": "success", "is_error": True, "api_error_status": 429,
                        "result": "You've hit your limit · resets 3pm", "usage": usage})
    elif answer.get("error") == "max_turns":
        printed.append({"type": "result", "subtype": "error_max_turns", "is_error": True, "num_turns": 31, "usage": usage})
    else:
        printed.append({"type": "assistant", "message": {"model": model, "content": [
            {"type": "tool_use", "name": "StructuredOutput", "input": answer["output"]}]}})
        printed.append({"type": "result", "subtype": "success", "is_error": False, "num_turns": len(tools) + 2,
                        "duration_ms": 1234, "session_id": "fake-session", "total_cost_usd": 0.25, "usage": usage,
                        "result": json.dumps(answer["output"]), "structured_output": answer["output"]})
    return printed


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
