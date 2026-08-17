# Windows 构建环境部署清单

> 本清单基于 `release.yml` 中 `build-windows` job 与 `build_system/` 下的脚本 (`ecan_build.py`、`minibuild_core.py`、`build_validator.py` 等) 整理得出。
> 适用架构：**Windows 10/11 x64 (amd64)**。GitHub-hosted runner 默认 `windows-latest`。
> 构建命令：`python build.py prod --version <版本号>`

---

## 一、基础清单（必装，缺一不可）

| # | 软件 / 工具 | 版本要求 | 用途 | 说明 |
|---|------------|----------|------|------|
| 1 | Windows OS | Win10 1809+ / Win11 / Server 2019+ | 操作系统 | **当前 release.yml 仅启用 x64 job**；`register_runner.ps1` 脚本已支持 ARM64(对应 runner_group `ecan-windows-arm64`),但 `release-cn.yml` / `release-intl.yml` 目前没有 `build-windows-arm64` job,所以 ARM64 runner 暂时不会被调度 |
| 2 | Python | **3.12.x**（必须 ≥ 3.12，build_validator 会拒绝 3.11） | Python 解释器 | 勾选 "Add Python to PATH" |
| 3 | Git for Windows | 最新 LTS（≥ 2.40） | 拉取代码 | Git Bash 提供 shell 工具链，VS Code 也常配套 |
| 4 | Node.js | **20.x LTS**（前端 `gui_v2`） | 前端构建 | 必须 ≥ 18，Vite 5/6 + Rollup 需要 |
| 5 | npm | 随 Node.js 10.x 自带 | 前端依赖 | `npm ci --legacy-peer-deps` |
| 6 | PowerShell 5.1 | win10 自带 | Inno Setup 安装 / signtool 探测 / 语言包下载 | 需开启 `RemoteSigned` 执行策略 |
| 6a | **PowerShell 7 (`pwsh.exe`)** | **必装**（workflow 全体 `shell: pwsh`） | 与 GitHub-hosted `windows-latest` 保持一致 | `winget install Microsoft.PowerShell` 或 MSI 安装到 `C:\Program Files\PowerShell\7\` |
| 7 | **Inno Setup 6.x** | **6.7.1**（CI 使用该版本）→ 也可用 6.x 最新 | 生成 `.exe` 安装包 | 路径必须为 `C:\Program Files (x86)\Inno Setup 6\` |
| 8 | **Windows SDK**（Windows Kits 10） | 含 signtool.exe；推荐 **10.0.22621** 或更高 | EXE/DLL 数字签名（仅 release 必需） | Chocolatey 包 `windows-sdk-10-version-22621-all` |
| 9 | **Visual C++ Redistributable** | 2015-2022 x64 | PyInstaller / C 扩展运行支持 | 通常已自带；离线安装包 `_vc_redist.x64.exe` |

---

## 二、可选清单（按场景安装）

| # | 软件 / 工具 | 版本 | 场景 | 说明 |
|---|------------|------|------|------|
| 10 | Azure Code Signing Tools (`dlib` + `trustee`) | 1.0+ | 若使用 **Azure Trusted Signing** | 见 `signing_manager.py` 的 `AzureTrustedSigningManager` |
| 11 | Playwright 浏览器（Chromium） | 由 `playwright install chromium` 下载 | `agent/` 中的 `browser-use` 自动化 | 构建时把浏览器打到 `third_party/ms-playwright` 后随安装包分发 |
| 12 | Chocolatey | 最新 | CI 用 `choco install windows-sdk-10-version-*` | 本地手工安装可选 |
| 13 | UPX（UPX Compressor） | 5.x | `prod` 模式启用 `upx_compression:true` | PyInstaller 自动调用；缺失仅是性能提示 |

---

## 三、环境变量配置

### 1. 系统 PATH（用户级即可）

```
C:\Python312\
C:\Python312\Scripts\
C:\Program Files\Git\cmd
C:\Program Files\nodejs\
C:\Program Files (x86)\Inno Setup 6
C:\Program Files (x86)\Windows Kits\10\bin\<SDK版本>\x64   # 含 signtool.exe
```

验证命令（PowerShell）：
```powershell
python --version         # Python 3.12.x
node --version           # v20.x
npm --version            # 10.x
git --version            # git version 2.4x
where pyinstaller        # 应在 .venv\Scripts 下（激活 venv 后）
where Inno Setup         # 应定位到 ISCC.exe
where signtool           # 应定位到 signtool.exe
```

### 2. 签名相关（任选一种方案）

| 方案 | 环境变量 | 说明 |
|------|---------|------|
| **Azure Trusted Signing** | `AZURE_TENANT_ID` / `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET` / `AZURE_SIGNING_ENDPOINT` / `AZURE_SIGNING_ACCOUNT` / `AZURE_SIGNING_PROFILE` | **首选**，密钥不出 HSM；需配合 `Azure.CodeSigning.Dlib.dll` |
| **PFX 证书** | `WIN_CERT_PFX`（Base64 编码） / `WIN_CERT_PASSWORD` | 备用；私钥文件 + 密码；时间戳 `http://timestamp.digicert.com` |
| **跳过签名** | 在 build 命令加 `--skip-signing` | 本地开发测试可用；release 必须签名 |

