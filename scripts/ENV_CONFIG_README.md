# ECBot Environment Variables Configuration Generator

This tool helps you generate environment variable configuration files (.env) for ECBot applications, supporting Windows and macOS/Linux platforms with automatic ECan installation path detection.

## 🚀 Quick Start

### Windows Users
Double-click to run the batch file:
```
scripts/generate_env_config.bat
```

### macOS/Linux Users
Run in terminal:
```bash
./scripts/generate_env_config.sh
```

## 🔍 Automatic Path Detection

The scripts automatically search for ECan installation paths, specially optimized for PyInstaller packaged applications:

### Windows
**PyInstaller Environment Detection**:
- `%_MEIPASS%` environment variable (set by PyInstaller)
- `%TEMP%\_MEI*` temporary directories
- Running ECan process paths

**Standard Installation Paths**:
- `%PROGRAMFILES%\eCan` (primary)
- `%PROGRAMFILES(X86)%\eCan`
- `%LOCALAPPDATA%\ECan` (legacy)
- `%APPDATA%\ECan` (legacy)
- Registry queries
- Current directory and parent directory

### macOS
**PyInstaller Environment Detection**:
- `/tmp/_MEI*` temporary directories
- Running ECan process paths

**Standard Installation Paths**:
- `/Applications/eCan.app/Contents/Resources` (primary)
- `/Applications/ECan.app/Contents/Resources` (legacy)
- `~/Applications/eCan.app/Contents/Resources`
- `~/Applications/ECan.app/Contents/Resources`
- `/usr/local/bin/eCan`
- `/usr/local/bin/ECan`

### Linux
**PyInstaller Environment Detection**:
- `/tmp/_MEI*` temporary directories
- `/var/tmp/_MEI*` temporary directories
- Running ECan process paths

**Standard Installation Paths**:
- `/usr/local/bin/eCan` (primary)
- `/usr/bin/eCan`
- `~/.local/bin/eCan`
- `/opt/eCan`
- `/usr/local/bin/ECan` (legacy)
- `/usr/bin/ECan` (legacy)
- `~/.local/bin/ECan` (legacy)
- `/opt/ECan` (legacy)

## 📋 Configuration Options

### API Key Configuration
- `OPENAI_API_KEY`: OpenAI API key (optional, hidden input)
- `DASHSCOPE_API_KEY`: Alibaba Cloud Tongyi Qianwen API key (optional, hidden input)
- `CLAUDE_API_KEY`: Anthropic Claude API key (optional, hidden input)
- `GEMINI_API_KEY`: Google Gemini API key (optional, hidden input)

### Basic Configuration
- `LOG_LEVEL`: Log level (DEBUG/INFO/WARNING/ERROR, default: INFO)
- `DEBUG_MODE`: Debug mode (true/false, default: false)

## 📁 File Locations

The generated .env file will be saved to ECan's bundle directory, which perfectly matches the path detection logic in the code:

### PyInstaller Packaged Applications
**Windows**:
- `%TEMP%\_MEI*\.env` (temporary bundle directory)
- Example: `C:\Users\User\AppData\Local\Temp\_MEI123456\.env`

**macOS/Linux**:
- `/tmp/_MEI*/.env` (temporary bundle directory)
- Example: `/tmp/_MEI123456/.env`

⚠️ **Important**: PyInstaller temporary directories are deleted after application closes!

### Standard Installation Applications
**Windows**:
- .env file in installation directory
- Example: `C:\Program Files\eCan\.env`

**macOS**:
- Resources directory within application bundle
- Example: `/Applications/eCan.app/Contents/Resources/.env`

**Linux**:
- Directory containing executable file
- Example: `/usr/local/bin/.env`

## 🔧 Usage

### 1. Interactive Configuration
After running the script, follow the prompts to enter configuration values:

