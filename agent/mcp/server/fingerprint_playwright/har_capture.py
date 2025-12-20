import asyncio

har_path = f"sessions/{profile_id}.har"

context = await browser.new_context(record_har_path=har_path)

# Optionally stop and save early
await context.close()  # will flush HAR file