### 3. OTA 签名（仅 production / staging / test 环境需要）

| 环境变量 | 说明 |
|----------|------|
| `OTA_ED25519_PRIVATE_KEY` | Base64 编码的 PEM 私钥内容 |
| `ECAN_ENVIRONMENT` | `production` / `staging` / `test` / `dev`；非 dev 环境若缺失会 **构建失败** |

构建脚本会把私钥解码后写入 `build_system/certificates/ed25519_private_key.pem`。

### 4. 构建标识

| 变量 | 必需 | 说明 |
|------|------|------|
| `ECAN_APP_ID` | 是 | `intl` / `cn`；不设默认 `intl` |
| `ECAN_APP_NAME` | 否 | 默认 `eCan` |
| `BUILD_ARCH` | 否 | Windows 仅支持 `amd64`（`aarch64` 会被 release.yml 显式拒绝） |
| `DIST_APP` | 否 | 默认 `eCan`（CN 版本为 `eCan.cn`） |
| `VIRTUAL_ENV` / `PYTHONPATH` | 推荐 | 指向仓库内 `.venv` |
| `PYTHONIOENCODING` / `CHCP` | 推荐 | 均设为 `utf-8` / `65001`，避免中文 log 乱码 |

---

## 四、安装步骤（推荐顺序）

### Step 1：操作系统与 PowerShell 策略
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force
# 启用长路径支持（Git for Windows 拉大仓库时需要）
git config --system core.longpaths true
```

### Step 2：安装 Python 3.12
- 下载 `python-3.12.x-amd64.exe`，**安装时勾选 "Add python.exe to PATH"**。
- 验证：`python -V` 与 `python -m pip --version`。

### Step 3：安装 Node.js 20 LTS
- `node-v20.x.x-x64.msi`，勾选 "Add to PATH"。
- 验证：`node -v` 与 `npm -v`。

### Step 4：安装 Git for Windows
- 默认安装；带 "Git from the command line and also from 3rd-party software" 选项。

### Step 5：安装 Inno Setup 6
两种方式二选一：
```powershell
# 方式 A：Chocolatey（推荐）
choco install innosetup -y

# 方式 B：下载官方安装包
Invoke-WebRequest -UseBasicParsing `
  -Uri "https://github.com/jrsoftware/issrc/releases/download/is-6_7_1/innosetup-6.7.1.exe" `
  -OutFile "$env:TEMP\innosetup-6.7.1.exe"
Start-Process -FilePath "$env:TEMP\innosetup-6.7.1.exe" `
  -ArgumentList "/SILENT","/SUPPRESSMSGBOXES","/NORESTART" -Wait
```

安装完务必让脚本感知 `ChineseSimplified.isl`（CN 版本需要）：
```powershell
$innoDir  = "${env:ProgramFiles(x86)}\Inno Setup 6"
$langsDir = Join-Path $innoDir "Languages"
New-Item -ItemType Directory -Force -Path $langsDir | Out-Null
Invoke-WebRequest -UseBasicParsing `
  -Uri "https://raw.githubusercontent.com/jrsoftware/issrc/is-6_7_1/Files/Languages/Unofficial/ChineseSimplified.isl" `
  -OutFile (Join-Path $langsDir "ChineseSimplified.isl")
```
也可直接执行仓库自带脚本：`python build_system/setup_inno_chinese.py`。

### Step 6：安装 Windows SDK（含 signtool）

```powershell
# Chocolatey 方式（CI 与本地都推荐）
choco install windows-sdk-10-version-22621-all -y --timeout 600

# 或者走 Visual Studio Installer：选 "Windows SDK" + ".NET 桌面开发"
```

