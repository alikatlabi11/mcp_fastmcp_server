<!-- README.md -->

# MCP FastMCP Server (stdio + HTTP) — Production‑minded PoC

> **Purpose**  
> This repository implements a **Model Context Protocol (MCP)** server in **Python**, with both **stdio** and **Streamable HTTP** transports. It exposes a practical set of **tools** (filesystem, HTTP fetch with SSRF guards, JSON Schema validation, append‑only artifacts, and optional Redis KV) using a production‑minded architecture: clean separation of concerns, strong input validation, explicit security controls, and a single **tool registry** powering **both** transports.

---

## Contents

- What is MCP? Why this server?
- Architecture Overview
- Transports
  - stdio (local)
  - Streamable HTTP (remote)
- Security Model
- Tools Exposed
- Configuration
- Quick Start
  - Run stdio transport
  - Run HTTP transport
- How Agents Use This Server
- Add a New Tool (Contributor Guide)- Testing, Linting, CI
- Observability & Auditing
- Design Rationale
- Folder Structure
- FAQ
- References

---

## What is MCP? Why this server?

**Model Context Protocol (MCP)** is an open, JSON‑RPC‑based protocol that lets AI clients/hosts discover and invoke **tools** and read **resources** from **servers** in a standard way. MCP defines how to **list** tools (names, descriptions, input schemas) and **call** them over a transport (stdio for local or Streamable HTTP for remote).

- **Transports**: MCP uses **JSON‑RPC 2.0**; standard transports are **stdio** and **Streamable HTTP** (HTTP POST with optional SSE streaming). The HTTP transport warns about **DNS rebinding** and requires **Origin validation** and recommends **authentication**. See:  
  *Transports (concepts)* — <https://modelcontextprotocol.io/docs/concepts/transports>  
  *Transports (spec)* — <https://modelcontextprotocol.io/specification/2025-06-18/basic/transports>
- **Tools**: tools are discoverable with `tools/list` and invokable with `tools/call` (JSON‑RPC messages; tool inputs are defined via JSON Schema). See:  
  *Tools (spec)* — <https://modelcontextprotocol.io/specification/2025-06-18/server/tools>
- **JSON‑RPC in MCP**: requests/responses/notifications follow JSON‑RPC 2.0. See:  
  *Guide: JSON‑RPC in MCP* — <https://mcpcat.io/guides/understanding-json-rpc-protocol-mcp/>

**This server** demonstrates a production‑minded Python implementation that:

- Keeps **LLM reasoning** in your **agent** while the server executes safe, deterministic **tools**.
- Provides **stdio** (easy local dev) and **HTTP** (remote/multi‑tenant) with a shared **tool registry**.
- Emphasizes **security**: filesystem sandbox, SSRF guards+allowlist, Origin validation, Bearer token.

---

## Architecture Overview

```text
mcp-fastmcp-server/
├─ server/
│  ├─ main.py                 # stdio transport entrypoint (FastMCP host)
│  ├─ http_app.py             # Streamable HTTP (FastAPI + Bearer + Origin checks)
│  └─ registry.py             # SINGLE source of truth: tools metadata + handlers
├─ server/tools/              # Only Pydantic input models live here (thin)
│  ├─ files.py                # FsWriteIn, FsReadIn models
│  ├─ http_fetch.py           # FetchIn model
│  ├─ json_validate.py        # JsonValidateIn model
│  ├─ artifacts.py            # ArtifactLogIn, ArtifactListIn models
│  └─ kv.py                   # KvPutIn, KvGetIn models (optional)
├─ app/
│  ├─ config.py               # Settings (env-driven)
│  ├─ di.py                   # Dependency wiring (services from settings)
│  ├─ logging.py              # Redaction helpers & log config
│  └─ services/
│     ├─ filesystem.py        # sandboxed FS
│     ├─ httpclient.py        # Safe HTTP (allowlist, DNS/IP checks, timeouts, caps)
│     ├─ validator.py         # JSON Schema validator
│     ├─ artifacts.py         # append/list NDJSON, monthly rotation
│     └─ kvstore.py           # Redis KV (optional)
├─ tests/                     # Unit tests (services + tools)
├─ scripts/                   # Dev scripts (setup, run, test, http run)
├─ .github/workflows/ci.yml   # GitHub Actions: make test on push/PR
├─ Makefile                   # setup, run, run-http, test, lint, typecheck
├─ pyproject.toml / requirements.txt
└─ .env.example / README.md
```

