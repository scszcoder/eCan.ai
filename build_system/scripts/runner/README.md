# GitHub Actions Self-Hosted Runner 注册脚本

> **源文件**
> - `build_system/scripts/runner/register_runner.sh`（Linux x64 / macOS x64|arm64）
> - `build_system/scripts/runner/register_runner.ps1`（Windows x64|arm64）
>
> 维护者：eCan.AI Build Team · 最近一次源码同步：见 git log

本文档由两个角度组织：
1. **[第一部分 使用手册](#第一部分-使用手册)** —— 新成员第一次跑通的自助步骤。
2. **[第二部分 技术规格](#第二部分-技术规格)** —— 与 `release.yml` matrix 对齐的实现细节，便于排错与改造。

---

## 第一部分 使用手册

### 0. 这两个脚本在做什么

把一台本机（Linux/macOS/Windows）注册成 **eCan.ai** 仓库下的 GitHub Actions self-hosted runner，并打上固定的 label，使 `release.yml` 中的 `runner_group` 矩阵能精确路由到此机器：

| 平台 | Label 四元组 | 对应 `runner_group` |
|------|--------------|--------------------|
| Linux x64 | `self-hosted,linux,x64,ecan-build` | `ecan-linux-amd64` |
| macOS x64 | `self-hosted,macos,x64,ecan-build` | `ecan-macos-amd64` |
| macOS arm64 | `self-hosted,macos,arm64,ecan-build` | `ecan-macos-arm64` |
| Windows x64 | `self-hosted,windows,x64,ecan-build` | `ecan-windows-amd64` |
| Windows arm64 | `self-hosted,windows,arm64,ecan-build` | `ecan-windows-arm64` |

> Label **不要改**，否则 `release.yml` 的 matrix filter 会过滤不到该机器，构建永远不会触发。

### 1. 前置条件

| 平台 | 必须满足 |
|------|---------|
| Linux | `systemctl`（systemd）、`curl`、`tar`、`sudo`（含 NOPASSWD 或能交互输入密码） |
| macOS | `curl`、`tar`；管理员账户（用于 LaunchDaemon） |
| Windows | PowerShell 5.1+（系统自带）；管理员 PowerShell（用于安装 Windows 服务） |
| 通用 | 可联网到 `github.com`、`api.github.com`、`objects.githubusercontent.com` |

### 2. 申请一次性注册 Token

registration token **只能用一次**，有效期约 1 小时。两种方式：

```bash
# GitHub CLI（推荐）
gh api -X POST /repos/<owner>/<repo>/actions/runners/registration-token --jq '.token'
```

或者 GitHub UI：**Settings → Actions → Runners → New self-hosted runner** 页面会显示。

> ⚠️ 切勿把 PAT 当成 registration token。

### 3. 各平台执行示例

#### 3.1 Linux / macOS（bash）

```bash
cd build_system/scripts/runner
export GITHUB_OWNER=liuqiang
export GITHUB_REPO=eCan.ai
export RUNNER_NAME=ecan-mac-arm64-01   # 可选，默认 = hostname
./register_runner.sh <registration-token>
```

也可以从 stdin 注入（避免 shell history 泄漏）：

```bash
cat /path/to/token.txt | ./register_runner.sh --stdin
```

#### 3.2 Windows（PowerShell 管理员）

```powershell
cd build_system\scripts\runner
$env:GITHUB_OWNER = 'liuqiang'
$env:GITHUB_REPO  = 'eCan.ai'
$env:RUNNER_NAME  = 'ecan-windows-amd64-01'   # 可选，默认 = $env:COMPUTERNAME
.\register_runner.ps1 -Token "<registration-token>"
```

或经环境变量（避免在进程列表中暴露 token）：

```powershell
$env:RUNNER_TOKEN = "<registration-token>"
.\register_runner.ps1
```

### 4. 期望输出

脚本尾部会打印：

```
────────────────────────────────────────────────────────────────────────────
Done.
  Runner name : ecan-windows-amd64-01
  Repo        : https://github.com/liuqiang/eCan.ai
  Labels      : self-hosted,windows,x64,ecan-build
  Next step   : In the 'Run workflow' UI, pick
                runner_group = ecan-windows-x64
  Service     : Get-Service "actions.runner.liuqiang-eCan.ai.ecan-windows-amd64-01"
────────────────────────────────────────────────────────────────────────────
```

并通过 GitHub REST API 回查标签是否全部出现，缺一即 exit code **3**。

### 5. 验证 & 日常运维

| 动作 | Linux / macOS | Windows |
|------|---------------|---------|
| 查看 service 状态 | `sudo ./svc.sh status` | `& .\svc.cmd status` |
| 查看实时日志 | `sudo journalctl -u actions.runner.<repo>-<name> -f` | Event Viewer → Applications and Services Logs → `actions.runner.*` |
| 重新注册（更新 label） | 直接重跑脚本即可（`--replace`） | 同左 |
| 彻底卸载 | `sudo ./svc.sh uninstall && sudo ./svc.sh stop` | `& .\svc.cmd uninstall` |

### 6. 常见失败

| 现象 | 原因 / 处理 |
|------|------------|
| `unsupported OS: ...` | 用错脚本；macOS/Linux 必须用 `.sh` |
| `sudo requires password; will be prompted...` | 需有 sudo 权限或配置 `NOPASSWD` |
| `download failed` | 网络受限；手动下载 `actions-runner-{os}-{arch}-<ver>.{tar.gz|zip}` 放到 `RUNNER_DIR` 后重跑 |
| `runner '<name>' not found in API` | token 已过期，重新申请 |
| `MISSING required labels: ...` | GitHub 端残留旧 runner 持有同名；先在 UI 删除再重跑 |

---

## 第二部分 技术规格

### 1. 行为契约

脚本对外的"事实契约"如下，任何修改都必须保持它们与 `release.yml` 一致：

| 契约 | 取值 / 说明 |
|------|------------|
| Runner 版本 | `RUNNER_VERSION=2.336.0`（PowerShell 默认；bash 也引用同值） |
| 安装目录 | Linux/macOS：`$HOME/actions-runner`；Windows：`%USERPROFILE%\actions-runner` |
| 工作目录 | `_work`（与 runner 默认一致） |
| 服务名 | `actions.runner.<repo-with-slashes-as-dashes>.<runner-name>` |
| Label 集合 | `self-hosted,<os-label>,<arch>,ecan-build`（4 项） |
| `os-label` | `linux` / `macos` / `windows`（与 workflow `matrix.runner` 字符串一致） |
| arch 映射 | Linux `x86_64|amd64 → x64`，`aarch64|arm64 → arm64`；macOS `x86_64 → x64`，`arm64 → arm64`；Windows `PROCESSOR_ARCHITECTURE` 同上 |
| tarball/zip 命名 | `actions-runner-{linux|osx|win}-{x64|arm64}-{ver}.{tar.gz|zip}` |
| 注册方式 | `--unattended --replace --runasservice`（macOS 上 `--runasservice` 被静默忽略） |
| 退出码 | `0` 成功 / `1` 通用失败 / `2` runner 未找到 / `3` label 不全 |

### 2. 关键流程图

```
�────────────────────────┐
│  校验 token / 解析参数 │
└──────────┬─────────────┘
           ▼
┌────────────────────────┐
│  检测 OS / arch / label│
└──────────┬─────────────┘
           ▼
┌────────────────────────┐                 ┌──────────────────────────┐
│  RUNNER_DIR 内有         │──否──► 下载并解压 │ https://github.com/      │
│  config.sh/config.cmd? │                │ actions/runner/releases  │
└──────────┬─────────────┘                 └──────────────────────────┘
           │是（已有 runner）
           ▼
┌────────────────────────────────────┐
│  svc stop + svc uninstall（旧服务）  │
└──────────┬─────────────────────────┘
           ▼
┌──────────────────────────────────────────┐
│  config.sh / config.cmd                  │
│  --unattended --replace                   │
│  --url / --token / --name / --labels      │
│  --work _work --runasservice              │
└──────────┬───────────────────────────────┘
           ▼
┌──────────────────────────────────────────┐
│  svc install + svc start                 │
│  sleep 3 + svc status                    │
└──────────┬───────────────────────────────┘
           ▼
┌──────────────────────────────────────────┐
│  GitHub REST API 回查                    │
│  GET /repos/{owner}/{repo}/actions/runners│
│  校对 labels 与 expected 完全一致         │
└──────────┬───────────────────────────────┘
           ▼
┌──────────────────────────────────────────┐
│  打印 Done. 块（runner / repo / labels /  │
│  runner_group 提示 / 服务名）             │
└──────────────────────────────────────────┘
```

### 3. 与 release.yml 的耦合点

`.github/workflows/release.yml` 中通过 `matrix.include[*].runner` 路由：

```yaml
matrix:
  include:
    - runner_group: ecan-windows-amd64
      build_arch: amd64
      runner: [self-hosted, windows, x64, ecan-build]
```

注册脚本产出的 label 必须**等于** `runner` 数组中元素的全集（顺序无所谓），且 `runner_group` 取值必须严格匹配 `include[*].runner_group`。任何一边改动都会导致构建不触发。

### 4. 与 eCan 构建环境的协同

- **Runner 不必预装 Python/Node/Inno Setup**：release.yml 的 `setup-python-env` / `setup-node-env` / `Install Inno Setup` 等 step 会在每次 job 内重新初始化。Runner 只提供 OS + 网络 + sudo / 管理员能力。
- **缓存目录**：构建缓存命中依赖于 runner **磁盘持久**（`~/.cache/pip`、`gui_v2/node_modules`、`third_party/ms-playwright` 都在 runner 本地）。
- **磁盘空间**：建议预留 ≥ 30 GB；PyInstaller + Playwright Chromium 解压后会超过 8 GB。

### 5. 安全考量

| 项 | 设计 |
|----|------|
| Token 注入 | bash 提供 `--stdin` 与位置参数；PowerShell 提供 `-Token` 与 `$env:RUNNER_TOKEN`。命令列表中默认不出现 token。 |
| GitHub API 回查 | 优先使用 `gh auth token`；无 `gh` 时静默跳过校验，仅打 `[warn]`。 |
| sudo | `sudo -n` 探测 NOPASSWD；否则提示将交互输入密码。 |
| OTA 私钥 / 代码签名 | **不在** runner 本地存放；由 GH Actions secret 在 job 内注入（见 `release.yml` 的 `OTA_ED25519_PRIVATE_KEY` / `WIN_CERT_PFX`）。 |
| 文件权限 | 不创建 / 写私钥到 runner 本地；如果将来引入，注意 set ACL `owner=R`（CI 中已有脚本示例）。 |

### 6. 可定制参数

| 变量 | 默认 | 含义 |
|------|------|------|
| `GITHUB_OWNER` | （空，必填或交互输入） | owner / org |
| `GITHUB_REPO` | （空，必填或交互输入） | repo 名 |
| `RUNNER_NAME` | hostname / `%COMPUTERNAME%` | GitHub UI 上的展示名 |
| `RUNNER_VERSION` | `2.336.0` | actions/runner 版本 |
| `RUNNER_DIR` | `$HOME/actions-runner` / `%USERPROFILE%\actions-runner` | 安装目录 |
| `WORK_DIR` | `_work` | runner 工作目录 |

> 升级 Runner 版本时请同时跑一遍 `register_runner.sh` 与 `register_runner.ps1`（CI 中 `actions/checkout` / `actions/setup-python` 兼容性需要验证）。

### 7. 限制与已知约束

1. **token 一次有效**：脚本无重试逻辑；过期即 fail，需要重跑。
2. **同名冲突**：`--replace` 要求 runner name 在仓库内唯一；若 GH 端存在同名 offline runner 残留，先在 UI 删除。
3. **离线环境**：无法从 GitHub 下载 tarball 时需手动放置；脚本已设计为"目录内已有 `config.sh/config.cmd` 时跳过下载"。
4. **macOS arm64 路径**：GitHub 官方 tarball 命名为 `actions-runner-osx-arm64-*`，脚本中 `PLATFORM_OS=osx` 与 `LABEL_OS=macos` 是有意解耦的。
5. **Windows ARM64**：当前 `release.yml` 仅启用 `windows-latest`（x64）；脚本已支持 arm64 以备扩展。

### 8. 故障矩阵（用于排错）

| 阶段 | 失败模式 | 排查动作 |
|------|---------|---------|
| 下载 | HTTP 4xx/5xx | `curl -fI https://github.com/actions/runner/releases/download/v${RV}/${PKG}` |
| 解压 | zip 损坏 | 重新下载；或校验 sha256 与 GitHub Release Notes |
| config | 401 / token invalid | 重新申请 token |
| config | name already exists | 改名或先在 UI 删除 |
| svc install | 权限不足 | macOS/Linux：sudo；Windows：用管理员 PowerShell |
| svc start | 端口占用 | 检查 `_diag/` 目录；runner 默认 0 端口监听，问题罕见 |
| API verify | 403 rate limit | 等 60 s 重跑，关闭 `gh auth token` 兜底即可 |
| API verify | label 不全 | runner 端未注册成功，重新执行 `config.cmd`（不重下） |

### 9. 版本演进记录（建议保留）

| 版本 | Runner Version | 备注 |
|------|----------------|------|
| 当前 | 2.336.0 | 与线上 `win-runner` 同步：升级后若出现 `Prepare workflow directory ... Access to the path 'C:\actions-runner\_work\_actions\... is denied.`，按 `docs/Windows构建环境部署清单.md` 「与 CI 的差异点」清缓存 |

升级时请同步：
- `.github/actions/setup-python-env/action.yml`（无直接影响）
- `release.yml` 中 `setup-python` 版本要求
- 私有镜像（如使用）：重新构建并 push runner 镜像

---

## 附录 A：最小化排错脚本（粘贴即用）

**bash：**

```bash
curl -fI https://github.com/actions/runner/releases/latest \
  && gh auth status \
  && sudo -n systemctl is-system-running \
  && echo "OK"
```

**PowerShell：**

```powershell
Test-NetConnection github.com -Port 443
gh auth status
Get-Service | Where-Object { $_.Name -like "actions.runner.*" } | Format-Table
```
