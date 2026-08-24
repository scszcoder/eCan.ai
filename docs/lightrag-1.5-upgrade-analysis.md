# LightRAG 1.5 升级分析与实施建议

更新日期：2026-08-22

> **实施状态**：本档分析于 2026-08-21 提出建议；阶段 B + 阶段 C 已在本次提交完成（删除 1.4-only 整体替换、`SUPPORTED_MIN_VERSION` 抬到 1.5.0、所有依赖固定到 1.5.6、客户端使用 1.5 新 API）。阶段 A 仍需追溯（4 个 patch 的删除 + 文档更新见下）。

## 结论

当前工程不应只修改 `lightrag-hku` 版本号后直接发布。推荐目标为最新稳定版 **LightRAG 1.5.6**，而不是当前上游最新预发布版 `1.5.7rc2`。升级前必须先去除或缩小对 LightRAG 内部模块的整体替换，否则会覆盖 1.5.x 的新实现，并可能造成数据一致性、安全和任务调度回退。

建议按三阶段升级：

1. 先统一当前依赖到 1.4.16，消除不同构建产物分别使用 1.4.10/1.4.16 的问题。
2. 将自定义代码改为稳定 API 适配层，停止整体替换 `document_routes` 和复制 `extract_entities`。
3. 升级到 1.5.6，同时接入流式进度、受限调度、动态文件能力、处理策略和恢复/审计能力。

## 已核实的版本状态

| 项目 | 当前状态 | 风险 |
|---|---|---|
| `requirements-web.txt` | `lightrag-hku==1.4.10` | Web 构建仍使用旧版 |
| `requirements-worker.txt` | `lightrag-hku==1.4.10` | Worker 与基础构建不一致 |
| `requirements-base.txt` | `lightrag-hku==1.4.16` | 已部分升级 |
| `lightrag_patch.py` | 明确按 1.4.16 重写 | 在 1.4.10 环境中存在行为漂移 |
| 上游本地仓库 | `v1.5.7rc2-47-g79c7e361` | 位于 RC 后开发提交，不适合作为生产固定点 |
| 最新稳定标签 | `v1.5.6` | 推荐生产目标 |

## 当前集成方式

当前工程已经不是简单调用 LightRAG API，而是深度嵌入：

- 进程内启动 `lightrag.api.lightrag_server`，并管理健康检查、重启与代理环境。
- 使用 `LIGHTRAG-WORKSPACE` 实现请求级工作区隔离。
- 封装文档上传、扫描、替换、删除、取消、分页、图谱编辑和流式查询。
- 实现非原生 rerank provider 代理和置信度评分。
- 整体替换 `lightrag.api.routers.document_routes`。
- 替换 `extract_entities` 和 `_validate_and_fix_document_consistency` 等内部函数。
- 注入自定义 chunker、HTTP 客户端取消和引用分数逻辑。

这些功能有实际价值，但后四项依赖上游私有实现，是 1.5 升级的主要阻碍。

## 1.5.6 值得接入的能力

### 1. 有界任务调度与背压

1.5.x 增加了 `MAX_PENDING_DOCUMENTS`、`MAX_TEXTS_PER_REQUEST`、`MAX_REQUEST_BODY_BYTES`、手工重试队列限制、批次 feeder 和调度指标。它们可以直接解决当前工程曾经通过自定义代码处理的“批量过大、队列假死、取消不及时”问题。

建议桌面端初始配置：

```dotenv
MAX_PENDING_DOCUMENTS=200
MAX_TEXTS_PER_REQUEST=50
PIPELINE_REQUIRE_STRICT_STORAGE_READS=false
```

具体数值应通过 10/100/500 文档压测确定。非 JSON 存储后端验证严格点读能力后，可将 `PIPELINE_REQUIRE_STRICT_STORAGE_READS` 设为 `true`。

### 2. 更安全的失败恢复与删除

1.5.x 引入严格存储读取、失败关闭式 purge、跨存储恢复日志、自定义 chunk 操作 journal、死进程 reservation 恢复和 KG 完整性审计。当前 `lightrag_patch.py` 会复制并替换一致性修复函数，升级后反而会绕过这些保护。

建议删除该整函数替换，改为：

- 取消动作走上游 pipeline cancel/reservation API。
- 用户取消状态保存在 eCan 自己的状态表中，而不是修改 LightRAG 私有重置算法。
- 必须保留 metadata 时，只在 API 边界写入并通过集成测试验证状态迁移。