完成后验证 `signtool /?` 能输出帮助；如果未识别，把对应 `bin\<SDK>\x64` 加入 PATH（脚本 `build_system/find_and_setup_signtool.ps1` 可自动挑选最优版本并写入当前会话 PATH）。

### Step 7：克隆仓库并建立 venv
```powershell
git clone <repo-url> eCan.ai
cd eCan.ai
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip wheel setuptools
pip install -r requirements-windows.txt -r requirements-intl.txt pyinstaller==6.18.0
```
关键版本参考 `requirements-base.txt` / `requirements-windows.txt`；PyInstaller 必须在 6.18.0（与 release.yml 设置一致）。

### Step 8：验证环境
```powershell
python build_system/build_validator.py -v
```
期望看到 `Overall Status: PASS`；若 `[Sign]` 或 `[Playwright]` 报错，按提示补工具/缓存即可。

### Step 9：执行构建
```powershell
# 标准 prod 模式
python build.py prod --version 0.7.0

# 若不需要签名（如纯本地 dev）
python build.py prod --version 0.7.0 --skip-signing

# 只产出安装包（已 PyInstaller 打过）
python build.py prod --version 0.7.0 --installer-only --skip-signing

# 跳过前端（CI 缓存命中时）
python build.py prod --version 0.7.0 --skip-frontend
```
构建结束后检查：
```
dist\eCan\eCan.exe
dist\eCan-<version>-windows-amd64-Setup.exe
```
可用 `python build_system/scripts/diagnose_windows_build.py` 二次确认。

---

## 五、与 CI 的差异点（自建机请对齐）

| 维度 | GitHub-hosted runner | 自建 Windows amd64 runner |
|------|---------------------|---------------------------|
| OS 镜像 | `windows-latest`（Server 2022） | Win10 1809+ / Server 2019+ |
| Python | `actions/setup-python` 3.12 + venv `.venv` | 同左 |
| Inno Setup | 脚本下载 6.7.1 exe 安装 | 用 Chocolatey / 复用已安装 |
| 签名 SDK | Chocolatey `windows-sdk-10-version-2004-all`（兼容；可升级到 22621） | 自装 Windows 10 SDK |
| C 缓存 | `~/.cache/pip`、`gui_v2/node_modules`、`third_party/ms-playwright` | 同左，路径替换为 Windows 等价 |
| 前端 Rollup | `npm ci --legacy-peer-deps` + `node18-win-x64` pkg 重建 wa_bridge | 同左 |

`register_runner.ps1` (`build_system/scripts/runner/`) 给出 GitHub Actions self-hosted runner 的注册脚本，请把 label 注册为 `windows, x64, ecan-build` 与 CI `matrix.runner` 保持一致。

