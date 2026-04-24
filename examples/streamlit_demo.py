"""Streamlit demo: Direct API vs CLI vs MCP, side by side.

Drives the same Tasks backend through all three integration paths from
Anthropic's "Building agents that reach production systems with MCP" and
surfaces the metrics that matter for an agent author:

  * round trips required to express the user's intent
  * how much schema knowledge the caller needs
  * how long the matching agent SKILL.md instructions have to be

Run:
    uv run --with streamlit --with httpx --with mcp \
        streamlit run examples/streamlit_demo.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

API_BASE_URL = "http://localhost:30080"
MCP_SERVER_URL = "http://localhost:30090/mcp"
OLLAMA_URL = "http://localhost:30100"
OLLAMA_MODEL = "qwen2.5:0.5b-instruct"
MAX_LOG_ENTRIES = 200

PATH_LABELS = ("Direct API", "CLI", "MCP")
PATH_COLORS = {
    "Direct API": "#6366f1",  # indigo
    "CLI": "#f59e0b",         # amber
    "MCP": "#10b981",         # emerald
}
PATH_ICONS = {
    "Direct API": "🔌",
    "CLI": "🖥️",
    "MCP": "🧩",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("mcp_demo")


def log_event(level: str, message: str, **fields: Any) -> None:
    """Log to stdout and to the in-app activity buffer."""
    rendered = message
    if fields:
        rendered = f"{message} | {json.dumps(fields, default=str)}"
    getattr(logger, level)(rendered)

    buffer = st.session_state.setdefault("activity_log", [])
    buffer.append(
        {
            "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "level": level.upper(),
            "message": rendered,
        }
    )
    del buffer[:-MAX_LOG_ENTRIES]


@dataclass
class CallTrace:
    label: str
    detail: str
    request_bytes: int = 0
    response_bytes: int = 0


@dataclass
class PathResult:
    output: dict[str, Any] | list[Any] | str
    traces: list[CallTrace] = field(default_factory=list)
    elapsed_ms: float = 0.0
    error: str | None = None
    preview: bool = False

    @property
    def total_request_bytes(self) -> int:
        return sum(trace.request_bytes for trace in self.traces)

    @property
    def total_response_bytes(self) -> int:
        return sum(trace.response_bytes for trace in self.traces)

    @property
    def wire_bytes(self) -> int:
        return self.total_request_bytes + self.total_response_bytes


def preview_direct_api_triage(title: str, assignee: str, priority: str) -> PathResult:
    body = {"title": title, "assignee": assignee, "priority": priority}
    estimated_response = json.dumps({
        "id": 0, "title": title, "assignee": assignee, "priority": priority,
        "status": "open", "note": None,
        "created_at": "2026-04-24T00:00:00Z",
        "updated_at": "2026-04-24T00:00:00Z",
    })
    trace = _trace_http(
        "POST", "/tasks", body, response_bytes=len(estimated_response),
    )
    return PathResult(
        output={"_preview": "would POST /tasks with this body", "body": body},
        traces=[trace],
        preview=True,
    )


def preview_cli_triage(title: str, assignee: str, priority: str) -> PathResult:
    payload = json.dumps({"title": title, "assignee": assignee, "priority": priority})
    cmd = (
        f"curl --silent --show-error --fail "
        f"-X POST {API_BASE_URL}/tasks "
        f"-H 'Content-Type: application/json' "
        f"-d {shlex.quote(payload)}"
    )
    estimated_response = json.dumps({
        "id": 0, "title": title, "assignee": assignee, "priority": priority,
        "status": "open", "note": None,
        "created_at": "2026-04-24T00:00:00Z",
        "updated_at": "2026-04-24T00:00:00Z",
    })
    return PathResult(
        output={"_preview": "would run this shell command", "cmd": cmd},
        traces=[
            CallTrace(
                label="shell", detail=cmd,
                request_bytes=len(cmd), response_bytes=len(estimated_response),
            ),
            CallTrace(
                label="parse",
                detail="python3 -c 'json.load(...)' to extract id",
            ),
        ],
        preview=True,
    )


def _trace_http(method: str, url: str, body: dict | None = None,
                response_bytes: int = 0) -> CallTrace:
    rendered = f"{method} {url}"
    request_bytes = len(method) + len(url) + 4  # rough request line
    if body is not None:
        body_json = json.dumps(body)
        rendered += f"\nbody: {body_json}"
        request_bytes += len(body_json)
    return CallTrace(
        label=f"HTTP {method}",
        detail=rendered,
        request_bytes=request_bytes,
        response_bytes=response_bytes,
    )


# --- Path 1: Direct API --------------------------------------------------------


def run_direct_api_triage(title: str, assignee: str, priority: str) -> PathResult:
    log_event("info", "Direct API: triage_new_task start",
              title=title, assignee=assignee, priority=priority)
    started = time.perf_counter()
    traces: list[CallTrace] = []
    try:
        with httpx.Client(base_url=API_BASE_URL, timeout=5.0) as client:
            create_body = {"title": title, "assignee": assignee, "priority": priority}
            log_event("info", "Direct API: POST /tasks", body=create_body)
            response = client.post("/tasks", json=create_body).raise_for_status()
            created = response.json()
            traces.append(_trace_http(
                "POST", "/tasks", create_body,
                response_bytes=len(response.content),
            ))
        elapsed = (time.perf_counter() - started) * 1000
        log_event("info", "Direct API: triage_new_task done",
                  task_id=created.get("id"), elapsed_ms=round(elapsed, 1))
        return PathResult(output=created, traces=traces, elapsed_ms=elapsed)
    except httpx.HTTPError as exc:
        log_event("error", "Direct API: triage failed", error=str(exc))
        return PathResult(output="", traces=traces, error=str(exc),
                          elapsed_ms=(time.perf_counter() - started) * 1000)


def run_direct_api_complete(task_id: int, note: str) -> PathResult:
    log_event("info", "Direct API: complete_task_with_note start",
              task_id=task_id, note=note)
    started = time.perf_counter()
    traces: list[CallTrace] = []
    try:
        with httpx.Client(base_url=API_BASE_URL, timeout=5.0) as client:
            status_body = {"status": "done"}
            log_event("info", "Direct API: PATCH status=done", task_id=task_id)
            status_resp = client.patch(
                f"/tasks/{task_id}", json=status_body
            ).raise_for_status()
            traces.append(_trace_http(
                "PATCH", f"/tasks/{task_id}", status_body,
                response_bytes=len(status_resp.content),
            ))

            note_body = {"note": note}
            log_event("info", "Direct API: PATCH note", task_id=task_id)
            note_resp = client.patch(
                f"/tasks/{task_id}", json=note_body
            ).raise_for_status()
            traces.append(_trace_http(
                "PATCH", f"/tasks/{task_id}", note_body,
                response_bytes=len(note_resp.content),
            ))
            final = note_resp.json()
        elapsed = (time.perf_counter() - started) * 1000
        log_event("info", "Direct API: complete_task_with_note done",
                  task_id=task_id, round_trips=2, elapsed_ms=round(elapsed, 1))
        return PathResult(output=final, traces=traces, elapsed_ms=elapsed)
    except httpx.HTTPError as exc:
        log_event("error", "Direct API: complete failed", error=str(exc))
        return PathResult(output="", traces=traces, error=str(exc),
                          elapsed_ms=(time.perf_counter() - started) * 1000)


# --- Path 2: CLI ---------------------------------------------------------------


def _run_shell(command: str) -> tuple[str, str]:
    completed = subprocess.run(
        command, shell=True, capture_output=True, text=True, timeout=10
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "shell command failed")
    return completed.stdout, completed.stderr


def run_cli_triage(title: str, assignee: str, priority: str) -> PathResult:
    log_event("info", "CLI: triage_new_task start",
              title=title, assignee=assignee, priority=priority)
    started = time.perf_counter()
    traces: list[CallTrace] = []
    payload = json.dumps({"title": title, "assignee": assignee, "priority": priority})
    create_cmd = (
        f"curl --silent --show-error --fail "
        f"-X POST {API_BASE_URL}/tasks "
        f"-H 'Content-Type: application/json' "
        f"-d {shlex.quote(payload)}"
    )
    log_event("info", "CLI: shell exec", cmd=create_cmd)
    try:
        stdout, _ = _run_shell(create_cmd)
        traces.append(CallTrace(
            label="shell", detail=create_cmd,
            request_bytes=len(create_cmd), response_bytes=len(stdout),
        ))
        traces.append(CallTrace(
            label="parse",
            detail="python3 -c 'json.load(...)' to extract id",
        ))
        created = json.loads(stdout)
        elapsed = (time.perf_counter() - started) * 1000
        log_event("info", "CLI: triage_new_task done",
                  task_id=created.get("id"), elapsed_ms=round(elapsed, 1))
        return PathResult(output=created, traces=traces, elapsed_ms=elapsed)
    except Exception as exc:  # noqa: BLE001 - surface to UI
        log_event("error", "CLI: triage failed", error=str(exc))
        return PathResult(output="", traces=traces, error=str(exc),
                          elapsed_ms=(time.perf_counter() - started) * 1000)


def run_cli_complete(task_id: int, note: str) -> PathResult:
    log_event("info", "CLI: complete_task_with_note start",
              task_id=task_id, note=note)
    started = time.perf_counter()
    traces: list[CallTrace] = []
    status_payload = json.dumps({"status": "done"})
    note_payload = json.dumps({"note": note})

    status_cmd = (
        f"curl --silent --show-error --fail "
        f"-X PATCH {API_BASE_URL}/tasks/{task_id} "
        f"-H 'Content-Type: application/json' -d {shlex.quote(status_payload)}"
    )
    note_cmd = (
        f"curl --silent --show-error --fail "
        f"-X PATCH {API_BASE_URL}/tasks/{task_id} "
        f"-H 'Content-Type: application/json' -d {shlex.quote(note_payload)}"
    )
    try:
        log_event("info", "CLI: shell exec status", cmd=status_cmd)
        status_out, _ = _run_shell(status_cmd)
        traces.append(CallTrace(
            label="shell", detail=status_cmd,
            request_bytes=len(status_cmd), response_bytes=len(status_out),
        ))
        log_event("info", "CLI: shell exec note", cmd=note_cmd)
        stdout, _ = _run_shell(note_cmd)
        traces.append(CallTrace(
            label="shell", detail=note_cmd,
            request_bytes=len(note_cmd), response_bytes=len(stdout),
        ))
        elapsed = (time.perf_counter() - started) * 1000
        log_event("info", "CLI: complete_task_with_note done",
                  task_id=task_id, round_trips=2, elapsed_ms=round(elapsed, 1))
        return PathResult(output=json.loads(stdout), traces=traces, elapsed_ms=elapsed)
    except Exception as exc:  # noqa: BLE001
        log_event("error", "CLI: complete failed", error=str(exc))
        return PathResult(output="", traces=traces, error=str(exc),
                          elapsed_ms=(time.perf_counter() - started) * 1000)


# --- Path 3: MCP ---------------------------------------------------------------


async def _mcp_call(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    async with streamable_http_client(MCP_SERVER_URL) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            response = await session.call_tool(tool_name, arguments=arguments)
            return json.loads(response.content[0].text)


async def _mcp_list_tools() -> list[dict[str, str]]:
    async with streamable_http_client(MCP_SERVER_URL) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            return [
                {"name": tool.name, "description": (tool.description or "").splitlines()[0]}
                for tool in tools.tools
            ]


def run_mcp(tool_name: str, arguments: dict[str, Any]) -> PathResult:
    log_event("info", "MCP: call_tool start", tool=tool_name, arguments=arguments)
    started = time.perf_counter()
    request_payload = json.dumps({"name": tool_name, "arguments": arguments})
    try:
        result = asyncio.run(_mcp_call(tool_name, arguments))
        elapsed = (time.perf_counter() - started) * 1000
        log_event("info", "MCP: call_tool done",
                  tool=tool_name, round_trips=1, elapsed_ms=round(elapsed, 1))
        traces = [CallTrace(
            label="MCP tool call",
            detail=f"{tool_name}({json.dumps(arguments)})",
            request_bytes=len(request_payload),
            response_bytes=len(json.dumps(result)),
        )]
        return PathResult(output=result, traces=traces, elapsed_ms=elapsed)
    except Exception as exc:  # noqa: BLE001
        log_event("error", "MCP: call_tool failed", tool=tool_name, error=str(exc))
        traces = [CallTrace(
            label="MCP tool call",
            detail=f"{tool_name}({json.dumps(arguments)})",
            request_bytes=len(request_payload),
        )]
        return PathResult(output="", traces=traces, error=str(exc),
                          elapsed_ms=(time.perf_counter() - started) * 1000)


# --- Skill snippets ------------------------------------------------------------

SKILL_DIRECT_API = """\
# SKILL: complete-task-with-note (Direct API)

