## Design rules to keep server/tools clean

* Thin adapters only: don’t put business rules in tools; put them in app/services/.
* Validate strictly: define Pydantic models for every tool’s input.
* Document purpose & side‑effects: the tool’s description should clearly tell the model when to use it.
* Deterministic & bounded: tools should be predictable, guard resource usage (timeouts, size caps), and avoid LLM calls.
* Security first: sandbox file paths, allowlist network domains, redact sensitive fields in logs.
* Version carefully: if you break a tool’s contract, publish a new name (e.g., fs_write_v2) and deprecate the old one.


## Quick “when to use what” guide for your agent

* Need a temporary scratchpad or idempotency marker? → kv_put / kv_get
* Need to verify existing content? → fs_read
* Need to call an API safely? → http_fetch (and validate the payload first)
* Need to enforce a contract before a side‑effect? → json_validate
* Need traceability/audit of a critical step/result? → artifact_log / later artifact_list
* Need to write a report/result for humans or later tools? → fs_write


## Conventions & best practices (quick checklist)


### Schemas:

* Put schemas under version control and version them in the $id.
* Keep them as embedded objects for now; later expose as MCP resources for discovery.
* Treat schema changes as API changes; avoid breaking fields.



### Artifacts:

* Decide retention (e.g., keep 90 days in .sandbox/artifacts); add a housekeeping script later.
* Use hashes (SHA‑256) for payload/result proofs; avoid storing secrets.
* Use correlation IDs consistently.



### Agent flow:

* Validate → Side‑effect → Log is a safe default pattern.
* On any error, log an artifact in errors with enough context (but still redacted).

## artifact_log / artifact_list — append‑only audit trail

### What they do

artifact_log(tag, content, meta?): Appends an immutable event record (line of NDJSON) under a sandboxed artifacts directory. Each record includes a timestamp, tag, and optional metadata (e.g., tool name, correlation ID, checksums).
artifact_list(tag, limit, order?): Reads back the latest N entries for a tag (default newest‑first), enabling review, summarization, or export.

### Why it’s useful in an MCP flow

Compliance & traceability: You get a durable timeline of what happened—what the agent planned, validated, executed, and produced.
Debuggability: When a run fails, you can reconstruct the steps from the log.
Handoffs & reviews: Humans or other agents can inspect artifacts without digging through raw files.