Key idea: the tool registry (server/registry.py) centralizes:

Tool metadata (name, description, Pydantic input model → JSON Schema).
Named handlers that call into services.
Helpers to emit list payloads and dispatch tool calls.
A hook to register every tool into the FastMCP stdio host.

Both transports import the same registry, guaranteeing consistent tools/schemas everywhere.

## Transports

### 1-stdio (local)

The host (agent/IDE like VS Code) launches the server as a subprocess and exchanges JSON‑RPC over stdin/stdout. Great for local dev and IDE integration.
Spec: stdio framing & rules (pure JSON‑RPC, newline delimited). See Transports (concepts/spec) in references.

Entrypoint:
```sh
python -m server.main
```
```
VS Code can launch stdio MCP servers; see its MCP docs: <https://code.visualstudio.com/docs/copilot/customization/mcp-servers>
```

### 2-Streamable HTTP (remote)

The server exposes a single MCP endpoint (e.g., /mcp) that accepts JSON‑RPC 2.0 via HTTP POST (one request per message). Optional SSE GET allows server‑initiated messages and streaming.
Security: you must validate Origin and should require authentication to mitigate DNS rebinding risks. This server enforces Bearer token and Origin allowlist. See Transports (concepts/spec) in references.

Entrypoint:

```
uvicorn server.http_app:app --host 127.0.0.1 --port 8080
```
#### HTTP client flow (JSON‑RPC):

1. initialize
2. tools/list
3. tools/call with { "name": "tool", "arguments": { ... } }

#### Transport details (single endpoint, POST per message, Origin validation, optional SSE) follow the MCP spec:

* Transports (concepts) — <https://modelcontextprotocol.io/docs/concepts/transports>
* Transports (spec) — <https://modelcontextprotocol.io/specification/2025-06-18/basic/transports>


## Security Model


1. **Filesystem sandbox**

All fs tools operate under SANDBOX_ROOT; path traversal escapes are rejected in app/services/filesystem.py.



2. **HTTP client safety**

  * http_fetch: allowlisted domains only; rejects private/loopback/link‑local/reserved IPs after DNS resolution; enforces timeouts and response size caps (prevents SSRF, resource abuse).



3. **HTTP transport controls**

  * Origin validation and Bearer token are enforced on each HTTP request, per MCP HTTP transport guidance (see spec links above).



4. **Strict input validation**

  * Each tool uses a Pydantic model; MCP tools/list publishes JSON Schemas so clients can validate before calling (see Tools spec).



5. **No secrets in logs**

* Basic email redaction is included in app/logging.py; extend redactors as needed.




## Tools Exposed

All tools are non‑LLM deterministic capabilities. Keep your LLM planning inside your agent.



* **fs_write(path, content) / fs_read(path)**

Sandbox‑enforced text file I/O under SANDBOX_ROOT.


* http_fetch(url, method='GET', headers?, body?)
Safe HTTP client with allowlist, DNS/IP checks (blocks private/loopback), timeout, size caps.


* json_validate(instance, schema, draft?)
Validate a JSON payload against a JSON Schema (draft 2020‑12 by default). Returns { "valid": bool, "errors": [...] }.
Useful for preflight (validate before side‑effects) and auto‑repair loops.

  * JSON Schema in MCP flows is common to enforce shape & types (see Tools spec).



* artifact_log(tag, content, meta?, corr?, actor?, tool?)
Append a redacted, immutable NDJSON record under .sandbox/artifacts/<yyyy-mm>/<tag>-NNNN.ndjson. Monthly rotation & size‑based file rolling.


* artifact_list(tag, limit=50, order='desc', months_back=12)
Read back the latest N artifacts for review/summarization/auditing.


