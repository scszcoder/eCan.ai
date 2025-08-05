# PyInstaller hook for browser_use package
# This hook ensures that browser_use's resource files (like system_prompt.md) are included in the build

from PyInstaller.utils.hooks import collect_data_files, collect_submodules
import os

# Collect all data files from browser_use package
datas = collect_data_files('browser_use')

# Specifically ensure prompt files are included
try:
    import browser_use
    browser_use_path = os.path.dirname(browser_use.__file__)
    
    # Add specific prompt files
    prompt_files = [
        'agent/system_prompt.md',
        'agent/system_prompt_flash.md', 
        'agent/system_prompt_no_thinking.md'
    ]
    
    for prompt_file in prompt_files:
        full_path = os.path.join(browser_use_path, prompt_file)
        if os.path.exists(full_path):
            datas.append((full_path, f'browser_use/{os.path.dirname(prompt_file)}'))
            print(f"[HOOK] Adding browser_use resource: {prompt_file}")

except ImportError:
    print("[HOOK] Warning: browser_use not found, skipping resource collection")

# Collect all submodules
hiddenimports = collect_submodules('browser_use')

# Add specific hidden imports that might be missed
additional_imports = [
    'browser_use.agent.prompts',
    'browser_use.agent.service', 
    'browser_use.agent.views',
    'browser_use.browser.types',
    'browser_use.dom.views',
    'browser_use.utils',
    'browser_use.controller',
    'browser_use.telemetry'
]

hiddenimports.extend(additional_imports)

print(f"[HOOK] browser_use: Found {len(datas)} data files and {len(hiddenimports)} hidden imports")
