# MCP Production PoC

[![Python](https://img.shields.io/badge/python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Kind](https://img.shields.io/badge/kind-v0.24+-326CE5?logo=kubernetes&logoColor=white)](https://kind.sigs.k8s.io/)
[![MCP](https://img.shields.io/badge/MCP-1.27-7c3aed)](https://modelcontextprotocol.io/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](#license)

> **A hands-on lab that proves why production agents converge on MCP — by deploying the same backend behind all three integration paths (Direct API, CLI, MCP) on a real Kubernetes cluster.**

Built to teach the patterns from Anthropic's [*Building agents that reach production systems with MCP*](https://claude.com/blog/building-agents-that-reach-production-systems-with-mcp).

---

## Architecture

```mermaid
flowchart TD
    subgraph clients["Agents / clients"]
        direction LR
        direct["<b>Path 1</b><br/>Direct API call<br/><i>httpx</i>"]
        cli["<b>Path 2</b><br/>CLI<br/><i>curl in shell</i>"]
        agent["<b>Path 3</b><br/>MCP client<br/><i>mcp SDK</i>"]
    end

    subgraph kind["Kind cluster: mcp-poc"]
        direction TB
        mcp["<b>MCP Server</b><br/>FastMCP · streamable-http<br/>NodePort :30090"]
        api[("<b>Tasks API</b><br/>FastAPI · :8000<br/>NodePort :30080")]
        mcp -- "intent-grouped tool calls" --> api
    end

    direct -- "HTTP" --> api
    cli -- "HTTP" --> api
    agent -- "MCP / streamable-http" --> mcp

    classDef client fill:#eef2ff,stroke:#4f46e5,stroke-width:1px,color:#1e1b4b;
    classDef service fill:#ecfdf5,stroke:#059669,stroke-width:1px,color:#064e3b;
    class direct,cli,agent client;
    class mcp,api service;
```

The Tasks API plays the role of "the production system." The MCP server wraps it with **intent-grouped tools** rather than mirroring its endpoints — the central design lesson of the article.

---

## Prerequisites

Pin these versions for a reproducible lab:

- [ ] **Docker Desktop** ≥ 4.30 — [macOS](https://docs.docker.com/desktop/install/mac-install/) · [Windows](https://docs.docker.com/desktop/install/windows-install/)
- [ ] **Kind** ≥ 0.24 — [install guide](https://kind.sigs.k8s.io/docs/user/quick-start/#installation)
- [ ] **kubectl** ≥ 1.31 — [install guide](https://kubernetes.io/docs/tasks/tools/)
- [ ] **uv** ≥ 0.5 — [install guide](https://docs.astral.sh/uv/getting-started/installation/)
- [ ] **Python** 3.12+ (only needed if you want to run the example clients locally)

> **Windows users:** run `scripts/*.sh` from Git Bash, WSL, or any POSIX shell. PowerShell users can invoke the same commands with `sh scripts/setup.sh`.

---

## Quickstart

```bash
# 0. (Optional) Verify required tools are installed
make check

# 1. Boot the cluster, build images, deploy everything
make deploy

# 2. Pull a small local LLM into the cluster (~400 MB, one-time)
make pull-model

# 3. Open the side-by-side Streamlit demo
make demo
```

Total time from zero to the demo: **under 5 minutes** on a warm Docker cache.

### `make demo` — the visual comparison

`make demo` boots a Streamlit app that drives the **same backend** through all
three paths against the same user intent (“complete a task with a closing
note”). It surfaces the metrics that matter for an agent author on **one
shared y-axis** so the wins read at a glance:

- **Round trips** per intent (`complete_task_with_note` is *2* over Direct
  API, *2* via CLI, **1** through MCP).
- **Latency (ms)** end-to-end for each path.
- **Wire bytes** (request + response) so you see the protocol overhead, not
  just the count, including a stacked request/response breakdown.
- **SKILL.md token cost** — how many prompt tokens the agent burns *every
  turn* just to remember how to use each path.
- **Real LLM in the loop** — a tiny `qwen2.5:0.5b-instruct` running *inside*
  the Kind cluster is fed each `SKILL.md` and asked to plan the same goal.
  The app charts the resulting prompt tokens, response tokens, latency, and
  skill character count side by side. This is the production cost lever the
  article cares about.
- **Runtime tool discovery** — only MCP exposes a self-describing tool list.

It is the most direct way to *see* why intent-grouped MCP tools shorten agent
skills and reduce the surface a model has to reason about.

### Poking each path manually (optional)

If you want to drive the paths directly instead of through the UI:

```bash
# Path 1 — Direct API call
uv run --python 3.12 --with httpx python examples/direct_api.py

# Path 2 — CLI
sh examples/cli_demo.sh

# Path 3 — MCP
uv run --python 3.12 --with mcp python examples/mcp_client.py
```

---

## What You'll See

The Streamlit demo opens at <http://localhost:8501>. After clicking
**▶️ Run the comparison** you get:

1. A **“What you're learning”** banner that ties the live numbers back to the
   article's intent-vs-endpoints lesson.
2. A grouped bar chart of **Round trips, Latency, Wire bytes, Skill tokens**
   on a shared 0–100% scale (worst path = 100%, raw values printed on top).
   MCP is visibly the shortest bar on every metric.
3. A stacked **request/response wire-bytes** chart per path.
4. Per-path detail cards with the actual code each path runs and the
   `SKILL.md` it needs.
5. A second “Real LLM in the loop” panel: prompt tokens, response tokens,
   latency, and skill chars compared on the same normalized scale, plus the
   plan the local model produced for each path.

Notice how the MCP client never touches HTTP semantics or endpoint paths —
it only speaks **intents**.

---

## Project Structure

```
.
├── README.md                              # You are here
├── kind-config.yaml                       # Single-node Kind cluster with NodePorts exposed
├── k8s/                                   # Plain Kubernetes manifests
│   ├── namespace.yaml                     # mcp-poc namespace
│   ├── tasks-api-deployment.yaml          # FastAPI backend deployment
│   ├── tasks-api-service.yaml             # NodePort 30080 -> backend
│   ├── mcp-server-deployment.yaml         # FastMCP server deployment
│   ├── mcp-server-service.yaml            # NodePort 30090 -> MCP server
│   ├── ollama-deployment.yaml             # In-cluster Ollama for the demo LLM
│   └── ollama-service.yaml                # NodePort 30100 -> Ollama
├── scripts/
│   ├── setup.sh                           # One-command bootstrap
│   └── teardown.sh                        # Clean destruction
├── services/
│   ├── tasks_api/                         # The "production system"
│   │   ├── pyproject.toml                 # uv-managed, FastAPI + uvicorn
│   │   ├── Dockerfile                     # Multi-stage, non-root, pinned versions
│   │   ├── src/tasks_api/main.py          # CRUD-style HTTP API for tasks
│   │   └── tests/test_main.py             # Smoke tests
│   └── mcp_server/                        # The integration layer
│       ├── pyproject.toml                 # uv-managed, mcp + httpx
│       ├── Dockerfile                     # Multi-stage, non-root, pinned versions
│       ├── src/mcp_server/api_client.py   # HTTP transport for the Tasks API
│       ├── src/mcp_server/server.py       # FastMCP server with intent-grouped tools
│       └── tests/test_tools.py            # Verifies the intent-grouping invariant
└── examples/
    ├── direct_api.py                      # Path 1: bare HTTP from Python
    ├── cli_demo.sh                        # Path 2: curl in a shell
    ├── mcp_client.py                      # Path 3: MCP streamable-http client
    └── streamlit_demo.py                  # `make demo`: side-by-side comparison UI
```

---

## How It Works

**Why three paths against one backend?** The article's framing is that mature integrations ship all three. Putting them side-by-side makes it obvious *which* trade-offs each path makes.

**Why intent-grouped tools matter.** The Tasks API exposes five endpoints. Mirroring them one-to-one would force the agent to chain three calls just to "complete a task with a note": `GET /tasks/{id}` → `PATCH /tasks/{id}` (status) → `PATCH /tasks/{id}` (note). The MCP server collapses that into a single `complete_task_with_note(task_id, note)` tool. Fewer round-trips, less context spent on choreography, fewer chances for the agent to go off-rails.

**Why FastMCP with streamable-http?** It's the recommended transport for production MCP deployments — works across web, mobile, and cloud-hosted agents, and is the configuration every major client is optimized to consume.

**Why Kind?** Identical Kubernetes semantics on macOS and Windows with no cloud bill. The cluster is a single node with NodePorts (30080, 30090) mapped straight to localhost so students don't need port-forward tutorials before they see anything work.

---

## Teardown

```bash
make destroy
```

That deletes the entire Kind cluster — no leftover containers, networks, or volumes.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `kind: command not found` | Kind not installed or not on `PATH` | Follow the [install guide](https://kind.sigs.k8s.io/docs/user/quick-start/#installation), then re-open your shell |
| `connection refused` on `localhost:30080` | Cluster came up but pods aren't ready yet | `kubectl -n mcp-poc get pods -w` and wait for `Running` |
| Image pull errors like `ErrImageNeverPull` | Image wasn't loaded into the Kind cluster | Re-run `sh scripts/setup.sh` — it re-loads the images |

---

## Next Steps

Once the lab is running, try these extensions to deepen your understanding of the patterns from the article:

1. **Add a fourth intent-grouped tool** — e.g., `reassign_high_priority_tasks(from_user, to_user)`. Notice how the LLM-facing surface stays small even as capability grows.
2. **Try the MCP Inspector** against `http://localhost:30090/mcp` — `npx -y @modelcontextprotocol/inspector` lets you poke the server interactively.
3. **Read [Writing tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)** — the deep dive behind the intent-grouped pattern.
4. **Explore [tool search and programmatic tool calling](https://www.anthropic.com/engineering/advanced-tool-use)** — the client-side context-efficiency patterns the article highlights.

---

## License

MIT.