* kv_put(key, value, ttlSec?) / kv_get(key) (optional; Redis)
Ephemeral cross‑step scratchpad & idempotency keys with TTL auto‑cleanup—handy for retries, rate limits, and multi‑turn handoffs.

TTL behavior & commands are a natural fit for ephemeral state (see Redis TTL docs).




Configuration

Copy .env.example → .env and adjust:

```
# Filesystem sandbox
SANDBOX_ROOT=./.sandbox

# Optional Redis for kv_* tools
REDIS_URL=redis://127.0.0.1:6379/0

# HTTP fetch safety
HTTP_ALLOWLIST=example.com, api.github.com
HTTP_TIMEOUT_SEC=10.0
HTTP_MAX_BYTES=2000000
LOG_LEVEL=INFO

# Streamable HTTP transport
MCP_HTTP_ENABLED=true
MCP_HTTP_HOST=127.0.0.1
MCP_HTTP_PORT=8080
MCP_HTTP_PATH=/mcp
MCP_HTTP_BEARER_TOKEN=change-me
MCP_HTTP_ALLOWED_ORIGINS=http://localhost, http://127.0.0.1
MCP_HTTP_ALLOW_NO_ORIGIN=true
```
## Quick Start

### Run stdio transport


```sh
make setup
cp .env.example .env
make run
```

Your agent (or an IDE like VS Code Agent Mode) can now launch this server as a subprocess and speak MCP over stdio. VS Code MCP docs: <https://code.visualstudio.com/docs/copilot/customization/mcp-servers>


### Run HTTP transport
```sh
make setup
cp .env.example .env
# set a strong MCP_HTTP_BEARER_TOKEN in .env
make run-http
```
**Client usage** (JSON‑RPC 2.0, Authorization: Bearer <token>):
```json
POST /mcp HTTP/1.1
Host: 127.0.0.1:8080
Content-Type: application/json
Accept: application/json
Authorization: Bearer <token>
Origin: http://localhost

{ "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {} }
```
Then:
```json
JSON{ "jsonrpc":"2.0","id":2,"method":"tools/list","params":{} }{ "jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"fs_write","arguments":{"path":"file.txt","content":"Hello"}} }
```

## How Agents Use This Server

Discover tools via tools/list.
Each tool includes an inputSchema (JSON Schema) that tells the agent how to validate arguments (see Tools spec).
Plan (in the agent): break down the user goal into tool calls.
Call tools via tools/call with {name, arguments} (validated JSON per schema).
Assemble responses to produce the final answer.


Example pattern: validate → side‑effect → log

json_validate the payload → if invalid, auto‑repair and re‑validate.
Perform side‑effect (http_fetch or fs_write).
artifact_log outcome with a correlation ID (corr) for traceability.



## Add a New Tool (Contributor Guide)

Your goal: add a tool once in the registry, and have it automatically appear in both transports.

0) Choose a meaningful name
Pick a short, snake_case identifier (e.g., csv_preview).
1) Define the input model
Create or update a file under server/tools/ with a Pydantic model containing only the input parameters and their validation constraints. Keep it thin—no business logic here.
```py
# server/tools/csv_preview.py
from pydantic import BaseModel, Field

class CsvPreviewIn(BaseModel):
    path: str = Field(..., description="Relative path under sandbox root")
    max_rows: int = Field(20, ge=1, le=1000, description="Rows to preview")

```
2) Implement the service logic
Put business logic in app/services/…. For example, app/services/csv.py reading from the sandbox and returning the preview (rows & headers).
3) Add a handler method
Add a named method to ToolHandlers (in server/registry.py) that accepts the Pydantic input model and calls your service:

```py
from server.tools.csv_preview import CsvPreviewIn
from app.services.csv import CsvService

class ToolHandlers:
    def __init__(self):
        self.container = build_container()
        self.csv_service = CsvService(self.container.fs_service)

    def csv_preview(self, args: CsvPreviewIn) -> dict:
        return self.csv_service.preview(args.path, args.max_rows)

```
4) Register the tool
Add a ToolSpec in build_tool_registry():
```py
reg["csv_preview"] = ToolSpec(
    name="csv_preview",
    description="Preview a CSV file under sandbox root",
    input_model=CsvPreviewIn,
    handler=handlers.csv_preview,
)

```
5) Tests

