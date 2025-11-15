# Inno Setup Language Packs

This directory contains language files for Inno Setup installer.

## Current Languages

- **ChineseSimplified.isl** - Simplified Chinese (简体中文)
  - Source: [Inno Setup Official Unofficial Languages](https://github.com/jrsoftware/issrc/tree/main/Files/Languages/Unofficial)
  - Maintained by: Zhenghan Yang
  - Version: Compatible with Inno Setup 6.5.0+
  - Last Updated: 2024-11-15

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
- ✅ Verify file integrity
- ✅ Display language information (name, ID, codepage)
- ✅ Save to the correct directory automatically

### Method 2: Manual Download

1. Browse official languages:
   - Official: https://github.com/jrsoftware/issrc/tree/main/Files/Languages
   - Unofficial: https://github.com/jrsoftware/issrc/tree/main/Files/Languages/Unofficial

2. Download the `.isl` file for your language

3. Place it in this directory: `build_system/inno_setup_languages/`

4. The build system will automatically detect and install it during CI/CD

### Method 3: Custom Translation

1. Copy `ChineseSimplified.isl` as a template
2. Translate all message strings
3. Update `LanguageName`, `LanguageID`, and `LanguageCodePage` in `[LangOptions]` section
4. Test locally before committing

## Language Pack Structure

```ini
[LangOptions]
LanguageName=简体中文           # Display name
LanguageID=$0804               # Windows LCID
LanguageCodePage=936           # Windows code page

[Messages]
SetupAppTitle=安装              # Translated messages
...
```

## Updating Existing Languages

1. Check for updates in the official repository
2. Download the latest version
3. Review changes (use `git diff`)
4. Test the build locally
5. Commit with clear message: `chore: update ChineseSimplified.isl to v6.x.x`

## CI/CD Integration

The GitHub Actions workflow automatically:
1. Detects all `.isl` files in this directory
2. Installs them to Inno Setup's Languages directory
3. Includes them in the installer script

No workflow changes needed when adding new languages!

## Best Practices

✅ **DO:**
- Version control all language files
- Document the source and version
- Test before committing
- Use official translations when available
- Keep terminology consistent with product UI

❌ **DON'T:**
- Download during CI/CD (unreliable)
- Mix different Inno Setup versions
- Modify without testing
- Use machine translation without review

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
