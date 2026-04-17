---
title: "Hermes Agent 飞书多用户完全隔离实现方案"
tags:
  - hermes-agent
  - implementation-plan
  - feishu
  - isolation
created: 2026-04-17
sources:
  - "[[raw/hermes-USB-feishu]]"
  - "[[outputs/2026-04-17-hermes-isolation-session-learning]]"
related:
  - "[[hermes-agent/Multi-Tenant Isolation]]"
  - "[[hermes-agent/Memory System]]"
  - "[[hermes-agent/Feishu SaaS Architecture]]"
---

# Hermes Agent 飞书多用户完全隔离实现方案

## 一、背景与问题

### 现状

Hermes Agent 飞书多用户部署中，所有用户共享同一个 `HERMES_HOME`（默认 `~/.hermes`）。记忆、会话、技能全部混在一起：

- `MEMORY.md` / `USER.md` — 所有用户共享一份
- `state.db` — 所有用户的会话存在同一个数据库
- `skills/` — 所有用户的自学习技能存在同一个目录

**核心风险**：用户 A 存储的偏好/信息会通过系统提示词注入到用户 B 的会话中。

### 目标

实现**完全隔离**——每个飞书用户拥有独立的记忆、会话、技能和配置，等价于每用户运行独立进程，但共享同一个 Gateway 进程。

---

## 二、核心挑战

### 2.1 `os.environ` 是进程全局的

`get_hermes_home()` 通过 `os.environ["HERMES_HOME"]` 读取路径。在并发的 asyncio Gateway 中，修改环境变量会影响**所有**正在处理的用户请求。

### 2.2 模块级缓存

代码库中有 **24+ 个模块级缓存**在 import 时固化了 `get_hermes_home()` 的值：

| 文件 | 缓存变量 | 引用次数 | 影响范围 |
|------|---------|---------|---------|
| `gateway/run.py:81` | `_hermes_home` | **61+** | Gateway 全局 |
| `tools/skills_tool.py:87-88` | `HERMES_HOME`, `SKILLS_DIR` | 14 | 被 5 个文件导入 |
| `tools/skill_manager_tool.py:80-81` | `HERMES_HOME`, `SKILLS_DIR` | 10 | 独立定义 |
| `tools/skills_hub.py:46-48` | `HERMES_HOME`, `SKILLS_DIR`, `HUB_DIR` | 8+ | 被 3 个文件导入 |
| `tools/skills_sync.py:35-37` | `HERMES_HOME`, `SKILLS_DIR` | 5+ | 内部使用 |
| `hermes_state.py:32` | `DEFAULT_DB_PATH` | 2 | 被 1 个文件导入 |
| `run_agent.py:52` | `_hermes_home` | 8 | .env 加载 |
| `cron/jobs.py:34` | `HERMES_DIR` | 2+ | Cron 系统 |
| `cron/scheduler.py:60` | `_hermes_home` | 9 | Cron 系统 |
| 14 个其他模块 | 各种路径常量 | 各异 | Gateway 子模块 |

并发场景下直接切换 `os.environ["HERMES_HOME"]` **不可行**——模块级缓存不会更新，且会影响其他用户的请求。

### 2.3 已有的隔离基础

好消息是，部分组件**已经**支持并发隔离：

| 组件 | 是否隔离 | 机制 |
|------|---------|------|
| Session Key 路由 | ✅ 已隔离 | `platform:chat_type:chat_id:user_id` |
| ContextVars（7个）| ✅ 已隔离 | 每个 asyncio Task 独立 |
| Agent 实例缓存 | ✅ 已隔离 | `_agent_cache[session_key]` |
| `get_memory_dir()` | ✅ 动态 | 函数调用 `get_hermes_home()`，非缓存 |
| `get_config_path()` | ✅ 动态 | 同上 |
| 飞书 user_id | ✅ 已提供 | `union_id`（`on_` 前缀） |

---

## 三、解决方案：ContextVar 覆盖层

### 核心思路

在 `hermes_constants.py` 的 `get_hermes_home()` 中引入 `ContextVar` 覆盖层。

- `ContextVar` 是 Python 标准库提供的**任务级变量**
- asyncio-safe：每个 asyncio Task 拥有独立值
- 通过 `copy_context().run()` 传播到子线程

Gateway 在处理每个用户消息时，设置该用户的 profile 目录到 ContextVar。此后所有**动态调用** `get_hermes_home()` 的代码自动获得正确的 per-user 路径。

### 目标目录结构

