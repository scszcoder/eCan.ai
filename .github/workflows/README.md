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

## Runner Groups

The `Release Build eCan` workflow exposes a `runner_group` input on
`workflow_dispatch` so a build can be redirected to a self-hosted runner. The
options are static (GitHub does not allow dynamic choice lists); each entry
maps to one or more `runs-on` labels.

| Option                | Default runner (GitHub-hosted)     | Self-hosted label                            | Used by build jobs                |
|-----------------------|------------------------------------|----------------------------------------------|-----------------------------------|
| `github-hosted`       | `ubuntu-22.04` / `windows-latest` / `macos-14` / `macos-latest` | -                                            | all `build-*` jobs                |
| `ecan-linux-amd64`    | -                                  | `self-hosted,linux,x64,ecan-build`           | `build-linux`, `build-linux-cn`   |
| `ecan-windows-amd64`  | -                                  | `self-hosted,windows,x64,ecan-build`         | `build-windows`, `build-windows-cn` |
| `ecan-macos-amd64`    | -                                  | `self-hosted,macos,x64,ecan-build`           | `build-macos`, `build-macos-cn` (amd64 row only) |
| `ecan-macos-arm64`    | -                                  | `self-hosted,macos,arm64,ecan-build`         | `build-macos`, `build-macos-cn` (aarch64 row only) |

### How the runner is selected

Each build job declares a small `matrix.include` that maps a runner group to a
real `runs-on` value. The job's `if:` clause filters out all rows except the
one matching `github.event.inputs.runner_group`, so only one matrix row
actually schedules a runner. Downstream jobs (`upload-to-s3`, `upload-to-cos`,
`generate-appcast-*`, `generate-download-links`, `final-status`) keep running
on `ubuntu-latest`; they only consume artifacts.

```yaml
strategy:
  matrix:
    include:
      - runner_group: github-hosted
        runner: ubuntu-22.04
      - runner_group: ecan-linux-amd64
        runner: [self-hosted, linux, x64, ecan-build]
if: |
  ... &&
  matrix.runner_group == github.event.inputs.runner_group
runs-on: ${{ matrix.runner }}
```

### Naming convention for self-hosted runners

Labels are a comma-separated list. GitHub requires the literal `self-hosted`
token. eCan.ai uses:

```
self-hosted, <os>, <arch>, ecan-build
```

`<os>` ∈ {`linux`, `macos`, `windows`}; `<arch>` ∈ {`x64`, `arm64`}. macOS
**must** distinguish `x64` and `arm64` — PyInstaller emits native binaries,
and the matrix filters on architecture independently of `runner_group`.

### Adding a new self-hosted runner

1. On the target machine, download and configure
   [`actions-runner`](https://github.com/actions/runner) (`./config.sh` or
   `.\config.cmd`).
2. Register with labels that **exactly** match one of the existing rows in
   the matrix — e.g. `--labels self-hosted,linux,x64,ecan-build`.
3. Confirm `Settings → Actions → Runners` shows the runner as `online`.
4. If you need a new runner-group option, update all of the following in the
   same PR so they stay in sync:
   - `release.yml` → `workflow_dispatch.inputs.runner_group.options`
   - Every `build-*` job → `matrix.include[*].runner_group` and
     `matrix.include[*].runner`
   - This README's option table

### Safety rules

- **Do not** add `pull_request` triggers while self-hosted runners are
  selectable. Forks can run arbitrary code on a self-hosted runner with repo
  secrets access. The current `release.yml` only fires from
  `workflow_dispatch` and `push` of `v*` tags, so this is safe today; any
  change that broadens the trigger set must also gate self-hosted rows.
- Do **not** bake signing certificates (`MAC_CERT_P12`, `WIN_CERT_PFX`,
  `AZURE_*`) into the runner image. Inject them via `secrets.*` and clear
  any on-disk copies immediately after use (the workflow already does this
  for the PFX fallback).
- Run the `actions-runner` service as a low-privilege account, not
  `root` / `Administrator`.
- The build cache key includes `${{ runner.os }}` and `${{ env.BUILD_ARCH }}`,
  so switching between GitHub-hosted and self-hosted runners does not corrupt
  caches.