You can complete a task and attach a note via the Tasks HTTP API.

Steps:
1. PATCH /tasks/{id} with {"status": "done"}.
2. PATCH /tasks/{id} again with {"note": "<text>"}.

Schema notes:
- status enum: open | in_progress | done
- note is a free-form string
- 404 if id unknown, 400 if body empty, 422 on bad enum
- Treat the two PATCHes as non-transactional; the second can fail
  after the first succeeded. Re-run safely.
"""

SKILL_CLI = """\
# SKILL: complete-task-with-note (CLI)

Same workflow as the HTTP API, but you must:
- Shell-quote the JSON payload safely.
- Parse stdout with `python3 -c 'json.load(...)'` to recover ids.
- Map non-zero exit codes to user-facing errors yourself.
- Re-run failed PATCHes; there is no transactional guarantee.
"""

SKILL_MCP = """\
# SKILL: complete-task-with-note (MCP)

Call the `complete_task_with_note` tool with `task_id` and `note`.
The server handles status transitions, validation, and error mapping.
"""


# --- UI ------------------------------------------------------------------------


def _estimate_llm_tokens(skill_md: str) -> int:
    """Rough heuristic: 1 token per ~4 characters of skill text."""
    return max(1, len(skill_md) // 4)


def _record_run(
    api_result: PathResult, cli_result: PathResult, mcp_result: PathResult
) -> None:
    history = st.session_state.setdefault("run_history", [])
    timestamp = datetime.now().strftime("%H:%M:%S")
    for label, result in zip(
        PATH_LABELS, (api_result, cli_result, mcp_result)
    ):
        history.append({
            "run": len(history) // 3 + 1,
            "time": timestamp,
            "path": label,
            "round_trips": len(result.traces),
            "latency_ms": result.elapsed_ms,
            "wire_bytes": result.wire_bytes,
        })


def _comparison_chart(
    api_result: PathResult, cli_result: PathResult, mcp_result: PathResult,
    skills: dict[str, str],
) -> go.Figure:
    raw_values = {
        "Round trips": [
            len(api_result.traces),
            len(cli_result.traces),
            len(mcp_result.traces),
        ],
        "Latency (ms)": [
            round(api_result.elapsed_ms, 1),
            round(cli_result.elapsed_ms, 1),
            round(mcp_result.elapsed_ms, 1),
        ],
        "Wire bytes": [
            api_result.wire_bytes,
            cli_result.wire_bytes,
            mcp_result.wire_bytes,
        ],
        "Skill tokens\u2248": [
            _estimate_llm_tokens(skills["Direct API"]),
            _estimate_llm_tokens(skills["CLI"]),
            _estimate_llm_tokens(skills["MCP"]),
        ],
    }
    rows = []
    for metric_name, values in raw_values.items():
        worst = max(values) or 1
        for label, value in zip(PATH_LABELS, values):
            rows.append({
                "metric": metric_name,
                "path": label,
                "relative": 100 * value / worst,
                "label": str(value),
            })
    frame = pd.DataFrame(rows)
    figure = px.bar(
        frame, x="metric", y="relative", color="path",
        barmode="group", text="label",
        color_discrete_map=PATH_COLORS,
        category_orders={
            "path": list(PATH_LABELS),
            "metric": list(raw_values.keys()),
        },
    )
    figure.update_traces(textposition="outside", cliponaxis=False)
    figure.update_layout(
        height=360,
        margin={"t": 30, "b": 30, "l": 50, "r": 10},
        font={"size": 13},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02,
                "title": ""},
        yaxis_title="% of worst path (shorter = better)",
        xaxis_title="",
    )
    figure.update_yaxes(range=[0, 115], ticksuffix="%")
    return figure


def _wire_bytes_chart(
    api_result: PathResult, cli_result: PathResult, mcp_result: PathResult,
) -> go.Figure:
    rows = []
    for label, result in zip(
        PATH_LABELS, (api_result, cli_result, mcp_result)
    ):
        rows.append({
            "path": label, "direction": "request →",
            "bytes": result.total_request_bytes,
        })
        rows.append({
            "path": label, "direction": "← response",
            "bytes": result.total_response_bytes,
        })
    frame = pd.DataFrame(rows)
    figure = px.bar(
        frame, x="path", y="bytes", color="direction",
        barmode="stack", text="bytes",
        category_orders={"path": list(PATH_LABELS)},
        color_discrete_sequence=["#94a3b8", "#475569"],
    )
    figure.update_traces(textposition="inside")
    figure.update_layout(
        height=300,
        margin={"t": 30, "b": 30, "l": 30, "r": 10},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
        yaxis_title="bytes",
        xaxis_title="",
    )
    return figure


def _history_chart(history: list[dict[str, Any]]) -> go.Figure:
    frame = pd.DataFrame(history)
    figure = px.line(
        frame, x="run", y="latency_ms", color="path", markers=True,
        color_discrete_map=PATH_COLORS,
        category_orders={"path": list(PATH_LABELS)},
    )
    figure.update_layout(
        height=260,
        margin={"t": 30, "b": 30, "l": 40, "r": 10},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
        yaxis_title="latency (ms)",
        xaxis_title="run #",
    )
    return figure


def _render_path_card(
    column: Any, label: str, result: PathResult,
    code_snippet: str, skill_md: str,
) -> None:
    icon = PATH_ICONS[label]
    color = PATH_COLORS[label]
    column.markdown(
        f"<div style='border-left:4px solid {color};padding:6px 12px;"
        f"margin-bottom:8px;background:rgba(255,255,255,0.02);"
        f"border-radius:4px;'>"
        f"<span style='font-size:1.3em;font-weight:600;'>"
        f"{icon} {label}</span></div>",
        unsafe_allow_html=True,
    )
    if result.preview:
        column.caption("👁️ preview only — not executed")

    metric_cols = column.columns(2)
    metric_cols[0].metric("Round trips", len(result.traces))
    latency_label = "—" if result.preview else f"{result.elapsed_ms:.0f} ms"
    metric_cols[1].metric("Latency", latency_label)

    metric_cols2 = column.columns(2)
    metric_cols2[0].metric("Wire bytes", result.wire_bytes)
    metric_cols2[1].metric(
        "Skill tokens≈", _estimate_llm_tokens(skill_md),
    )

    tab_trace, tab_result, tab_code, tab_skill = column.tabs(
        ["Trace", "Result", "Code", "SKILL.md"]
    )
    with tab_trace:
        for trace in result.traces:
            st.markdown(f"**{trace.label}** · "
                        f"{trace.request_bytes + trace.response_bytes} B")
            st.code(
                trace.detail,
                language="bash" if trace.label == "shell" else "text",
            )
    with tab_result:
        if result.error:
            st.error(result.error)
        else:
            st.json(result.output)
    with tab_code:
        st.code(code_snippet, language="python")
    with tab_skill:
        st.code(skill_md, language="markdown")


def _list_open_tasks_via_api() -> list[dict[str, Any]]:
    with httpx.Client(base_url=API_BASE_URL, timeout=5.0) as client:
        return client.get("/tasks", params={"status": "open"}).raise_for_status().json()


def _list_all_tasks_via_api() -> list[dict[str, Any]]:
    with httpx.Client(base_url=API_BASE_URL, timeout=5.0) as client:
        return client.get("/tasks").raise_for_status().json()


def _reset_demo_data_via_api() -> list[dict[str, Any]]:
    with httpx.Client(base_url=API_BASE_URL, timeout=5.0) as client:
        return client.post("/admin/reset").raise_for_status().json()


def render_reset_control() -> None:
    if st.button("🔄 Reset demo data", help="Wipe and re-seed tasks"):
        try:
            _reset_demo_data_via_api()
            log_event("info", "Demo data reset via /admin/reset")
            st.session_state["run_history"] = []
            st.session_state.pop("selected_task_id", None)
            st.rerun()
        except httpx.HTTPError as exc:
            st.error(f"Reset failed: {exc}")


def _render_lesson_banner() -> None:
    st.markdown(
        """
