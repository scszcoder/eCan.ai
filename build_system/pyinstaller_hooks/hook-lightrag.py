from PyInstaller.utils.hooks import collect_submodules, collect_all

# 1. Force collection of all submodules within lightrag
# This resolves errors like "No module named 'lightrag.kg.faiss_impl'"
# because PyInstaller cannot automatically detect LightRAG's dynamically loaded backend implementations
hiddenimports = collect_submodules('lightrag')

# 2. Collect all data files (configurations, templates, etc.) from lightrag
datas, binaries, _ = collect_all('lightrag')

print(f"[LightRAG Hook] Collected {len(hiddenimports)} submodules and {len(datas)} data files.")