```
~/.hermes/                          # 基础 Profile（Gateway 启动时的默认值）
├── config.yaml                     # 共享配置模板
├── .env                            # 共享环境变量（API keys 等）
├── user_profiles/                  # 🆕 per-user 隔离目录
│   ├── {feishu_user_id_1}/
│   │   ├── memories/
│   │   │   ├── MEMORY.md           # 用户 1 的记忆
│   │   │   └── USER.md             # 用户 1 的画像
│   │   ├── skills/                 # 用户 1 自学习创建的技能
│   │   ├── sessions/               # 用户 1 的会话日志
│   │   ├── state.db                # 用户 1 的独立会话数据库
│   │   └── config.yaml             # 可选：用户级配置覆盖
│   └── {feishu_user_id_2}/
│       └── ...                     # 用户 2 完全独立
└── skills/                         # 全局共享技能（可选保留）
```

---

## 四、实现步骤

### Step 1: 核心 — `hermes_constants.py` 添加 ContextVar 覆盖

**文件**: `hermes_constants.py`（line 6-16）

这是整个方案的基石。修改 `get_hermes_home()` 优先读取 ContextVar：

```python
import os
from contextvars import ContextVar
from pathlib import Path

# Task-local override for HERMES_HOME — used by gateway to
# scope each user to an isolated profile directory.
_HERMES_HOME_CTX: ContextVar[str | None] = ContextVar(
    "_HERMES_HOME_CTX", default=None
)

def get_hermes_home() -> Path:
    """Return the Hermes home directory.

    Resolution order:
    1. ContextVar override (per-task, set by gateway for multi-user)
    2. HERMES_HOME env var
    3. ~/.hermes default
    """
    ctx = _HERMES_HOME_CTX.get(None)
    if ctx is not None:
        return Path(ctx)
    return Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))

def set_hermes_home_ctx(path: str | Path | None) -> None:
    """Set the task-local HERMES_HOME override.

    Call this in gateway before processing each user's message.
    Pass None to clear the override.
    """
    _HERMES_HOME_CTX.set(str(path) if path else None)
```

**效果**：所有调用 `get_hermes_home()` 的**函数级代码**自动获得正确的 per-user 路径。模块级缓存仍使用启动时的基础路径（下面分步修复）。

**向后兼容**：ContextVar 默认值为 `None`，CLI/Cron 等不设置 ContextVar 的场景自动回退到 `os.environ` → 默认值。

---

### Step 2: 修复 Gateway 相关的模块级缓存

只修复在 Gateway 进程中会被加载且涉及用户数据的模块。CLI-only、RL、Cron 等模块不改。

#### 2a. `tools/skills_tool.py`（line 87-88）

```python
# 改前（模块级缓存）：
HERMES_HOME = get_hermes_home()
SKILLS_DIR = HERMES_HOME / "skills"

# 改后（动态函数，hermes_constants.py 已有 get_skills_dir()）：
# 删除这两行，所有 SKILLS_DIR 引用改为 get_skills_dir() 调用
```

文件内约 14 处引用需替换。

**同步修复导入方**：
- `agent/skill_commands.py`：`from tools.skills_tool import SKILLS_DIR` → `from hermes_constants import get_skills_dir`
- `hermes_cli/commands.py`：同上

#### 2b. `tools/skill_manager_tool.py`（line 80-81）

同理，删除 `HERMES_HOME` 和 `SKILLS_DIR` 模块级变量，改为 `get_skills_dir()` 调用。约 10 处引用。

#### 2c. `tools/skills_hub.py`（line 46-48）

```python
# 改前：
HERMES_HOME = get_hermes_home()
SKILLS_DIR = HERMES_HOME / "skills"
HUB_DIR = SKILLS_DIR / ".hub"

# 改后：
def _hub_dir() -> Path:
    return get_skills_dir() / ".hub"
```

导入方 `hermes_cli/skills_hub.py` 同步修复。

#### 2d. `tools/skills_sync.py`（line 35-37）

同理，删除模块级缓存，改为动态调用。

#### 2e. `hermes_state.py`（line 32）

```python
# 改前：
DEFAULT_DB_PATH = get_hermes_home() / "state.db"

# 改后：
def _default_db_path() -> Path:
    return get_hermes_home() / "state.db"

class SessionDB:
    def __init__(self, db_path: Path = None):
        self.db_path = db_path or _default_db_path()
```

`tools/session_search_tool.py` 中的 `DEFAULT_DB_PATH` 引用同步修改。

#### 2f. `gateway/run.py`（line 81）— 改动量最大