### 3. 多种文档解析和分块策略

1.5.x 支持通过 `process_options` 选择固定 token、递归字符、语义向量、段落语义和自定义分块（`F/R/V/P/C`），还支持跳过 KG、按文件 hint/rule 选择解析引擎，以及原生 Markdown/Docx 智能标题能力。

推荐在 eCan 知识库上传 UI 中增加“处理策略”：

- 默认：`F`，速度快且行为稳定。
- 长篇 Markdown/技术文档：`R` 或 `P`。
- 语义边界重要的合同/报告：`V`，但需要额外 embedding 成本。
- 仅向量检索、不构建 KG：`!F`。
- eCan 自定义 chunker：显式选择 `C`，不再全局猴子补丁注入。

### 4. 动态文件能力发现

上游已提供支持文件类型与 parser capability matrix。当前 `LightragClient.ALLOWED_EXTENSIONS` 是静态列表，可能显示实际上无法解析的格式，也无法自动获得新格式。

建议启动后读取上游 capability API，缓存 5 分钟；API 不可用时才回退静态列表。

### 5. 流式查询进度与性能指标

`/query/stream` 新增可选 `include_progress`，能够返回检索阶段进度和最终 `response_time`。当前客户端尚未转发该字段。

建议：

- UI 查询默认传 `include_progress=true`。
- 解析 `progress` 事件并显示“关键词提取 / 图谱检索 / 文本检索 / 生成答案”。
- 记录 `response_time`、首 token 时间、检索时间，替换仅靠本地总耗时推测性能的方式。
- MCP 保持默认 `false`，直到其流事件 schema 加入进度事件，避免旧调用方把进度误当答案。

### 6. 内容去重与来源冲突修复

1.5.x 加强内容 hash 去重、同请求去重、重复来源文件保留和 source-conflict repair。当前工程的 `replace_document` 先删后传逻辑应迁移到上游修复/重处理语义，减少删除成功但上传失败造成的知识缺口。

### 7. 图谱和运维能力

可接入 KG integrity audit/rebuild 工具、图谱读取一致性改进、PostgreSQL 原生图存储以及调度指标。对企业部署，建议优先评估 PostgreSQL 原生图存储，减少单独维护 Neo4j/AGE 的复杂度；桌面单机继续使用现有轻量存储。

## 主要兼容性问题

### 整体替换 document routes

当前 `third_party/lightrag_custom/document_routes_custom.py` 约 3452 行；1.5.6 上游 `document_routes.py` 约 7229 行。继续执行 `sys.modules` 整体替换会丢失新版本的：

- admission/backpressure；
- 新 parser 和 process options；
- 动态能力发现；
- 严格删除与恢复；
- 请求体和文件名安全限制；
- 新扫描与手工重试状态机。

应把 Excel 空列清理放到上传前预处理，把停止检查放到 eCan 的任务控制层或上游公开取消接口，彻底移除模块替换。

### 整体替换 extract_entities

当前 `operate_custom.py` 复制的是旧提取流程，而上游 1.5.x 已包含新的合并、截断、恢复、multimodal 和可观察性逻辑。继续替换会让新版本名义升级、核心抽取实际仍停留在旧实现。

应改用上游受管后台任务和取消机制。若仍有缺口，只在 LLM 调用边界注入 cancellation token，不复制整条抽取算法。

### 覆盖一致性修复函数

1.5.6 的 `_validate_and_fix_document_consistency` 已加入严格点读、journal 保护、metadata 规范化等逻辑。旧补丁覆盖它会产生数据删除或恢复风险，必须移除。

### Python Web 依赖

1.5.5/1.5.6 对 `python-multipart` 和 `starlette` 提高了安全版本下限；当前工程固定 `python-multipart==0.0.20`、`starlette==0.46.1`、`fastapi==0.115.11`。因此升级必须作为 FastAPI/Starlette 依赖组整体解析和回归，不能只改单个包。

## 推荐实施步骤

### 阶段 A：基线收敛 ✅ 已完成

1. 将三个 requirements 文件的 LightRAG 版本统一到 1.5.6（详见 `tests/unit/test_lightrag_dependency_version.py`）。
2. 构建测试断言所有 requirements 中 LightRAG 版本一致。
3. 启动时版本日志和支持区间检查由 `knowledge/lightrag_compat.support_status` 提供。
4. **取消 1.4 回归集**：1.4 不再受支持（见下文阶段 B）。