<div style='border-left:4px solid #10b981;padding:10px 16px;
background:rgba(16,185,129,0.08);border-radius:6px;margin-bottom:8px;'>
<b>What you're learning</b><br/>
<span style='color:#cbd5e1;font-size:0.92em;'>
From Anthropic's <a href='https://claude.com/blog/building-agents-that-reach-production-systems-with-mcp'>
<i>Building agents that reach production systems with MCP</i></a> &mdash; the same
user intent (“complete a task with a closing note”) is run through three
integration paths against one backend. The lesson:
<b>group tools around intent, not endpoints.</b>
A single MCP tool collapses what would otherwise be multiple HTTP calls,
shrinks the agent's <code>SKILL.md</code>, and cuts the prompt-token cost of
<i>every turn</i> of the agent loop.
</span>
</div>
        """,
        unsafe_allow_html=True,
    )


def _ensure_open_task() -> dict[str, Any]:
    """Always return a fresh open task. Reset demo data if all are done."""
    tasks = _list_all_tasks_via_api()
    open_tasks = [task for task in tasks if task["status"] != "done"]
    if open_tasks:
        return open_tasks[0]
    log_event("info", "All tasks done; auto-resetting demo data")
    fresh = _reset_demo_data_via_api()
    return next(task for task in fresh if task["status"] != "done")


def render_complete_scenario() -> None:
    st.subheader("🎯 Same intent, three integration paths")
    st.caption(
        "Click the button. The same task is completed three ways: a Direct "
        "API client, a CLI shell, and an MCP tool call. Watch the round trips, "
        "bytes on the wire, and — below — the prompt tokens a real LLM spends "
        "to plan each one."
    )

    note = st.text_input(
        "Closing note (the same note is used for all three paths)",
        value="rolled back the bad release",
    )
    st.session_state["selected_task_note"] = note

    if not st.button(
        "▶️ Run the comparison",
        type="primary", use_container_width=True,
    ):
        return

    try:
        target = _ensure_open_task()
    except httpx.HTTPError as exc:
        st.error(f"Could not reach Tasks API at {API_BASE_URL}: {exc}")
        return

    task_id = target["id"]
    st.session_state["selected_task_id"] = task_id
    st.caption(
        f"Operating on task **#{task_id} · {target['title']}** "
        f"(assignee: {target['assignee']}, priority: {target['priority']})."
    )

    api_result = run_direct_api_complete(task_id, note)
    cli_result = run_cli_complete(task_id, note)
    mcp_result = run_mcp(
        "complete_task_with_note", {"task_id": task_id, "note": note}
    )
    _record_run(api_result, cli_result, mcp_result)

    skills = {
        "Direct API": SKILL_DIRECT_API,
        "CLI": SKILL_CLI,
        "MCP": SKILL_MCP,
    }

    st.markdown("#### 📊 Side-by-side metrics")
    chart_cols = st.columns([2, 1])
    chart_cols[0].plotly_chart(
        _comparison_chart(api_result, cli_result, mcp_result, skills),
        use_container_width=True,
        config={"displayModeBar": False},
    )
    chart_cols[1].plotly_chart(
        _wire_bytes_chart(api_result, cli_result, mcp_result),
        use_container_width=True,
        config={"displayModeBar": False},
    )

    history = st.session_state.get("run_history", [])
    if len(history) >= 6:
        st.markdown("#### 📈 Latency across runs (this session)")
        st.plotly_chart(
            _history_chart(history),
            use_container_width=True,
            config={"displayModeBar": False},
        )

    st.markdown("#### 🔍 Per-path detail")
    columns = st.columns(3)
    _render_path_card(
        columns[0], "Direct API", api_result,
        'client.patch(f"/tasks/{id}", json={"status": "done"})\n'
        'client.patch(f"/tasks/{id}", json={"note": note})',
        SKILL_DIRECT_API,
    )
    _render_path_card(
        columns[1], "CLI", cli_result,
        'curl -X PATCH $API/tasks/$id -d \'{"status":"done"}\'\n'
        'curl -X PATCH $API/tasks/$id -d \'{"note":"..."}\'',
        SKILL_CLI,
    )
    _render_path_card(
        columns[2], "MCP", mcp_result,
        'session.call_tool(\n'
        '    "complete_task_with_note",\n'
        '    {"task_id": id, "note": note},\n'
        ')',
        SKILL_MCP,
    )

    saved_trips = len(api_result.traces) - len(mcp_result.traces)
    saved_bytes = api_result.wire_bytes - mcp_result.wire_bytes
    saved_pct = (
        100 * saved_bytes / api_result.wire_bytes
        if api_result.wire_bytes else 0
    )
    st.success(
        f"🎯 MCP saved **{saved_trips} round trip** and "
        f"**{saved_bytes} bytes ({saved_pct:.0f}%)** vs the Direct API — "
        "same outcome, smaller agent surface."
    )
    st.caption(
        "⚠️ MCP latency includes a fresh streamable-http session handshake. "
        "Production agents reuse the session across calls and amortize this "
        "cost to near zero."
    )


def render_discovery_panel() -> None:
    st.subheader("Tool discovery (MCP only)")
    st.caption(
        "MCP clients learn the tool surface at runtime. Direct API and CLI "
        "callers must be told out-of-band — usually in a long SKILL.md."
    )
    if st.button("List MCP tools"):
        try:
            tools = asyncio.run(_mcp_list_tools())
        except Exception as exc:  # noqa: BLE001
            st.error(f"MCP server unreachable at {MCP_SERVER_URL}: {exc}")
            return
        st.table(tools)


def _ollama_chat(system_prompt: str, user_prompt: str,
                 model: str = OLLAMA_MODEL) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 256},
    }
    with httpx.Client(timeout=120.0) as client:
        response = client.post(f"{OLLAMA_URL}/api/chat", json=payload)
        response.raise_for_status()
        return response.json()


def _ollama_health() -> tuple[bool, list[str]]:
    try:
        with httpx.Client(timeout=2.0) as client:
            tags = client.get(f"{OLLAMA_URL}/api/tags").raise_for_status().json()
        names = [model["name"] for model in tags.get("models", [])]
        return True, names
    except httpx.HTTPError:
        return False, []


def _plan_with_skill(label: str, skill_md: str, goal: str) -> dict[str, Any]:
    system = (
        "You are an automation agent. You are given a SKILL document that "
        "describes ONE way to accomplish tasks. Read it, then output a "
        "concise step-by-step PLAN to satisfy the user's goal using only "
        "what the SKILL describes. Do not execute anything. Output plain "
        "text, no markdown headings.\n\n"
        f"SKILL DOCUMENT:\n{skill_md}"
    )
    started = time.perf_counter()
    log_event("info", f"Ollama: plan via {label}", goal=goal,
              skill_chars=len(skill_md))
    raw = _ollama_chat(system_prompt=system, user_prompt=goal)
    elapsed_ms = (time.perf_counter() - started) * 1000
    plan_text = raw.get("message", {}).get("content", "").strip()
    prompt_tokens = raw.get("prompt_eval_count", 0)
    response_tokens = raw.get("eval_count", 0)
    log_event(
        "info", f"Ollama: plan via {label} done",
        prompt_tokens=prompt_tokens, response_tokens=response_tokens,
        elapsed_ms=round(elapsed_ms, 1),
    )
    return {
        "plan": plan_text,
        "prompt_tokens": prompt_tokens,
        "response_tokens": response_tokens,
        "elapsed_ms": elapsed_ms,
    }


def _llm_comparison_chart(
    plans: dict[str, dict[str, Any]], skills: dict[str, str],
) -> go.Figure:
    raw_values = {
        "Prompt tokens": [
            plans["Direct API"]["prompt_tokens"],
            plans["CLI"]["prompt_tokens"],
            plans["MCP"]["prompt_tokens"],
        ],
        "Response tokens": [
            plans["Direct API"]["response_tokens"],
            plans["CLI"]["response_tokens"],
            plans["MCP"]["response_tokens"],
        ],
        "Latency (ms)": [
            round(plans["Direct API"]["elapsed_ms"]),
            round(plans["CLI"]["elapsed_ms"]),
            round(plans["MCP"]["elapsed_ms"]),
        ],
        "Skill chars": [
            len(skills["Direct API"]),
            len(skills["CLI"]),
            len(skills["MCP"]),
        ],
    }
    rows = []
    for metric_name, values in raw_values.items():
        worst = max(values) or 1
        for label, value in zip(PATH_LABELS, values):
            rows.append({
                "metric": metric_name,
                "path": label,
                "relative": 100 * value / worst,
                "label": str(value),
            })
    frame = pd.DataFrame(rows)
    figure = px.bar(
        frame, x="metric", y="relative", color="path",
        barmode="group", text="label",
        color_discrete_map=PATH_COLORS,
        category_orders={
            "path": list(PATH_LABELS),
            "metric": list(raw_values.keys()),
        },
    )
    figure.update_traces(textposition="outside", cliponaxis=False)
    figure.update_layout(
        height=360,
        margin={"t": 30, "b": 30, "l": 50, "r": 10},
        font={"size": 13},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02,
                "title": ""},
        yaxis_title="% of worst path (shorter = better)",
        xaxis_title="",
    )
    figure.update_yaxes(range=[0, 115], ticksuffix="%")
    return figure


def render_llm_panel() -> None:
    st.subheader("Real LLM in the loop (Ollama on Kind)")
    st.caption(
        f"Feeds each path's SKILL.md as the system prompt to a local "
        f"`{OLLAMA_MODEL}` running in the cluster, then asks the model to "
        "produce a plan for the same goal. Compares prompt-token cost and "
        "wall-clock latency for the *exact same intent*."
    )

    healthy, models = _ollama_health()
    if not healthy:
        st.warning(
            f"Ollama not reachable at {OLLAMA_URL}. Run `make deploy` to "
            "provision it, then `make pull-model` to download the weights."
        )
        return
    if OLLAMA_MODEL not in models:
        st.warning(
            f"Model `{OLLAMA_MODEL}` not present (loaded models: "
            f"{models or 'none'}). Run `make pull-model` first."
        )
        return

    selected_id = st.session_state.get("selected_task_id")
    selected_note = st.session_state.get(
        "selected_task_note", "rolled back the bad release"
    )
    default_goal = (
        f"Mark task #{selected_id} as done and add the note '{selected_note}'."
        if selected_id
        else "Mark task #2 as done and add the note 'rolled back the bad release'."
    )
    goal = st.text_input("User goal", value=default_goal)
    if selected_id:
        st.caption(
            f"Goal auto-synced to the task selected above (#{selected_id}). "
            "Edit it freely."
        )
    if not st.button("Ask the local LLM (3 plans, one per skill)"):
        return

    with st.spinner(f"Calling {OLLAMA_MODEL} three times..."):
        plans = {}
        for label, skill in (
            ("Direct API", SKILL_DIRECT_API),
            ("CLI", SKILL_CLI),
            ("MCP", SKILL_MCP),
        ):
            try:
                plans[label] = _plan_with_skill(label, skill, goal)
            except httpx.HTTPError as exc:
                log_event("error", f"Ollama: {label} failed", error=str(exc))
                plans[label] = {"error": str(exc)}

    skill_lookup = {
        "Direct API": SKILL_DIRECT_API,
        "CLI": SKILL_CLI,
        "MCP": SKILL_MCP,
    }
    if all("prompt_tokens" in plan for plan in plans.values()):
        st.markdown("#### 📊 LLM cost side-by-side")
        st.plotly_chart(
            _llm_comparison_chart(plans, skill_lookup),
            use_container_width=True,
            config={"displayModeBar": False},
        )

    st.markdown("#### 🔍 Per-path plans")
    columns = st.columns(3)
    for column, label in zip(columns, ("Direct API", "CLI", "MCP")):
        column.markdown(f"### {label}")
        plan = plans[label]
        if "error" in plan:
            column.error(plan["error"])
            continue
        skill = skill_lookup[label]
        metric_cols = column.columns(3)
        metric_cols[0].metric("Prompt tokens", plan["prompt_tokens"])
        metric_cols[1].metric("Response tokens", plan["response_tokens"])
        metric_cols[2].metric("Latency (ms)", f"{plan['elapsed_ms']:.0f}")
        column.caption(
            f"Skill chars: {len(skill)} \u00b7 char ratio vs MCP: "
            f"{len(skill) / max(1, len(SKILL_MCP)):.1f}\u00d7"
        )
        with column.expander("LLM plan", expanded=True):
            st.write(plan["plan"] or "(empty response)")

    if all("prompt_tokens" in plan for plan in plans.values()):
        mcp_tokens = plans["MCP"]["prompt_tokens"]
        api_tokens = plans["Direct API"]["prompt_tokens"]
        cli_tokens = plans["CLI"]["prompt_tokens"]
        st.success(
            f"Prompt tokens fed to the model \u2014 "
            f"Direct API: **{api_tokens}** \u00b7 CLI: **{cli_tokens}** \u00b7 "
            f"MCP: **{mcp_tokens}**. "
            f"At cloud LLM pricing this is the cost of *every single turn* "
            f"of the agent loop."
        )


def render_takeaways() -> None:
    st.subheader("📖 Lessons from the article")
    st.markdown(
        """