```python
# 改前：
_hermes_home = get_hermes_home()  # 61+ 引用

# 改后：直接删除模块级缓存
# 所有 _hermes_home 引用改为 get_hermes_home() 调用
```

这是简单的全局替换（`_hermes_home` → `get_hermes_home()`），但涉及 61+ 处。

> [!tip] 安全性
> ContextVar 仅在处理用户消息时设置。Gateway 启动阶段 ContextVar 为 None，`get_hermes_home()` 自然回退到 env var，不影响启动逻辑。

---

### Step 3: Gateway 集成 — 设置 per-user ContextVar

**文件**: `gateway/run.py`

#### 3a. 自动创建用户 Profile 目录

在 `_run_agent()` 方法中（约 line 8600），AIAgent 创建之前：

```python
from hermes_constants import set_hermes_home_ctx

# 计算 per-user profile 路径
base_home = Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))
user_profile_dir = base_home / "user_profiles" / str(source.user_id)

# 首次访问时创建目录结构
if not user_profile_dir.exists():
    for subdir in ("memories", "skills", "sessions", "logs"):
        (user_profile_dir / subdir).mkdir(parents=True, exist_ok=True)
    # 从基础 Profile 复制 config.yaml
    base_config = base_home / "config.yaml"
    user_config = user_profile_dir / "config.yaml"
    if base_config.exists() and not user_config.exists():
        import shutil
        shutil.copy2(base_config, user_config)

# 设置 ContextVar（task-local，不影响其他并发用户）
set_hermes_home_ctx(str(user_profile_dir))
```

#### 3b. Per-user SessionDB

Gateway 当前在启动时创建一个共享 `self._session_db = SessionDB()`。改为 per-user：

```python
# 用 Dict 缓存 per-user SessionDB 连接
if not hasattr(self, '_user_session_dbs'):
    self._user_session_dbs = {}

user_id_str = str(source.user_id)
if user_id_str not in self._user_session_dbs:
    self._user_session_dbs[user_id_str] = SessionDB(
        db_path=user_profile_dir / "state.db"
    )
user_session_db = self._user_session_dbs[user_id_str]
```

然后将 `user_session_db` 传入 AIAgent 的 `session_db` 参数。

#### 3c. ContextVar 清理

消息处理完毕后清除 ContextVar：

```python
# 在 _run_agent() 的 finally 块中：
set_hermes_home_ctx(None)
```

---

### Step 4: 确保自学习写入正确位置

#### 4a. 后台审查 Agent（`run_agent.py` line 2361-2407）

后台审查 Agent 通过 `_spawn_background_review()` 在新线程中运行。需要用 `copy_context()` 传播 ContextVar：

```python
import contextvars
ctx = contextvars.copy_context()

def _run_review():
    # 已在正确的 context 中，get_hermes_home() 返回用户目录
    review_agent = AIAgent(...)
    review_agent._memory_store = self._memory_store
    ...

threading.Thread(target=ctx.run, args=(_run_review,), daemon=True).start()
```

如果现有代码已使用 `copy_context()`，则无需修改。否则需要包装。

#### 4b. Memory flush Agent（`gateway/run.py` line 743-848）

`_flush_memories_for_session()` 在 `run_in_executor` 中执行。需确保 ContextVar 传播：

```python
import contextvars
ctx = contextvars.copy_context()
await loop.run_in_executor(
    None, ctx.run, self._flush_memories_for_session, old_session_id, session_key
)
```

---

### Step 5: `run_agent.py` 模块级缓存处理

`run_agent.py:52` 的 `_hermes_home = get_hermes_home()` 用于 `.env` 加载（进程启动时的全局配置），**保留不变**。`.env` 中是 API keys 等共享配置，应该使用基础 Profile 的值。

`run_agent.py:1143-1147` 的 session 日志路径已经是动态函数调用（`hermes_home = get_hermes_home()`），自动受益于 ContextVar，无需修改。

---

## 五、不变的部分

| 组件 | 原因 |
|------|------|
| `hermes_constants.py` 其他函数 | 它们内部调用 `get_hermes_home()`，自动受益 |
| `tools/memory_tool.py` | `get_memory_dir()` 调用 `get_hermes_home()`，已动态 ✅ |
| `gateway/session_context.py` | ContextVar 在 `hermes_constants.py` 中管理 |
| `gateway/platforms/feishu.py` | 已正确提供 user_id |
| CLI-only 模块（`cli.py`, `rl_cli.py`） | 单用户模式，模块级缓存无害 |
| `cron/` 模块 | 独立进程运行，不受 Gateway 并发影响 |

