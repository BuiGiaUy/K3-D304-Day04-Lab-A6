# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A teaching lab (AI20k Day 04, K3 cohort). Students build a tool-calling research agent in `starter_v0/` and improve its **prompt + tool declarations** across versions (`v0` → `v3`), using real API runs as evidence. `README.md` is the student brief (Vietnamese); `TOOL-SETUP.md` is the per-API key/smoke-test guide.

There is no test suite. **The eval runner is the test suite** — every "does this work" question is answered by running `run_eval.py` against a live provider.

## Commands

All commands run from `starter_v0/`.

```powershell
# setup (Windows)
py -3 -m venv .venv; .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }   # never overwrite an existing .env

# does the provider return structured tool calls at all?
python scripts/preflight_provider.py --provider openrouter

# the "test suite" — one run per version; writes runs/<run_id>.json
python run_eval.py --provider openrouter --version v0 --suite base  --eval-cases data/eval_base.json
python run_eval.py --provider openrouter --version v3 --suite group --eval-cases data/eval_group.json
python run_eval.py --provider openrouter --version v3 --suite extension --eval-cases data/eval_research_extension.json

# interactive multi-round agent; writes transcripts/*.transcript.json
python chat.py --provider openrouter --version v3

# flatten run JSON into a per-case CSV
python scripts/parse_runs.py runs/ --output analysis/base_runs.csv
```

Running a single eval case: there is no `--case` flag. Copy the case into a scratch JSON with the same envelope (`dataset_id`, `cases: [...]`) and pass it via `--eval-cases`.

Testing one tool implementation directly (bypasses the model, spends only that tool's quota):

```powershell
python -c "from pathlib import Path; from env_loader import load_lab_env; load_lab_env(Path.cwd()); from tools import TOOL_FUNCTIONS as T; r=T['lookup']('AI', max_results=1); print({'error': r.get('error'), 'n': len(r.get('items') or [])})"
```

`--provider` is one of `openrouter | openai | anthropic | gemini` and must be passed on every command. Every eval and chat run hits real APIs and burns quota.

## Architecture

Two entrypoints share one substrate but implement **different loops** — this is deliberate, not duplication:

- `run_eval.py` → `agent.py::ResearchAgent.run()` — **single round**, forces `tool_choice="required"` unless the case expects `no_tool`. It grades the *first* set of tool calls; the loop must not continue, or grading would see downstream calls.
- `chat.py::run_model_tool_loop()` — **multi-round** (default 4), feeds tool results back as a `TOOL_RESULTS_JSON:` user message. Any UI (`app.py`, not provided by the starter — teams build it) must reuse this function rather than write a third loop, so UI/CLI/eval share prompt + declarations.

Shared substrate:

- `providers/` — each provider normalizes its vendor API to `ModelResponse{text, tool_calls[ToolCall{name,args}]}` (`providers/base.py`). `OpenRouterProvider` subclasses `OpenAIProvider` with a different base URL and `default_model`. Add a provider by adding a class + a branch in `make_provider()`, and to the `choices=` list in all three CLIs.
- `tools/` — one folder per tool: `TOOL.md` (YAML frontmatter contract, see `tools/README.md`) + self-contained `tool.py`. `tools/__init__.py` holds `TOOL_FUNCTIONS`, the single registry all entrypoints import.
- `artifacts/system_prompt.md` + `artifacts/tools.yaml` — the two files that are the actual subject of the lab. `tools.yaml` is loaded and converted to OpenAI function-calling shape by `to_openai_tools()`.
- `versioning.py` — SHA-256 hashes both artifact files into `artifact_version = "<label>+p<12>+t<12>"`, stamped into every run JSON and transcript. This is what makes a claimed "v2 improvement" verifiable.
- `env_loader.py` — hand-rolled dotenv, `override=True` by default. Loaded at import time in `chat.py`/`run_eval.py`; `DAY04_ENV_FILE` redirects to an external `.env`.

### Contracts to preserve

- **Tool return shape.** Tools never raise. Success returns a dict with `items` (research tools) or tool-specific fields; failure returns `_shared.err(name, exc)` → `{tool, error, message}`. Callers check `error is None`, so swallowing the error key breaks every smoke test in `TOOL-SETUP.md`.
- **`awaiting_user` is the pause protocol.** `chat.py` detects the clarification tool by `result["awaiting_user"] is True`, deliberately *not* by tool name, so teams can rename `clarify` freely. Preserve that flag on any clarification-style tool.
- **`confirmed=False` is the action boundary.** `send` returns `{"status": "needs_confirmation"}` without sending. Base eval grades this path via `clarify(response_type="yes_no")`; keep Telegram credentials unset during any `run_eval`.
- **Function names ≠ tool names.** Implementations keep descriptive names (`web_search`, `get_user_tweets`, `ask_user`); the registry keys (`lookup`, `timeline`, `clarify`) are what the model and the eval see. Tool folder names are intentionally vague — that vagueness is the lab exercise.

### Renaming a tool requires a full sync

`run_eval.py::validate_expected_tools()` hard-fails with `not declared in tools.yaml` / `no implementation` if these drift. Update all of: `artifacts/tools.yaml` → `tools/__init__.py` (`TOOL_FUNCTIONS`) → `tools/<name>/TOOL.md` → `artifacts/system_prompt.md` → `data/eval_base.json` → `data/eval_research_extension.json` → `data/eval_group.json` → `artifacts/REPORT.md`.

### Eval grading semantics (`run_eval.py`)

- Args are compared as a **subset** — only keys listed in `expect.args` are checked; extra actual args are ignored. `missing_fields` and `constraints` compare as subsets-of-sets; everything else is lowercase/strip-normalized (`normalize_value`).
- Expected calls are matched to actual calls by name, then by `best_arg_match` (most matching arg keys wins). Leftover actual calls become `extra_tool_call` failures.
- Multi-turn cases are **flattened into one synthetic user message** (`case_messages`) — prior turns become context lines, only the last turn is graded. So the last element of `turns` must be the user turn under test.
- `summary` excludes `failure_type == "provider_error"` cases from accuracy denominators. A run is only reportable when `provider_error_cases == 0` and `measured_cases == total_cases`. Routing PASS does *not* mean the tool executed successfully — `results[*].tool_results` must be reviewed separately.

## Working rules for this repo

- Never overwrite an existing `.env`, and never write keys, tokens, or a `.venv/` into the repo or into report/transcript files.
- `data/eval_base.json` and `data/eval_research_extension.json` are fixed: change only tool-name fields for a rename, never queries or expectations. `data/eval_group.json` is empty on purpose — teams author exactly 10 cases (5 `query`, 5 `turns`).
- `failure_type` must be one of `wrong_tool | wrong_arg_value | wrong_boundary | unnecessary_tool | out_of_scope | missing_info`; the loader raises otherwise. `phase` is always `"B"`.
- Per optimization round, change **one** hypothesis in `system_prompt.md` or `tools.yaml`, run one eval, then append a row to `artifacts/version_log.csv` (header defines the columns). Don't re-run identical artifacts under three version labels.
- `artifacts/system_prompt.md` ships deliberately bad (tells the agent never to clarify, to guess handles/URLs, to send without confirming). Do not "fix" it unprompted — rewriting it is the student's exercise.
- `starter_v0/` is the submission root; a `solution/` referenced in the README is not present in this repo.