From *[Building agents that reach production systems with MCP](https://claude.com/blog/building-agents-that-reach-production-systems-with-mcp)*:

1. **Three paths exist for connecting agents to systems** — Direct API, CLI,
   and MCP. Each makes sense somewhere; the question is whether there is a
   common layer between agents and services, and how far that layer reaches.
2. **Production agents run in the cloud**, and the systems they reach are
   cloud-hosted too. MCP is the only path that gives you that reach with
   standardized auth, discovery, and rich semantics.
3. **Group tools around intent, not endpoints.** Fewer, well-described tools
   beat exhaustive API mirrors — `complete_task_with_note(id, note)` beats
   chaining `PATCH /tasks/{id}` twice. The demo above proves it on real wire
   bytes and real prompt tokens.
4. **Skills and MCP are complementary.** MCP gives the agent access to tools;
   the `SKILL.md` teaches it the procedural knowledge of how to use them. The
   intent-grouped MCP tool needs a *much* shorter skill, which means a
   smaller prompt every turn.
        """
    )


def main() -> None:
    st.set_page_config(
        page_title="Agent skills · MCP vs CLI vs API",
        page_icon="🧩",
        layout="wide",
    )

    st.markdown(
        "<h1 style='margin-bottom:0'>🧩 Agent integration paths</h1>"
        "<p style='color:#94a3b8;margin-top:4px;'>"
        "Same backend, three integration styles — visualized side by side."
        "</p>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "Driven by the patterns in "
        "[*Building agents that reach production systems with MCP*]"
        "(https://claude.com/blog/building-agents-that-reach-production-systems-with-mcp)."
    )

    with st.sidebar:
        st.header("Cluster endpoints")
        st.code(
            f"Tasks API   {API_BASE_URL}\n"
            f"MCP server  {MCP_SERVER_URL}\n"
            f"Ollama      {OLLAMA_URL}  ({OLLAMA_MODEL})",
            language="text",
        )
        st.markdown(
            "Need to bring it up?\n\n"
            "```bash\nmake deploy\nmake pull-model\n```\n\n"
            "Tear it down with `make destroy`."
        )
        st.divider()
        st.subheader("Demo data")
        render_reset_control()
        st.caption(
            "Each comparison run completes one task. Reset to start over "
            "with a fresh batch of three open tasks."
        )
        st.divider()
        st.subheader("Activity log")
        log_entries = st.session_state.get("activity_log", [])
        if not log_entries:
            st.caption("Click any button to see live activity here.")
        else:
            if st.button("Clear log"):
                st.session_state["activity_log"] = []
                st.rerun()
            for entry in reversed(log_entries[-50:]):
                icon = "❌" if entry["level"] == "ERROR" else "•"
                st.text(f"{icon} {entry['time']} {entry['message']}")

    render_discovery_panel()
    st.divider()
    _render_lesson_banner()
    render_complete_scenario()
    st.divider()
    render_llm_panel()
    st.divider()
    render_takeaways()


if __name__ == "__main__":
    main()
