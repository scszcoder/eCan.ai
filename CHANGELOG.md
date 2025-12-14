# Changelog

All notable changes to eCan.ai will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.0.5] - 2025-11-21

### Added
- S3 accelerated download URL support - Provides both standard and accelerated download URLs for each update package
- OTA auto-check delay configuration - 5 seconds for development environment, 2 minutes for other environments
- Development environment independent OTA switch - `dev_ota_check_enabled` configuration option
- pip dependency caching - GitHub Actions uses `requirements.txt` and caching to speed up builds
- Multi-language appcast support - Automatically generates English and Chinese versions of update notes
- Appcast fallback mechanism - Automatically falls back to English if localized version is not available

### Fixed
- Fixed restart script command parsing issue - Unix shell scripts now correctly handle commands with arguments
- Fixed Windows build process missing `.sig` signature files
- Fixed simulated builds missing signature files

### Changed
- Optimized GitHub Actions checkout - Build jobs use shallow clone (fetch-depth: 1) saving ~28% time
- Unified Python dependency management - Using `build_system/scripts/requirements.txt`
- Improved logging output - OTA delay check now displays environment information

### Performance
- Build time optimization: Saves ~21 seconds per build (~28% improvement)
- Dependency installation optimization: Saves ~80% time when pip cache hits

## [0.0.4] - 2025-11-20

### Added
- Initial release
- OTA automatic update functionality
  - Support for macOS and Windows platforms
  - Ed25519 signature verification
  - Automatic download and installation
  - Background silent updates
- Sparkle-compatible Appcast format
- S3 storage and distribution
- Multi-environment support (development, test, staging, production)
- GitHub Actions automated build and release workflow

### Security
- Ed25519 digital signature verification
- Secure update download and installation process

---

## Version Notes

### Version Number Format
- Major.Minor.Patch (e.g., 1.0.0)
- Follows Semantic Versioning

### Update Types
- **Added**: New features
- **Changed**: Changes in existing functionality
- **Deprecated**: Soon-to-be removed features
- **Removed**: Removed features
- **Fixed**: Bug fixes
- **Security**: Security updates
- **Performance**: Performance improvements

[Unreleased]: https://github.com/scszcoder/eCan.ai/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/scszcoder/eCan.ai/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/scszcoder/eCan.ai/releases/tag/v1.0.0