```
🔧 ECBot Environment Config Generator (Windows)
============================================================
Target directory: C:\Users\YourName\ECBot

📋 Please enter API key configuration:
========================================

🔑 API Key Configuration:
----------------------------------------
OpenAI API Key (input will be hidden, optional):
DashScope API Key (input will be hidden, optional):
Claude API Key (input will be hidden, optional):
Gemini API Key (input will be hidden, optional):

⚙️ Basic Configuration:
----------------------------------------
Debug mode (true/false) [false]:
Log level (DEBUG/INFO/WARNING/ERROR) [INFO]:
```

### 2. Using Template File
You can also copy the `env_template.env` file and modify it manually:

```bash
# Copy template
cp scripts/env_template.env .env

# Edit configuration
nano .env  # Linux/macOS
notepad .env  # Windows
```

## 🛡️ Security Features

### Password and Key Input
- All password inputs are hidden from display
- Generated .env file contains sensitive information, please keep it secure
- Do not commit .env file to version control systems

### File Permissions
- Scripts automatically set appropriate file permissions
- Ensure only necessary users can access .env file

## 📄 Generated Files

After running the script, the following files will be generated:

1. **`.env`**: Main configuration file

### .env File Example
```bash
# ECBot Environment Variables Configuration File
# Generated: 2024-01-01 12:00:00
# Platform: Windows
# ECan Path: C:\Program Files\eCan
# Runtime Mode: Standard Installation

# API Key Configuration
# OpenAI API Key
OPENAI_API_KEY=sk-1234567890abcdef...

# DashScope API Key
DASHSCOPE_API_KEY=sk-abcdef1234567890...

# Claude API Key
CLAUDE_API_KEY=sk-ant-api03-xyz...

# Gemini API Key
GEMINI_API_KEY=AIzaSyABC123...

# Basic Configuration
# Log Level
LOG_LEVEL=INFO
# Debug Mode
DEBUG_MODE=false
```

## 🔄 Updating Configuration

### Regenerating Configuration
If you need to modify configuration, simply run the script again:
- Script will detect existing configuration file
- Ask if you want to update existing configuration
- Keep existing values as defaults

### Manual Editing
You can also directly edit the .env file:
```bash
# Find configuration file location
find . -name ".env" -type f

# Edit file
nano path/to/.env
```

## 🐛 Troubleshooting

### Common Issues

#### Path Not Found
If the script cannot automatically find ECan installation path:
1. Ensure ECan is properly installed
2. Manually enter the correct installation path
3. Check file permissions

#### Permission Errors
**Windows**:
- Run Command Prompt as administrator
- Right-click .bat file and select "Run as administrator"

**macOS/Linux**:
```bash
# Set script execution permissions
chmod +x scripts/generate_env_config.sh

# If needed, run with sudo
sudo ./scripts/generate_env_config.sh
```

#### Configuration File Not Taking Effect
1. Confirm .env file location is correct
2. Restart ECan application
3. Check application logs for configuration loading information

### Debug Mode
If you encounter issues, you can enable debug mode:
```bash
# Set environment variable
export DEBUG=1

# Run script
./scripts/generate_env_config.sh
```

## 📄 生成的文件示例

```bash
# ECBot环境变量配置文件
# 生成时间: 2024-01-01 12:00:00
# 平台: Windows
# ECan路径: C:\Program Files\ECan
# 运行模式: 标准安装

# API密钥配置
# OpenAI API密钥
OPENAI_API_KEY=sk-1234567890abcdef...

# DashScope API密钥
DASHSCOPE_API_KEY=sk-abcdef1234567890...

# Claude API密钥
CLAUDE_API_KEY=sk-ant-api03-xyz...

# Gemini API密钥
GEMINI_API_KEY=AIzaSyABC123...

# 基础配置
# 日志级别
LOG_LEVEL=INFO
# 调试模式
DEBUG_MODE=false
```

## 📞 Getting Help

If you encounter issues, please:
1. Check the troubleshooting section above
2. Confirm ECan installation path is correct
3. Check file permissions and disk space
4. Contact technical support

---

**🎯 Now you can easily configure API keys for ECan!**
