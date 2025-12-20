# save_profile_state.py

async def save_state(context, profile_dir: Path):
    state_path = profile_dir / "state.json"
    state = await context.storage_state()
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
