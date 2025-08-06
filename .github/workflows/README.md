# GitHub Actions Workflows

This project contains a main GitHub Actions workflow for automated build and release processes.

## Workflows Overview

### Release Build (`release.yml`)
**Unified Release Process** - Triggered when creating tags or releases

**Trigger Conditions:**
- Push tag: `v*` (e.g., `v1.0.0`, `v2.1.3`)
- Create/edit/publish GitHub Release
- Manual trigger (with platform selection support)

**Features:**
- ✅ Validate tag format
- ✅ Support selective builds (Windows, macOS, or all)
- ✅ Parallel build for Windows and macOS versions
- ✅ Automatic GitHub Release creation
- ✅ Upload build artifacts
- ✅ Unified multi-platform build management

## Usage

### Creating a New Version Release

1. **Prepare Code**
   ```bash
   git checkout main
   git pull origin main
   ```

2. **Create and Push Tag**
   ```bash
   # Create tag (following Semantic Versioning)
   git tag v1.0.0
   
   # Push tag to remote repository
   git push origin v1.0.0
   ```

3. **Automatic Build Trigger**
   - After pushing the tag, GitHub Actions will automatically trigger the build process
   - After build completion, it will automatically create a GitHub Release

### Tag Naming Convention

Following [Semantic Versioning (SemVer)](https://semver.org/) specification:

- **Stable Release**: `v1.0.0`, `v2.1.3`
- **Pre-release**: `v1.0.0-alpha.1`, `v2.0.0-beta.1`
- **Development**: `v1.0.0-dev.20240101`

### Manual Trigger

You can manually trigger builds through GitHub's web interface:

1. Go to project's **Actions** tab
2. Select **Release Build** workflow
3. Click **Run workflow**
4. Choose platform (Windows, macOS, or all)
5. Click **Run workflow** button

## Build Artifacts

### Windows
- `eCan-Setup.exe` - Installer
- `eCan/eCan.exe` - Portable executable

### macOS
- `eCan.pkg` - macOS installer package
- `eCan.app` - macOS application bundle (portable)

### Artifact Storage
- **GitHub Actions**: 30 days retention
- **GitHub Releases**: Permanent storage
- **Download**: Available from GitHub Releases page

## Version Management

### Version Information Passing
- Automatically extract version number from Git tags
- Version information automatically applied to build artifacts
- Support for Semantic Versioning (SemVer)
- Build artifact filenames include version numbers

### Version Application Scope
- **Windows Installer**: Application information in `eCan-Setup.exe`
- **macOS Installer**: `eCan-{version}.pkg` filename and package information
- **Application**: Application version information in executable files
- **Release Notes**: Automatically generate release notes with version information

## Build Process

### Windows Build
1. **Environment Setup**: Windows Server 2022
2. **Dependencies**: Install Python, Node.js, system tools
3. **Build**: Execute `python build.py prod --version {version}`
4. **Artifacts**: Generate installer and portable version
5. **Upload**: Upload to GitHub Actions artifacts

### macOS Build
1. **Environment Setup**: macOS 12 (Intel)
2. **Dependencies**: Install Python, Node.js, system tools
3. **Build**: Execute `python build.py prod --version {version}`
4. **Artifacts**: Generate `.pkg` installer and `.app` bundle
5. **Upload**: Upload to GitHub Actions artifacts

### Release Creation
1. **Dependency**: Requires successful completion of Windows and macOS builds
2. **Artifacts**: Download build artifacts from previous jobs
3. **Release**: Create GitHub Release with version tag
4. **Upload**: Upload all platform artifacts to Release
5. **Notes**: Generate release notes with download links

## Platform Selection

When manually triggering workflows, you can select specific platforms to build:

- **all**: Build both Windows and macOS (default)
- **windows**: Build Windows only
- **macos**: Build macOS only

This feature is useful for:
- 🔧 Debugging platform-specific issues
- ⚡ Faster iteration during development
- 💰 Reducing CI/CD resource usage
- 🎯 Platform-specific releases

## Troubleshooting

### Common Issues

1. **Tag format error**: Ensure tag follows `v*` format (e.g., `v1.0.0`)
2. **Build failure**: Check build logs in GitHub Actions
3. **Missing artifacts**: Verify build completed successfully
4. **Permission error**: Ensure repository has proper access permissions

### Debug Steps

1. Check GitHub Actions logs
2. Verify tag format and version number
3. Ensure all required dependencies are available
4. Check build script execution permissions
5. Verify artifact upload permissions

## Configuration

Build configuration is managed through:
- `build_system/build_config.json` - Application and installer configuration
- `build.py` - Main build script entry point
- `build_system/ecan_build.py` - Core build system implementation

For detailed configuration options, see the build system documentation.