> **⚠️ 自建 runner 升级或更换服务账户后，必须清空 `_work\_actions` 缓存**
>
> 现象：job 跑到 `Prepare workflow directory` 阶段报 `Access to the path 'C:\actions-runner\_work\_actions\actions\upload-artifact\v6\...' is denied.`。
>
> 原因：`_work\_actions\` 是 runner 第一次跑某个 action 时按当时服务账户身份缓存下来的 action 源码副本；若后续**升级了 runner 版本**或**把服务改用另一个账户跑**（如从管理员账户切到 `LocalSystem`，或反过来），新账户对旧缓存目录的 NTFS ACL 没有读取权限，runner 就拒绝继续。
>
> 修法（任选其一，**推荐 ①**）：
>
> ① 清缓存自愈（最稳）：
> ```powershell
> & C:\actions-runner\svc.cmd stop
> Remove-Item -Recurse -Force "C:\actions-runner\_work\_actions"
> Remove-Item -Recurse -Force "C:\actions-runner\_work\_tool"
> & C:\actions-runner\svc.cmd start
> ```
> 下次跑 job 时 runner 会按当前服务账户重新下载 action 副本。
>
> ② 给当前服务账户授权（保留缓存、不重新下载）：
> ```powershell
> $svc     = Get-CimInstance Win32_Service -Filter "Name='actions.runner.liuqiang-eCan.ai.win-runner'"
> $account = $svc.StartName
> foreach ($p in @("C:\actions-runner\_work\_actions","C:\actions-runner\_work\_tool")) {
>   if (Test-Path $p) { icacls $p /grant "${account}:(OI)(CI)RX" /T | Out-Null }
> }
> ```
> 若 `StartName = LocalSystem`，通常无需手动授权（SYSTEM 默认继承访问权）；如果还报错，走 ① 更稳。
>
> **预防**：升级 runner 版本前先停服务 → 备份 `_diag` 之外直接覆盖文件 → 重启服务时**保留同一个服务账户**；如确需换账户，按 ① 清一次缓存。

---

## 六、排错 Checklist

| 症状 | 排查点 |
|------|--------|
| `Python xxx is too old` | Python 必须 ≥ 3.12 |
| `signtool.exe not found` | 装 Windows SDK 或运行 `build_system/find_and_setup_signtool.ps1` |
| `Inno Setup not found` | 装 Inno Setup 6；路径必须在 `C:\Program Files (x86)\Inno Setup 6` |
| 中文 installer 回退英文 | 没放 `ChineseSimplified.isl` 到 `Languages\` 目录，重跑 `setup_inno_chinese.py` |
| Playwright 浏览器未打包 | 跑 `python -m playwright install chromium`，构建前确认 `third_party/ms-playwright` 非空 |
| OTA signing 失败 | dev 环境可忽略，非 dev 必须有 `OTA_ED25519_PRIVATE_KEY` |
| spec 文件路径乱码 | PowerShell 没设 `PYTHONIOENCODING=utf-8` & `chcp 65001` |
| 长路径报错 | `git config --system core.longpaths true` 且启用 Win32 Long Paths |
| `##[error]pwsh: command not found` (self-hosted runner) | win-runner 没装 PowerShell 7。按 §九.3.1 装 `pwsh.exe` (`winget install Microsoft.PowerShell` 或从 GitHub releases 下 MSI) |
| `##[error]bash: command not found` (self-hosted runner) | Git Bash 在 *user* PATH,`actions.runner.*-svc` 是 SYSTEM 账户看不到。按 §九.3.1 把 Git Bash 加到 SYSTEM PATH 然后重启 runner service |
| `Prepare workflow directory ... Access to the path 'C:\actions-runner\_work\_actions\... is denied.` | runner 服务账户对旧 `_work\_actions\` 缓存目录无读取权限；按「与 CI 的差异点」中 ① 清缓存或 ② icacls 授权 |

---

## 七、常用安装脚本片段（PowerShell，复制即可）

```powershell
# 一次性安装所有"基础清单"
choco install -y python --version=3.12.7 git nodejs-lts innosetup windows-sdk-10-version-22621-all

# 验证
python --version ; node --version ; npm --version
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /?
& "C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe" /?
```

---

## 八、安全 / 证书放置约定

| 资产 | 存放位置 | 权限 |
|------|---------|------|
| PFX 证书 | 不写盘；通过 env `WIN_CERT_PFX` (Base64) 注入 | — |
| OTA Ed25519 私钥 | `build_system\certificates\ed25519_private_key.pem`，仅当前用户可读（CI 用 ACL 收紧） | ACL: owner=R |
| 代码签名私钥 | Azure HSM（推荐）或 `WIN_CERT_PFX` 加载 | 仅 CI secret 注入 |

完成以上 1-9 步即可运行 `python build.py prod` 在本地出 eCan Windows 安装包。

---

## 九、Self-hosted Runner 安装规范

> 本章专门覆盖 `register_runner.ps1` 注册 GitHub self-hosted runner 的标准做法,
> 以及 `_work\` 子目录出现 `Access to the path ... is denied` 的根因与标准修法。
> 配套脚本：`build_system/scripts/runner/diagnose-work-acl.ps1`（只读）、
> `build_system/scripts/runner/apply-work-acl-fix.ps1`（写 ACL，需二次确认）。

### 1. 角色 / 名称 / 目录

| 项 | 规范值 | 备注 |
|---|---|---|
| Runner name | `win-runner` | 与 GitHub UI 注册名一致 |
| Runner group | `Default` | 组织级可见即可 |
| 机器名 | `GIT-HOST-RUNNER` | 物理机 / VM 名 |
| 安装目录 | `C:\actions-runner\` | **必须** `C:\` 根,不要放 `D:\` 或文件同步目录 |
| 工作目录 | `C:\actions-runner\_work\` | 不要改 `--work` 参数 |
| Labels | `self-hosted,windows,x64,ecan-build` | 与 `release.yml` matrix 完全一致 |
| Runner version | `2.336.0` | `register_runner.ps1` 默认 |
| 工作账户 | `NT AUTHORITY\SYSTEM` | 由 `config.cmd --runasservice` 默认产生 |

> ⚠️ **不要把 work 路径放在 `D:\`。** `D:\` 上若被 EFS / 域策略 / 卷加密,即使 SYSTEM 也不能自由写,会出现与当前完全相同的 Access Deny。

### 2. 三个互斥的安装路径(选一个,不要混用)

| 路径 | 适用 | 风险 |
|---|---|---|
| **A. 默认 LocalSystem (`config.cmd --runasservice`) ← ★ 推荐** | 90% 场景 | 看不见已登录用户的证书 / 凭据 |
| B. `sc config obj= DOMAIN\svc-actions` | 需要访问域内资源(文件共享、证书私钥) | 维护账户,密码过期要换 |
| C. `gMSA`(Group Managed Service Account) | 域账户 + 自动密码轮换 | 域控配合度高 |

**eCan.ai 暂不涉及域凭据,默认 A 即可**。如以后要 B 或 C,只可二选一、不要中途切换——见第 6 节"账户变更的代价"。

### 3. 安装命令(标准流程)

```powershell
# 1) 在 Administrator PowerShell 里
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force

