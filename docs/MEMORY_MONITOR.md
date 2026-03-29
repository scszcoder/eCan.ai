# Memory Monitor

Background memory tracker with automatic leak detection. Logs process RSS, runs `tracemalloc` snapshot diffs to pinpoint which file/line is allocating the most, and optionally uses `objgraph` to trace reference chains.

## How It Works

The monitor starts automatically with the app (`main.py`) and runs a daemon thread that:

1. **Every 60 seconds** -- logs RSS, VMS, traced memory, and thread count to `memory.log`
2. **Every 5 minutes** -- takes a `tracemalloc` snapshot and diffs it against the previous one, showing the top 15 allocations sorted by growth
3. **On threshold breach** -- pushes a warning to the main `eCan.log` when:
   - RSS exceeds 1500 MB
   - RSS is growing faster than 50 MB/min

## Log Files

| File | Content |
|------|---------|
| `runlogs/memory.log` | All memory data -- RSS timeline, snapshot diffs, object dumps |
| `runlogs/eCan.log` | Only warnings when thresholds are exceeded |

`memory.log` is a rotating file (20 MB max, 3 backups).

## Reading the Logs

### RSS Timeline

```
2026-03-29 15:40:01 | INFO    | RSS=482.3MB  VMS=1205.7MB  traced=180.2MB  peak=195.1MB  threads=24
2026-03-29 15:41:01 | INFO    | RSS=490.1MB  VMS=1210.3MB  traced=185.7MB  peak=195.1MB  threads=25
```

- **RSS** (Resident Set Size) -- actual physical memory used by the process
- **VMS** (Virtual Memory Size) -- total virtual address space
- **traced** -- memory tracked by `tracemalloc` (Python allocations only, not C extensions)
- **peak** -- highest traced value since startup
- **threads** -- OS thread count

If RSS grows steadily over time without leveling off, you likely have a leak.

### Snapshot Diffs

```
--- tracemalloc diff (vs previous) -- top 15 growing allocations ---
  #1  agent/ec_skills/build_node.py:142  size=5200.3KB  delta=+3100.2KB  count=850  delta_count=+420
  #2  agent/mcp/client.py:88            size=2100.1KB  delta=+1200.0KB  count=300  delta_count=+150
  #3  langchain_core/messages.py:45     size=1800.5KB  delta=+800.3KB   count=5200 delta_count=+2100
  TOTAL: 42.3MB  delta=+8.1MB  (1247 entries)
```

- **file:line** -- exact source location of the allocation
- **size** -- current total allocated at that location
- **delta** -- change since the last snapshot (5 min ago)
- **count / delta_count** -- number of live allocations and change

**How to interpret:** Sort by `delta` -- the top entries are where memory is growing the fastest. A large positive delta that repeats across multiple snapshots = probable leak at that location.

### Threshold Warnings (in eCan.log)

```
[MemoryMonitor] WARNING: RSS=1520.3MB exceeds threshold 1500MB
[MemoryMonitor] WARNING: RSS growing at 62.1MB/min (400.2MB -> 1520.3MB over 18.0min)
[MemoryMonitor] Significant memory growth: +12.4MB (vs previous). Check memory.log for details.
```

## On-Demand Diagnostics

### From Python (debug console / script)

```python
from utils.memory_monitor import get_memory_monitor

monitor = get_memory_monitor()

# Current stats
print(monitor.get_summary())
# {'rss_mb': 482.3, 'vms_mb': 1205.7, 'traced_mb': 180.2, ...}

# Snapshot diff vs previous (last 5 min)
print(monitor.snapshot_diff())

# Snapshot diff vs startup baseline (cumulative growth)
print(monitor.snapshot_diff(vs_baseline=True))

# Group by file instead of line (broader view)
print(monitor.snapshot_diff_by_file())

# Top growing object types (needs: pip install objgraph)
print(monitor.dump_top_objects())

# What's keeping EC_Agent objects alive?
print(monitor.dump_backrefs('EC_Agent'))
```

### From the Frontend (IPC)

Three IPC endpoints are available:

```typescript
// Current memory stats
const stats = await ipcApi.call('get_memory_stats');
// { rss_mb, vms_mb, traced_mb, traced_peak_mb, growth_rate_mb_per_min, threads }

// Snapshot diff
const diff = await ipcApi.call('memory_snapshot_diff', {
  vs_baseline: true,  // compare against startup (default: false = vs previous)
  by_file: false,     // group by filename (default: false = by line)
});
// { diff: "--- tracemalloc diff ..." }

// Object type growth (requires objgraph)
const dump = await ipcApi.call('memory_dump_objects', { top_n: 20 });
// { dump: "--- Object growth ..." }
```

## Configuration

Pass keyword arguments to `start_memory_monitor()` or `get_memory_monitor()`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `interval` | `60` | Seconds between RSS checks |
| `snapshot_interval` | `300` | Seconds between tracemalloc snapshot diffs |
| `rss_warn_mb` | `1500` | Warn when RSS exceeds this (MB) |
| `growth_warn_mb_per_min` | `50` | Warn when growth rate exceeds this |
| `top_n` | `15` | Number of top allocations in snapshot diffs |

Example -- more aggressive monitoring during debugging:

```python
from utils.memory_monitor import start_memory_monitor

start_memory_monitor(
    interval=15,              # check every 15s
    snapshot_interval=60,     # diff every 1 min
    rss_warn_mb=800,          # lower threshold
    growth_warn_mb_per_min=20,
)
```

## Investigating a Leak

### Step 1: Identify the trend

Open `memory.log` and look at the RSS timeline. Steady growth = leak. Plot it if needed:

```python
# Quick parse from memory.log
import re
with open('runlogs/memory.log') as f:
    rss_values = [float(m.group(1)) for line in f if (m := re.search(r'RSS=(\d+\.\d+)MB', line))]
print(f"Start: {rss_values[0]}MB  End: {rss_values[-1]}MB  Growth: {rss_values[-1]-rss_values[0]:.1f}MB")
```

### Step 2: Find the source

Look at the snapshot diffs in `memory.log`. The entries with the largest `delta` that repeat across multiple diffs are your suspects.

Or trigger a baseline diff on-demand:

```python
# Shows cumulative growth since app startup
print(get_memory_monitor().snapshot_diff(vs_baseline=True))
```

### Step 3: Trace references (optional)

If you know a specific object type is leaking (e.g., `EC_Agent` objects not being GC'd):

```bash
pip install objgraph
```

```python
monitor = get_memory_monitor()

# What types are growing?
monitor.dump_top_objects()

# What's keeping EC_Agent alive?
monitor.dump_backrefs('EC_Agent')
```

`dump_backrefs` shows the reference chain from a sample object back to its roots -- this tells you exactly what's holding onto it and preventing garbage collection.

### Common Leak Patterns in This Codebase

| Pattern | Where to look | Fix |
|---------|---------------|-----|
| Agent not removed from `self.agents` | `MainGUI.py`, `agent_handler.py` | Ensure stop/disable removes from list |
| Task futures not cleaned up | `ec_agent.active_tasks` | Cancel and clear on stop |
| LangGraph state accumulating messages | `EC_Skill` state | Trim message history |
| MCP client sessions not closed | `agent/mcp/client.py` | Ensure `async with` or explicit close |
| Callback / signal references | Qt signal connections | Use `weakref` or disconnect on cleanup |
| Browser pages not closed | Playwright / browser-use | Close page/context after task |

## Dependencies

| Library | Required | Source |
|---------|----------|--------|
| `psutil` | Yes | Already installed (`requirements-base.txt`) |
| `tracemalloc` | Yes | Python stdlib |
| `objgraph` | Optional | `pip install objgraph` -- enables `dump_top_objects()` and `dump_backrefs()` |

## Files

| File | Purpose |
|------|---------|
| `utils/memory_monitor.py` | Core monitor module |
| `gui/ipc/w2p_handlers/memory_handler.py` | IPC endpoints for frontend access |
| `main.py` (line ~807) | Startup integration |
| `runlogs/memory.log` | Output log file |