Add unit tests under tests/ to cover the service and handler behavior.
For simple verification, test the service directly (no transport needed).
Optionally add an HTTP integration test that POSTs tools/call with your tool.

6) Docs

Update README “Tools Exposed” with your tool.
Document any new env variables.

7) Submit a PR

Run make test locally (ruff, black, pytest).
Our GitHub Actions workflow runs the same on push/PR.


Testing, Linting, CI

Unit tests: pytest in tests/.
Linters/formatters: ruff, black.
Type checking: mypy.
CI: .github/workflows/ci.yml runs make test on push/PR.
```sh
make test      # ruff + black --check + pytest
make format    # black
make typecheck # mypy

```
## Observability & Auditing

Structured logs: you can wrap handler calls (in ToolHandlers) to log duration, errors, and arguments (with redaction).
Artifacts: artifact_log / artifact_list provide a simple append‑only audit trail for outcomes and important events. Use semantic tags (orders:create, errors, plan) and correlation IDs (corr) to reconstruct runs.


## Design Rationale

Single tool registry as the source of truth prevents drift between transports and aligns with MCP’s discover → call model (see Tools spec).
Named handlers (not lambdas) improve readability, testability, and logging.
Strict validation (Pydantic input models) surfaces accurate tool schemas to clients.
HTTP safety follows MCP transport advice: Origin checks and auth mitigate DNS‑rebinding and unauthorized access (see Transports spec).
KV optionality keeps the PoC lightweight but allows ephemeral idempotency, rate limiting, and multi‑turn scratchpad when needed.


## Folder Structure
```
server/            # transports + registry (no business logic)
  main.py          # stdio entry (FastMCP)
  http_app.py      # Streamable HTTP entry (FastAPI)
  registry.py      # tool specs + handlers + dispatch/list helpers

server/tools/      # Pydantic input models only (thin)
  files.py, http_fetch.py, json_validate.py, artifacts.py, kv.py

app/               # "application" layer: config + services + DI
  config.py        # env settings
  di.py            # container wiring (services)
  logging.py       # redaction helpers
  services/        # business logic backing the tools
    filesystem.py, httpclient.py, validator.py, artifacts.py, kvstore.py

tests/             # pytest unit tests
scripts/           # setup/run/test scripts
.github/workflows/ # ci.yml (make test on push/PR)

```
## FAQ
Q: Can I use this server directly from VS Code / Copilot Agent Mode?
A: Yes. For stdio, VS Code can launch it as a subprocess. For HTTP, configure the URL and auth header; VS Code + other hosts can connect to remote MCP servers. See: <https://code.visualstudio.com/docs/copilot/customization/mcp-servers>
Q: Does HTTP support streaming?
A: The spec allows Streamable HTTP and optional SSE for streaming/server‑initiated messages. This PoC implements POST (non‑streaming) first; SSE can be added if you need server‑pushed updates. See Transports references.
Q: Where should I put complex business rules?
A: In services (e.g., app/services/...). Keep tool handlers thin and transport‑agnostic.
Q: How do I disable Redis and KV tools?
A: Leave REDIS_URL blank in .env. The registry registers kv_* only if Redis is configured.

## References


MCP Transports (stdio, Streamable HTTP, SSE)
Concepts: <https://modelcontextprotocol.io/docs/concepts/transports>
Spec: <https://modelcontextprotocol.io/specification/2025-06-18/basic/transports>


MCP Tools (list/call, schemas, content blocks)
Spec: <https://modelcontextprotocol.io/specification/2025-06-18/server/tools>


JSON‑RPC used by MCP
Guide: <https://mcpcat.io/guides/understanding-json-rpc-protocol-mcp/>


VS Code MCP Clients
Docs: <https://code.visualstudio.com/docs/copilot/customization/mcp-servers>