# 2) 解出注册 token(在 GitHub UI: Settings → Actions → Runners → New runner)
$env:RUNNER_TOKEN = "ABC123..."
$env:RUNNER_NAME  = "win-runner"

# 3) 跑注册脚本
cd C:\actions-runner
.\register_runner.ps1

# 4) 注册完,必跑诊断
.\diagnose-work-acl.ps1
```

`register_runner.ps1` 自动完成的 7 件事:

| 步骤 | 由脚本完成 | 标准值 |
|---|---|---|
| 创建 runner 目录 | ✅ | `C:\actions-runner\` |
| 下载 2.336.0 zip | ✅ | `actions-runner-win-x64-2.336.0.zip` |
| 解压 | ✅ | 同级目录 |
| 停 + 卸载旧 service | ✅ | `svc.cmd stop / uninstall` |
| config `--unattended --replace` | ✅ | **没有账户参数** → 默认 `LocalSystem` |
| install / start service | ✅ | `svc.cmd install / start` |
| 验证 labels via GitHub API | ✅ | `self-hosted,windows,x64,ecan-build` |

### 3.1 Windows runner 必备工具(与 GitHub-hosted `windows-latest` 对齐)

> **运行机制**:release-cn.yml 的每一个 self-hosted Windows job
> 第一个 step 是 `Ensure Git Bash + PowerShell 7 are on runner-service
> PATH`。它**幂等**:
>
> 1. **`PowerShell ExecutionPolicy` 探测** —— 必须 `LocalMachine =
>    RemoteSigned` (or higher). 若是 `Restricted` 直接 `::error::`
>    退出 (因为 GHA runner 用 `powershell -command ". '<guid>.ps1'"`
>    dot-source 临时 inline script, `Restricted` 拒绝 dot-source,
>    抢先 `UnauthorizedAccess` 立刻 exit 1 — 这是 log #86728979772
>    的真实根因)。
> 2. **Git Bash** 探测 `C:\Program Files\Git\bin\bash.exe`,没装就
>    `winget install Git.Git`。装好加到 `$GITHUB_PATH` 给后续 step。
> 3. **PowerShell 7** 探测 `C:\Program Files\PowerShell\7\pwsh.exe`,
>    没装就 `winget install Microsoft.PowerShell`,winget 失败 fallback
>    到 `Invoke-WebRequest` 下 MSI 直接装。
>
> **所以 runner 上**:**强烈建议**在 `register_runner.ps1` 跑完后**提前
> 装好**这三个 (`pwsh` + `Git Bash` + `ExecutionPolicy`),这样:
>
> - workflow 的 preflight step 跑得快 (只 `Test-Path` + `Get-ExecutionPolicy`
>   几次就 `[OK]`, 无 `winget` 调速, 无 `$env:TEMP` 残留 MSI)
> - 第一次跑 build 不用等 `winget` 把 PowerShell 7 下到本机 (网络差时
>   可能 5-10 分钟)
> - 重装 runner 系统后可以一次恢复到位,不用每次都跑 workflow 的 fallback
> - **最重要**: ExecutionPolicy 没法在 workflow step 里自动修 (它在
>   SYSTEM 范围,改要 elevated,要 restart service — `register_runner.ps1`
>   做这事)。如果 runner 上没修, preflight 立刻 `::error::` 精准报错
>   指向 `register_runner.ps1`,而不是 build 中途才被 catch 到。

#### 3.1.1 GitHub-hosted `windows-latest` vs self-hosted 工具差异表

`windows-latest` 跑的是
[`actions/runner-images`](https://github.com/actions/runner-images)
仓库里 `Windows2025-VS2026` 镜像 (release 时约 `2026-08-10` 版本) — 装了一大堆
工具。**self-hosted runner 不需要装全部**,只需要下面这张表里
**`operator-side` 列 = 是** 的那几个,workflow 其它工具 (Python, Node.js,
Inno Setup, signtool) 在 build job 内由对应 `setup-*` 复合 action 或
job-level step 自动装。

| Tool | GitHub-hosted `windows-latest` | self-hosted 当前 | 必须 operator-side 装? | 来源 / 安装命令 |
|---|---|---|---|---|
| PowerShell 5.1 (`powershell.exe`) | ✓ Win 内置 | ✓ Win 内置 | ❌ | 操作系统自带 |
| **PowerShell 7 (`pwsh.exe`)** | ✓ `C:\Program Files\PowerShell\7\pwsh.exe` | ✗ (除非手动) | ✅ | `register_runner.ps1` 自动装 / `winget install Microsoft.PowerShell` |
| **Git for Windows / Bash** | ✓ `C:\Program Files\Git\bin\bash.exe` | ✗ (除非手动) | ✅ | `register_runner.ps1` 自动装 / `winget install Git.Git` |
| **Chocolatey** | ✓ `C:\ProgramData\chocolatey\bin\choco.exe` (v2.7.3) | ✗ | ✅ | `register_runner.ps1` 自动装 (setup-signtool-env 的 fallback 路径需要 choco) |
| **PowerShell ExecutionPolicy=RemoteSigned** | ✓ Group Policy 锁定 | ✗ (`Restricted` 默认) | ✅ | `register_runner.ps1` 自动设 |
| Python (3.12) | ✓ `C:\hostedtoolcache\windows\Python\` | ✗ | ❌ | `actions/setup-python@v6` (via `setup-python-env` action) |
| Node.js (20 LTS) | ✓ `C:\hostedtoolcache\windows\node\` | ✗ | ❌ | `actions/setup-node@v6` (via `setup-node-env` action) 或 system Node |
| Chocolatey / signtool 关联 | ✓ 见上 | ❌ | ❌ | `setup-signtool-env` (用 choco 装 Windows SDK) |
| Inno Setup 6.7.1 | ✓ `C:\Program Files (x86)\Inno Setup 6\ISCC.exe` | ✗ | ❌ | `Install Inno Setup` step (在 build-windows job 内) |
| Windows SDK (signtool) | ✓ `C:\Program Files (x86)\Windows Kits\10\bin\<ver>\x64\signtool.exe` | ✗ | ❌ | `setup-signtool-env` (探测 / choco 装 / 手动) |
| 7zip / ImageMagick / jq / WiX / etc | ✓ 全套 | ✗ | ❌ | release workflow 不用,可按需装 |

`windows-latest` 自带 PowerShell 7 (`pwsh.exe`) + Git Bash,vanilla
self-hosted runner 这三个都没有。如果 build job 跑起来后才发现:

- 任何 `shell: pwsh` 的 step 立刻 `##[error]pwsh: command not found`
  (workflow 大量使用 PowerShell 7 现代语法:`?.` / `&&=` / 三目 / null-conditional)
