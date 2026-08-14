# Build System Scripts

## 📋 概述

这个目录包含构建和发布相关的脚本，用于 CI/CD 流程和依赖检查。

---

## 📂 子目录

### `runner/`
注册 GitHub Actions self-hosted runner 的脚本，覆盖 Linux / macOS / Windows。
详见 [`runner/README.md`](./runner/README.md)。

- `register_runner.sh` — Linux + macOS（自动检测 OS）
- `register_runner.ps1` — Windows

---

## 📄 脚本说明

### upload_to_s3.py

上传构建产物到 AWS S3。

**用途**: 将编译好的安装包上传到 S3 的不同环境路径

**使用方法**:
```bash
python3 build_system/scripts/upload_to_s3.py \
  --version 1.0.0 \
  --env production
```

**参数**:
- `--version`: 版本号 (必需)
- `--env`: 目标环境 (必需): development, test, staging, production
- `--platform`: 平台过滤 (可选): macos, windows
- `--arch`: 架构过滤 (可选): amd64, aarch64

**功能**:
- 上传 Windows/macOS 安装包到 S3
- 计算并上传 SHA256 校验和
- 生成版本元数据
- 更新 latest 指针

---

### generate_appcast.py

生成 Sparkle/WinSparkle Appcast XML 文件。

**用途**: 从 S3 扫描版本并生成 OTA 更新的 Appcast 文件

**使用方法**:
```bash
python3 build_system/scripts/generate_appcast.py \
  --env production \
  --channel stable
```

**参数**:
- `--env`: 目标环境 (必需): development, test, staging, production
- `--channel`: 发布渠道 (可选): stable, beta

**功能**:
- 扫描 S3 中的所有版本
- 为每个平台/架构生成独立的 Appcast XML
- 生成 latest.json 文件
- 上传到 S3 的 channels 目录

---

## 🔄 CI/CD 集成

这些脚本被以下 GitHub Actions workflows 使用：

### shared-s3-upload.yml
```yaml
- name: Upload to S3
  run: |
    python3 build_system/scripts/upload_to_s3.py \
      --version "$VERSION" \
      --env "$ENVIRONMENT"
```

### shared-appcast-generation.yml
```yaml
- name: Generate Appcast
  run: |
    python3 build_system/scripts/generate_appcast.py \
      --env "$ENVIRONMENT" \
      --channel "$CHANNEL"
```

---

## 📂 S3 路径结构

脚本会将文件上传到以下路径：

```
s3://ecan-releases/
├── {environment}/
│   ├── releases/v{version}/{platform}/{arch}/
│   │   ├── eCan-{version}-{platform}-{arch}.{ext}
│   │   └── eCan-{version}-{platform}-{arch}.{ext}.sha256
│   └── channels/{channel}/
│       ├── appcast-{platform}-{arch}.xml
│       └── latest.json
```

---

## 🔑 环境变量

脚本需要以下 AWS 凭证：

```bash
export AWS_ACCESS_KEY_ID=xxx
export AWS_SECRET_ACCESS_KEY=xxx
export AWS_REGION=us-east-1  # 可选，默认 us-east-1
```

---

## 📝 依赖

```bash
pip install boto3 pyyaml
```

---

## 🧪 本地测试

### 测试上传

```bash
# 上传到开发环境
python3 build_system/scripts/upload_to_s3.py \
  --version 1.0.0-dev-test \
  --env development

# 只上传 macOS aarch64
python3 build_system/scripts/upload_to_s3.py \
  --version 1.0.0 \
  --env production \
  --platform macos \
  --arch aarch64
```

### 测试 Appcast 生成

```bash
# 生成生产环境 Appcast
python3 build_system/scripts/generate_appcast.py \
  --env production \
  --channel stable

# 生成测试环境 Appcast
python3 build_system/scripts/generate_appcast.py \
  --env test \
  --channel beta
```

---

## ⚠️ 注意事项

1. **权限**: 确保 AWS 凭证有 S3 读写权限
2. **路径**: 脚本从项目根目录的 `dist/` 读取构建产物
3. **配置**: 使用 `ota/config/ota_config.yaml` 中的配置
4. **环境**: 脚本会自动从配置文件读取环境相关设置

---

## 🔗 相关文档

- [OTA 部署指南](../../docs/OTA_DEPLOYMENT_GUIDE.md)
- [CI/CD 实现指南](../../docs/CI_CD_IMPLEMENTATION_GUIDE.md)
- [S3 架构设计](../../docs/S3_SINGLE_BUCKET_DESIGN.md)
