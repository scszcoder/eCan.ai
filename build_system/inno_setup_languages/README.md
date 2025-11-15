# Inno Setup Language Packs

This directory contains language files for Inno Setup installer.

## Current Languages

- **ChineseSimplified.islu** - Simplified Chinese (简体中文)
  - Format: Unicode (.islu) with LanguageCodePage=0
  - Source: [Inno Setup Official Unofficial Languages](https://github.com/jrsoftware/issrc/tree/main/Files/Languages/Unofficial)
  - Maintained by: Zhenghan Yang
  - Version: Compatible with Inno Setup 6.0+ (Unicode version)
  - Last Updated: 2024-11-15

> **Note**: This project uses `.islu` (Unicode) format exclusively for all language packs.
> This is the modern standard recommended by Inno Setup for Unicode support.

## Adding New Languages

### Method 1: Using the Download Script (Easiest) ✨

Use the provided download script to automatically fetch official language packs:

```bash
# Download specific languages
python ../download_inno_languages.py ChineseSimplified Japanese Korean

# Download all unofficial (community-maintained) languages
python ../download_inno_languages.py --all-unofficial

# List available languages
python ../download_inno_languages.py --list

# Update existing languages to latest versions
python ../download_inno_languages.py --update-existing

# Show currently installed languages
python ../download_inno_languages.py --installed
```

The script will:
- ✅ Download from official Inno Setup repository
- ✅ **Automatically convert to `.islu` format** (LanguageCodePage=0)
- ✅ Verify file integrity
- ✅ Display language information (name, ID, codepage)
- ✅ Save to the correct directory automatically

### Method 2: Manual Download

1. Browse official languages:
   - Official: https://github.com/jrsoftware/issrc/tree/main/Files/Languages
   - Unofficial: https://github.com/jrsoftware/issrc/tree/main/Files/Languages/Unofficial

2. Download the `.isl` file for your language

3. **Convert to `.islu` format:**
   - Rename file extension from `.isl` to `.islu`
   - Change `LanguageCodePage=<number>` to `LanguageCodePage=0`
   - Ensure file is saved as UTF-8 encoding

4. Place it in this directory: `build_system/inno_setup_languages/`

5. The build system will automatically detect and install it during CI/CD

### Method 3: Custom Translation

1. Copy `ChineseSimplified.islu` as a template
2. Translate all message strings
3. Update `LanguageName` and `LanguageID` in `[LangOptions]` section
4. Keep `LanguageCodePage=0` (for Unicode support)
5. Save as UTF-8 encoding with `.islu` extension
6. Test locally before committing

## Language Pack Structure (.islu format)

```ini
[LangOptions]
LanguageName=简体中文           # Display name
LanguageID=$0804               # Windows LCID
LanguageCodePage=0             # 0 = Unicode (required for .islu)

[Messages]
SetupAppTitle=安装              # Translated messages
...
```

**Key Points:**
- File extension: `.islu` (not `.isl`)
- Encoding: UTF-8 (without BOM recommended)
- LanguageCodePage: Must be `0` for Unicode support

## Updating Existing Languages

1. Check for updates in the official repository
2. Download the latest version
3. Review changes (use `git diff`)
4. Test the build locally
5. Commit with clear message: `chore: update ChineseSimplified.islu to v6.x.x`

## CI/CD Integration

The GitHub Actions workflow automatically:
1. Detects all `.islu` files in this directory
2. Installs them to Inno Setup's Languages directory
3. Includes them in the installer script

**No workflow changes needed when adding new languages!**

> The workflow only processes `.islu` files (Unicode format).
> Legacy `.isl` files are not supported.

## Best Practices

✅ **DO:**
- Version control all language files
- Document the source and version
- Test before committing
- Use official translations when available
- Keep terminology consistent with product UI

❌ **DON'T:**
- Use `.isl` files (legacy ANSI format, not supported)
- Mix different Inno Setup versions
- Modify without testing
- Use machine translation without review
- Save files with non-UTF-8 encoding

## Troubleshooting

### Warning: "Message name X is not recognized"
- Cause: Language file is newer than Inno Setup version
- Solution: Either upgrade Inno Setup or remove the unrecognized messages

### Warning: "Could not verify required markers"
- Cause: Incorrect `LanguageID` or `LanguageCodePage`
- Solution: Check official documentation for correct values

### Characters display as ???
- Cause: Encoding mismatch
- Solution: Ensure file is saved with correct encoding (UTF-8 with BOM or ANSI with correct codepage)

## References

- [Inno Setup Documentation](https://jrsoftware.org/ishelp/)
- [Language Files Guide](https://jrsoftware.org/ishelp/index.php?topic=langoptionssection)
- [Official Language Repository](https://github.com/jrsoftware/issrc/tree/main/Files/Languages)
- [LCID Reference](https://docs.microsoft.com/en-us/openspecs/windows_protocols/ms-lcid/)