---

## 六、关键文件清单

| 文件 | 改动类型 | 估算行数 |
|------|---------|---------|
| `hermes_constants.py` | 添加 ContextVar + set/get 函数 | +15 行 |
| `gateway/run.py` | `_hermes_home` → `get_hermes_home()` + per-user 逻辑 | ~70 行 |
| `tools/skills_tool.py` | `SKILLS_DIR` 缓存 → 动态函数 | ~20 行 |
| `tools/skill_manager_tool.py` | 同上 | ~15 行 |
| `tools/skills_hub.py` | 同上 | ~15 行 |
| `tools/skills_sync.py` | 同上 | ~10 行 |
| `hermes_state.py` | `DEFAULT_DB_PATH` → 动态函数 | ~5 行 |
| `run_agent.py` | 后台审查 `copy_context()` 包装 | ~5 行 |
| `agent/skill_commands.py` | 导入修改 | ~5 行 |

**总计**: ~8-9 个文件，约 160 行改动

---

## 七、风险评估

| 风险 | 等级 | 根因 | 缓解 |
|------|------|------|------|
| `user_id` 含路径不安全字符 | 🟢 低 | 飞书 open_id 为 `ou_xxx`（字母数字） | 已知安全，必要时加 `re.sub` |
| 并发 ContextVar 泄露 | 🟢 低 | finally 块忘记清理 | try/finally 强制清理 |
| 模块级缓存遗漏 | 🟡 中 | 24+ 个缓存可能漏改 | 仅修 Gateway 相关的，CLI/Cron 不影响 |
| `gateway/run.py` 61+ 处替换回归 | 🟡 中 | 部分引用可能有特殊逻辑 | 逐一审查，启动阶段 ContextVar 为 None |
| SessionDB 连接数增长 | 🟢 低 | 每用户一个 SQLite 连接 | SQLite 连接极轻量 |

---

## 八、验证方案

### 单元测试

1. **ContextVar 隔离**：`set_hermes_home_ctx("/tmp/user_a")`，验证 `get_hermes_home()` 返回正确路径；清除后回退到 env var
2. **并发隔离**：两个 asyncio task 设置不同 ContextVar，验证互不影响
3. **MemoryStore 自动隔离**：设置 ContextVar 后创建 MemoryStore，验证写入 `user_profiles/{id}/memories/`
4. **Skills 自动隔离**：设置 ContextVar 后调用 `get_skills_dir()`，验证返回 `user_profiles/{id}/skills/`
5. **SessionDB 隔离**：per-user `db_path` 验证独立存储

### 集成验证

1. 启动飞书 Gateway
2. 用户 A 发消息 → 检查 `~/.hermes/user_profiles/{user_a}/memories/MEMORY.md` 创建
3. 用户 B 发消息 → 检查 `~/.hermes/user_profiles/{user_b}/memories/MEMORY.md` 创建
4. 验证 A 看不到 B 的记忆，B 看不到 A 的记忆
5. 触发 skill nudge → 验证写入正确用户的 `skills/` 目录
6. 用户 A 搜索历史会话 → 只搜到自己的会话（独立 `state.db`）
7. CLI 模式 `hermes` 命令 → 仍使用基础 Profile，无回归

---

## 九、与现有方案的对比

| 方案 | 隔离范围 | 改动量 | 并发安全 | 复杂度 |
|------|---------|--------|---------|--------|
| **A: Memory 子目录** | 仅记忆 | ~20 行 / 3 文件 | ✅ | 低 |
| **B: per-user Profile（本方案）** | 记忆+会话+技能+配置 | ~160 行 / 9 文件 | ✅ | 中 |
| **C: 多进程** | 完全隔离 | 0 行代码 | ✅ | 运维高 |

本方案选择 **B**：在单进程内通过 ContextVar 实现等价于多进程的完全隔离，兼顾隔离强度和运维简单性。

---

## 十、相关页面

- [[hermes-agent/Memory System]] — 三层记忆架构，冻结快照，自学习触发
- [[hermes-agent/Multi-Tenant Isolation]] — 四层隔离体系（身份/数据/权限/计费）
- [[hermes-agent/Feishu SaaS Architecture]] — 飞书 SaaS 总体架构
- [[hermes-agent/Skills System]] — agentskills.io 技能系统
- [[hermes-agent/Security Model]] — 七层安全模型
- [[outputs/2026-04-17-hermes-isolation-session-learning]] — 源码深度分析报告