### 阶段 B：解除私有实现耦合 ✅ 已完成

1. 移除 `replace_document_routes()`、删除 `third_party/lightrag_custom/document_routes_custom.py`（3471 行）。
2. 移除整函数 `extract_entities` 替换；删除 `_legacy_1_4x/operate_custom.py`（754 行）。
3. 移除整函数一致性修复替换；删除 `_legacy_1_4x/lightrag_patch.py`（230 行）。
4. 自定义 chunker 仍走 `patch_lightrag_init()` 注入到 `chunking_func`，1.5 在 `process_options` 不指定 F/R/V/P 策略时仍调它。
5. 保留 rerank 代理、置信度评分、`LIGHTRAG-WORKSPACE` header 和 Lambda header 注入——这些是 eCan 的独立价值，与上游 1.5 不冲突。

副作用：
- GUI 的 chunk-level 进度字段（`total_chunks` / `processed_chunks` / `current_chunk_file`）从 `operate_custom.py` 注入改为 1.5 上游不提供；保留字段名为 `None` 以兼容旧 GUI 渲染（仅显示 batch-level 进度）。
- `knowledge/stop_controller.async_request_stop()` 不再调 `cancel_all_extraction_tasks`，只翻本地标志位；GUI 必须先调 `POST /cancel_pipeline` 再翻标志位才能真正取消正在运行的 LLM。

完成标准 ✅：对上游包的 patch 只发生在明确、短小且有签名断言的边界（`patch_lightrag_init` / `patch_ssl` / `patch_utils_for_confidence_scoring` / `patch_openai_client_for_lambda_proxy` / `patch_httpx_timeout_compat`）；不再复制上游路由或核心 pipeline。

### 阶段 C：升级 1.5.6 ✅ 已完成

1. 所有 `requirements-*.txt` 锁到 `lightrag-hku==1.5.6`（`tests/unit/test_lightrag_dependency_version.py` 守门）。
2. `LightragClient` 已使用 `get_supported_file_types`、workspace-scoped `get_pipeline_status`、`include_progress`、`metrics` chunk（`tests/unit/test_lightrag_15_client.py` 守门）。
3. `support_status` 抬到 `[1.5.0, 1.5.6]`；1.4.x 触发 `below_minimum` WARNING 并提示升级，不再提供 monkey-patch 回退。

### 阶段 D：可选优化

- 评估 `PGTableGraphStorage`（上游 1.5.0 #3103）替代 AGE，避免 1.5.6 #3621 强制禁止 AGE ≥ 1.8.0 的问题。
- 评估 Smart Heading（上游 1.5.5 #3364）提升结构混乱的 DOCX 的 chunking 质量。
- 在 `process_options` 默认值里显式选 `C` 策略以避免 `chunking_func` 在指定策略时的 silent no-op 风险。

## 必须覆盖的测试

- 同一内容同名/异名重复上传。
- 文档在 PENDING、PARSING、ANALYZING、PROCESSING 各阶段取消。
- 进程强杀后恢复，确认不会重复抽取或误删状态行。
- 替换文档中途网络失败。
- workspace A/B 上传、查询、删除完全隔离。
- embedding 模型和维度变化时明确拒绝或迁移。
- 100/500/2000 文档入队时内存有界并正确返回 413/429/503。
- 流式协议同时覆盖旧模式和 `include_progress=true`。
- JSON、PostgreSQL、Neo4j/Milvus 等实际启用存储组合的数据一致性。
- 中英文 Markdown、PDF、Docx、Excel 和图片文档解析。

## 回滚原则

LightRAG 升级涉及持久化数据结构和恢复语义。回滚应以“程序 + 完整工作区快照”为单位，不能让 1.4.16 直接继续写入已经由 1.5.6 迁移或补充过的数据目录。灰度期间每个 workspace 应有独立副本，并记录 embedding 模型、维度、LightRAG 版本和存储 schema 版本。

## 最终建议

短期先完成阶段 A，这能立即消除现有版本漂移；随后优先做阶段 B。真正的 1.5.6 升级应放在解除私有实现耦合之后。这样才能实际获得 1.5.x 的调度、恢复、解析和安全能力，而不是只让包版本号变新、运行路径仍由旧复制代码控制。
