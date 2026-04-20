# Hermes Agent Security Policy

This document outlines the security protocols, trust model, and deployment hardening guidelines for the **Hermes Agent** project.

## 1. Vulnerability Reporting

Hermes Agent does **not** operate a bug bounty program. Security issues should be reported via [GitHub Security Advisories (GHSA)](https://github.com/NousResearch/hermes-agent/security/advisories/new) or by emailing **security@nousresearch.com**. Do not open public issues for security vulnerabilities.

### Required Submission Details
- **Title & Severity:** Concise description and CVSS score/rating.
- **Affected Component:** Exact file path and line range (e.g., `tools/approval.py:120-145`).
- **Environment:** Output of `hermes version`, commit SHA, OS, and Python version.
- **Reproduction:** Step-by-step Proof-of-Concept (PoC) against `main` or the latest release.
- **Impact:** Explanation of what trust boundary was crossed.

---

## 2. Trust Model

The core assumption is that Hermes is a **personal agent** with one trusted operator.

### Operator & Session Trust
- **Single Tenant:** The system protects the operator from LLM actions, not from malicious co-tenants. Multi-user isolation must happen at the OS/host level.
- **Multi-User Gateway Isolation:** In gateway deployments (Feishu, Telegram, Discord), each user gets an isolated profile directory (`~/.hermes/user_profiles/{user_id}/`) with separate memories, skills, sessions, and logs. User boundary validation prevents cross-user data access. See Section 6 for details.
- **Gateway Security:** Authorized callers (Telegram, Discord, Slack, etc.) receive equal trust. Session keys are used for routing, not as authorization boundaries.
- **Execution:** Defaults to `terminal.backend: local` (direct host execution). Container isolation (Docker, Modal, Daytona) is opt-in for sandboxing.

### Dangerous Command Approval
The approval system (`tools/approval.py`) is a core security boundary. Terminal commands, file operations, and other potentially destructive actions are gated behind explicit user confirmation before execution. The approval mode is configurable via `approvals.mode` in `config.yaml`:
- `"on"` (default) — prompts the user to approve dangerous commands.
- `"auto"` — auto-approves after a configurable delay.
- `"off"` — disables the gate entirely (break-glass; see Section 3).

### Output Redaction
`agent/redact.py` strips secret-like patterns (API keys, tokens, credentials) from all display output before it reaches the terminal or gateway platform. This prevents accidental credential leakage in chat logs, tool previews, and response text. Redaction operates on the display layer only — underlying values remain intact for internal agent operations.

### Skills vs. MCP Servers
- **Installed Skills:** High trust. Equivalent to local host code; skills can read environment variables and run arbitrary commands.
- **MCP Servers:** Lower trust. MCP subprocesses receive a filtered environment (`_build_safe_env()` in `tools/mcp_tool.py`) — only safe baseline variables (`PATH`, `HOME`, `XDG_*`) plus variables explicitly declared in the server's `env` config block are passed through. Host credentials are stripped by default. Additionally, packages invoked via `npx`/`uvx` are checked against the OSV malware database before spawning.

### Code Execution Sandbox
The `execute_code` tool (`tools/code_execution_tool.py`) runs LLM-generated Python scripts in a child process with API keys and tokens stripped from the environment to prevent credential exfiltration. Only environment variables explicitly declared by loaded skills (via `env_passthrough`) or by the user in `config.yaml` (`terminal.env_passthrough`) are passed through. The child accesses Hermes tools via RPC, not direct API calls.

### Subagents
- **No recursive delegation:** The `delegate_task` tool is disabled for child agents.
- **Depth limit:** `MAX_DEPTH = 2` — parent (depth 0) can spawn a child (depth 1); grandchildren are rejected.
- **Memory isolation:** Subagents run with `skip_memory=True` and do not have access to the parent's persistent memory provider. The parent receives only the task prompt and final response as an observation.

---

## 3. Out of Scope (Non-Vulnerabilities)

The following scenarios are **not** considered security breaches:
- **Prompt Injection:** Unless it results in a concrete bypass of the approval system, toolset restrictions, or container sandbox.
- **Public Exposure:** Deploying the gateway to the public internet without external authentication or network protection.
- **Trusted State Access:** Reports that require pre-existing write access to `~/.hermes/`, `.env`, or `config.yaml` (these are operator-owned files).
- **Default Behavior:** Host-level command execution when `terminal.backend` is set to `local` — this is the documented default, not a vulnerability.
- **Configuration Trade-offs:** Intentional break-glass settings such as `approvals.mode: "off"` or `terminal.backend: local` in production.
- **Tool-level read/access restrictions:** The agent has unrestricted shell access via the `terminal` tool by design. Reports that a specific tool (e.g., `read_file`) can access a resource are not vulnerabilities if the same access is available through `terminal`. Tool-level deny lists only constitute a meaningful security boundary when paired with equivalent restrictions on the terminal side (as with write operations, where `WRITE_DENIED_PATHS` is paired with the dangerous command approval system).

---

## 4. Deployment Hardening & Best Practices

### Filesystem & Network
- **Production sandboxing:** Use container backends (`docker`, `modal`, `daytona`) instead of `local` for untrusted workloads.
- **File permissions:** Run as non-root (the Docker image uses UID 10000); protect credentials with `chmod 600 ~/.hermes/.env` on local installs.
- **Network exposure:** Do not expose the gateway or API server to the public internet without VPN, Tailscale, or firewall protection. SSRF protection is enabled by default across all gateway platform adapters (Telegram, Discord, Slack, Matrix, Mattermost, etc.) with redirect validation. Note: the local terminal backend does not apply SSRF filtering, as it operates within the trusted operator's environment.

### Skills & Supply Chain
- **Skill installation:** Review Skills Guard reports (`tools/skills_guard.py`) before installing third-party skills. The audit log at `~/.hermes/skills/.hub/audit.log` tracks every install and removal.
- **MCP safety:** OSV malware checking runs automatically for `npx`/`uvx` packages before MCP server processes are spawned.
- **CI/CD:** GitHub Actions are pinned to full commit SHAs. The `supply-chain-audit.yml` workflow blocks PRs containing `.pth` files or suspicious `base64`+`exec` patterns.

### Credential Storage
- API keys and tokens belong exclusively in `~/.hermes/.env` — never in `config.yaml` or checked into version control.
- The credential pool system (`agent/credential_pool.py`) handles key rotation and fallback. Credentials are resolved from environment variables, not stored in plaintext databases.

---

## 5. Disclosure Process

- **Coordinated Disclosure:** 90-day window or until a fix is released, whichever comes first.
- **Communication:** All updates occur via the GHSA thread or email correspondence with security@nousresearch.com.
- **Credits:** Reporters are credited in release notes unless anonymity is requested.

---

## 6. Multi-User Gateway Isolation

### Overview

In multi-user gateway deployments (Feishu, Telegram, Discord), Hermes implements a defense-in-depth security model to prevent cross-user data access. Each user receives an isolated profile directory with separate memories, skills, sessions, and logs.

### Architecture

**ContextVar-Based Isolation** (`hermes_constants.py`)

Each user gets an isolated profile:
```
~/.hermes/user_profiles/{user_id}/
  ├── memories/     # MEMORY.md, USER.md
  ├── skills/       # Custom skill definitions
  ├── sessions/     # Conversation history
  ├── logs/         # Agent activity logs
  └── state.db      # Per-user session state
```

The gateway sets `_HERMES_HOME_CTX` ContextVar per-request in `gateway/run.py:_run_agent()`:
```python
_user_profile_dir = _base_home / "user_profiles" / str(source.user_id)
set_hermes_home_ctx(str(_user_profile_dir))
```

**User Boundary Validation** (`tools/file_tools.py`)

All file access tools validate paths before I/O:
- `read_file_tool` - Blocks reading other users' files
- `write_file_tool` - Blocks writing to other users' directories
- `patch_tool` - Blocks modifying other users' files
- `search_tool` - Blocks searching other users' directories

Validation only applies in gateway mode (detected via ContextVar). CLI mode has full filesystem access (unchanged).

**Path Disclosure Prevention** (`hermes_constants.py`)

User IDs are sanitized in all displayed paths:
- Before: `~/.hermes/user_profiles/ou_e35410f852dacadaced24f89d5743de1/skills/`
- After: `~/.hermes/user_profiles/<your-profile>/skills/`

This prevents user enumeration and targeted attacks.

### Attack Vectors Mitigated

1. **Direct Path Access**: User A specifies User B's absolute path → BLOCKED by validation
2. **Path Traversal**: User A uses `../` to escape profile → BLOCKED by `Path.resolve()` + validation
3. **Symlink Attack**: User A creates symlink to User B's files → BLOCKED by `Path.resolve()`
4. **Path Enumeration**: User A extracts user IDs from responses → User IDs sanitized
5. **Tool Chaining**: User A uses multiple tools in sequence → Each tool validates independently

### Testing

- `tests/tools/test_file_tools_user_boundary.py` (10 tests) - User boundary validation
- `tests/test_path_disclosure.py` (3 tests) - Path sanitization
- `tests/gateway/test_per_user_gateway_isolation.py` (10 tests) - Concurrent user isolation

### Known Limitations

1. **Operator config is shared**: All users share the same API keys and model routing (by design)
2. **No rate limiting**: Repeated boundary violations are not rate-limited
3. **No audit trail for file tools**: Cross-user access attempts via file tools are not logged (memory files have audit logging)
4. **Terminal tool unrestricted**: The `terminal` tool has full host access and is not subject to user boundary validation (same trust model as single-user mode)

### Memory File Protection (feat-009)

**Defense-in-Depth for SOUL.md, MEMORY.md, USER.md**

In addition to file tool validation, memory files have explicit path validation:

- **tools/memory_tool.py**: Validates `MEMORY.md` and `USER.md` paths before read/write
- **agent/prompt_builder.py**: Validates `SOUL.md` path before loading
- **Audit logging**: Failed access attempts logged to `{HERMES_HOME}/logs/memory_security.log`

**Why additional validation?**
- Memory files use direct file I/O (not through file_tools)
- Provides defense-in-depth even though ContextVar already isolates users
- Detects ContextVar misconfiguration or bypass attempts

**Audit log format**:
```json
{
  "timestamp": "2026-04-20T15:30:45.123456",
  "event": "memory_access_denied",
  "file_type": "SOUL" | "MEMORY" | "USER",
  "attempted_path": "/path/to/file",
  "user_id": "ou_xxx" | null,
  "context_var": "/actual/context/path" | null,
  "error": "Path escapes allowed directory: ..."
}
```

**User customization preserved**: Users can still modify their own SOUL.md (original Hermes design).

### Incident: CVE-2026-XXXX (Cross-User Data Access)

**Discovered**: 2026-04-20  
**Severity**: CRITICAL  
**Status**: FIXED in v0.11.0

**Vulnerability**: User A could access User B's private data (memories, skills, sessions) by specifying paths outside their profile directory.

**Attack Vector**:
1. User A asked "你的技能检索的路径" → Agent revealed User B's full path
2. User A used `search_files` and `skill_view` to access User B's data
3. User A extracted User B's personal information from `USER.md`

**Root Cause**: File tools accepted arbitrary paths without checking user ownership.

**Fix**: Added user boundary validation to all file tools and path disclosure prevention in `display_hermes_home()`.

**References**: 
- `progress.md` - Session 2026-04-20
- `feature_list.json` - feat-008
- `tests/tools/test_file_tools_user_boundary.py` - Regression tests