- 任何 `shell: bash` 的 step 立刻 `##[error]bash: command not found`
  (Git for Windows 只把 bin 加到 *user* PATH,`actions.runner.*-svc` 是
  SYSTEM 账户,继承不到)
- 任何 `shell: powershell` / `shell: pwsh` 的 step 立刻
  `UnauthorizedAccess`: `File <...>_work\_temp\<guid>.ps1 cannot be
  loaded because running scripts is disabled on this system` (默认
  ExecutionPolicy `Restricted` 拒绝 dot-source runner 的 inline script
  wrapper — **真根因见 log #86728979772**)

**提前装**(runner 机器上 elevated PowerShell 跑一次,**`register_runner.ps1`
之前或之后**;`register_runner.ps1` 本身也会自动装这三个 + restart svc
再 exit, 所以**最稳的路径就是跑 `register_runner.ps1` 一遍**):

```powershell
# PowerShell 7 (二选一)
winget install --id Microsoft.PowerShell -e --source winget --accept-package-agreements --accept-source-agreements
# 或 MSI fallback:
Invoke-WebRequest -UseBasicParsing -OutFile "$env:TEMP\pwsh.msi" `
  "https://github.com/PowerShell/PowerShell/releases/download/v7.4.6/PowerShell-7.4.6-win-x64.msi"
msiexec.exe /i "$env:TEMP\pwsh.msi" /qn /norestart

# Git for Windows (workflow preflight 会自动装,但提前装更稳)
winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements

# ExecutionPolicy (LocalMachine=RemoteSigned)
# → 允许 runner dot-source 本地 inline script;仍然禁止 unsigned 互联网脚本
# → 必须在 elevated PowerShell 跑
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope LocalMachine -Force

# Git Bash bin 加到 SYSTEM PATH (Git for Windows installer 只加 user PATH)
# runner service 账户继承 SYSTEM PATH 看不到 Git Bash
[Environment]::SetEnvironmentVariable(
  "Path",
  [Environment]::GetEnvironmentVariable("Path","Machine") + ";C:\Program Files\Git\bin",
  "Machine"
)

# 重启 runner service — ExecutionPolicy 和 PATH 改完后必须 restart,
# 现有 service 进程不会重读这俩
& C:\actions-runner\svc.cmd stop
& C:\actions-runner\svc.cmd start
```

> **为什么 ExecutionPolicy 是 runner-side 一次性配置, workflow 兜底不了**:
> GHA runner 通过 `powershell -command ". '<guid>.ps1'"` 调
> `shell: powershell` step (见
> `actions/runner/src/Runner.Worker/Handlers/ScriptHandlerHelpers.cs`)。
> `Restricted` policy 拒绝 dot-source 本地 `.ps1` 文件, runner 失败
> 发生在 *这个 step 自身被 dot-source 之前* — workflow step 内部
> 写 `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` 也
> 太晚(进程已用 Restricted 启动)。唯一可行的修法是在 runner 端
> elevated 设 `LocalMachine=RemoteSigned`,然后重启 service 让新
> 子进程继承。`register_runner.ps1` 末尾已经自动做这件事。

**验证**(装好之后跑一遍;任意一条没满足,workflow preflight 都会失败,
不用等到 build 中途才发现):

```powershell
where.exe pwsh.exe                       # 期望: C:\Program Files\PowerShell\7\pwsh.exe
where.exe bash.exe                       # 期望: C:\Program Files\Git\bin\bash.exe
where.exe choco.exe                      # 期望: C:\ProgramData\chocolatey\bin\choco.exe
$PSVersionTable.PSVersion                # 期望: Major=7
Get-ExecutionPolicy -List                # 期望: LocalMachine = RemoteSigned (or higher)
[Environment]::GetEnvironmentVariable("Path","Machine") -split ";" | Where-Object { $_ -like "*Git*" }
# 期望: ...C:\Program Files\Git\bin
```

> **`choco.exe` 验证失败的话**:setup-signtool-env 在 signtool 缺失时会
> 走 Chocolatey fallback 装 Windows SDK。Chocolatey 没装这一步就
> `##[error]Chocolatey not available`,signtool 装不上,build-windows
> `Code sign Windows artifacts (PFX fallback)` 失败。手动一次性安装:
>
> ```powershell
> # Elevated PowerShell,Internet 可达 community.chocolatey.org
> [System.Net.ServicePointManager]::SecurityProtocol = `
>   [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
> Invoke-Expression ((New-Object System.Net.WebClient).DownloadString(
>   'https://community.chocolatey.org/install.ps1'))
> # 验证
> choco --version
> ```

### 4. ACL 标准(防 `Access Deny` 的关键)

`_work\` 不是 git 仓库一部分,完全由 runner 在第一个 job 跑时**按当前 service 账户身份**创建子目录。如果 service 账户对 `C:\actions-runner\` 没有显式 Full Control,就会出现 Access Deny。

**标准 ACL**:

| 路径 | Owner | 权限 |
|---|---|---|
| `C:\actions-runner\` | `BUILTIN\Administrators` | 继承 + `SYSTEM = Full Control` |
| `C:\actions-runner\_work\` | `SYSTEM`（首个 job 后） | 继承 + `SYSTEM = Full Control` |
| `C:\actions-runner\_work\_PipelineMapping\` | `SYSTEM` | 继承 + `SYSTEM = Full Control` |
| `C:\actions-runner\_work\_actions\` | `SYSTEM` | 继承 + `SYSTEM = Full Control` |

**标准设置命令**:

```powershell
# ① 极简版 —— 一行搞定,不需要 diagnose
.\apply-work-acl-fix.ps1

# ② 手动版（脚本不存在时）
# 注意: NT AUTHORITY\SYSTEM 里有反斜杠,加双引号要写成 \" 转义
cmd /c "icacls C:\actions-runner /inheritance:e /T"
cmd /c 'icacls "C:\actions-runner" /grant "NT AUTHORITY\SYSTEM:(OI)(CI)F" /T'
```

`apply-work-acl-fix.ps1` 已做 y/N 二次确认,默认假设跑在 `LocalSystem`。

### 5. 排错的标准姿势

```
Access to the path 'C:\actions-runner\_work\_PipelineMapping\scszcoder\eCan.ai\PipelineFolder.json' is denied
```

按从轻到重:

| 步骤 | 命令 | 期望 |
|---|---|---|
| 1. 服务在跑 | `Get-Service actions.runner.* \| ft Name, Status` | `Running` |
| 2. 账户是 SYSTEM | `Get-CimInstance Win32_Service -Filter "Name='actions.runner.scszcoder-eCan.ai.win-runner'" \| Select StartName` | `LocalSystem` |
| 3. _work 可写 | `.\diagnose-work-acl.ps1` | `✅ probe succeeded` |
| 4. 不行就 `apply-work-acl-fix.ps1` | 重建 ACL | `✅ write OK` |
| 5. 还不行 → 清缓存 | `& svc.cmd stop ; rm -r -fo _work\_actions, _work\_tool, _work\_PipelineMapping ; & svc.cmd start` | 下一个 job 重新创建 |

### 6. 账户变更的代价(必须知道)

把 service 账户从 A 换成 B,或者从 `LocalSystem` 换成 `DOMAIN\svc-actions`,
**新账户对旧 `_work\` 下所有已缓存目录都"陌生"**:

```
v1: _work\_actions\actions\setup-node\v4\...    ← owner = 当前登录管理员
v2: 改为 LocalSystem 跑
     → 旧 _actions\ 缓存读不到 → "Access denied"
```

**变更账户的标准动作**:

```powershell
& svc.cmd stop
Remove-Item -Recurse -Force _work\_actions
Remove-Item -Recurse -Force _work\_tool
Remove-Item -Recurse -Force _work\_PipelineMapping
# 换账户
sc.exe config "actions.runner.scszcoder-eCan.ai.win-runner" obj= "DOMAIN\svc-actions" password= "..."
& svc.cmd start
```

下个 job 会按新账户身份重新下载 action 副本、按新账户身份创建 `_PipelineMapping\`。

### 7. 升级 runner 版本的标准动作

runner 升级会让 `_diag\Runner_*.log` 落盘;**只要 service 账户不变**,不需要清 `_work\_actions`。
但稳妥流程:

```powershell
& svc.cmd stop
# 备份
Copy-Item _diag _diag.bak -Recurse -Force
# 升级：拿新 zip、解压覆盖
Invoke-WebRequest -OutFile actions-runner.zip https://github.com/actions/runner/releases/download/v<NEW>/actions-runner-win-x64-<NEW>.zip
Expand-Archive actions-runner.zip -DestinationPath C:\actions-runner -Force
& svc.cmd start
```

### 8. 验证矩阵(部署完成后跑一遍)

| 检查 | 命令 | 通过条件 |
|---|---|---|
| Service running | `Get-Service actions.runner.*` | `Running` |
| Account = LocalSystem | `Get-CimInstance Win32_Service -Filter "Name LIKE 'actions.runner.%'" \| Select StartName` | `LocalSystem` |
| _work writeable | `.\diagnose-work-acl.ps1` 末段 | `✅ probe succeeded` |
| Labels 一致 | `gh api repos/scszcoder/eCan.ai/actions/runners --jq '.runners[].labels[].name' \| sort -u` | 包含 `self-hosted,windows,x64,ecan-build` |
| 能接 job | GitHub UI 显示 runner 为 "Idle" | ✅ |
| 端到端冒烟 | 手动 `workflow_dispatch` 跑 `release-cn.yml` 只跑 `validate-tag` | ✅ |
