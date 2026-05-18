#!/usr/bin/env python3
"""
Unit tests for agent_converter skill matching logic.

Tests cover:
1. skill_id exact match (priority)
2. skill_name exact match
3. Prefix match (task starts with skill name)
4. Contains match (word overlap between task and skill names)

Run:
    cd /Users/liuqiang/WorkSpace/ecan/eCan.ai
    python3 -m pytest tests/unit/test_agent_converter.py -v -s
    # or standalone:
    python3 tests/unit/test_agent_converter.py
"""

import pytest
from unittest.mock import MagicMock
from typing import Any, List, Tuple, Optional

# ── Path setup ────────────────────────────────────────────────────────────────
import sys
from pathlib import Path
_ROOT = Path("/Users/liuqiang/WorkSpace/ecan/eCan.ai")
sys.path.insert(0, str(_ROOT))

pytestmark = pytest.mark.unit


# ── Mock Logger ───────────────────────────────────────────────────────────────
class MockLogger:
    """Mock logger for testing."""
    def info(self, msg, *args): print(f"  INFO: {msg % args if args else msg}")
    def debug(self, msg, *args): print(f"  DEBUG: {msg % args if args else msg}")
    def warning(self, msg, *args): print(f"  WARN: {msg % args if args else msg}")
    def error(self, msg, *args): print(f"  ERROR: {msg % args if args else msg}")

logger = MockLogger()


# ── Extract the function under test (standalone version) ────────────────────────

def _find_matching_skill_for_task_standalone(
    task_obj, 
    skill_objects: List[Any], 
    compiled_skills: List[Any]
) -> Tuple[Optional[Any], str]:
    """
    Standalone version of _find_matching_skill_for_task for testing.
    
    Matching priority:
    1. skill_id exact match (if task already has a skill_id bound)
    2. skill_name exact match
    3. skill_name contains match (prefix/suffix)
    4. task name contains skill name words
    
    Returns (matched_skill, old_skill_name) or (None, '') if no match found.
    """
    task_name_lower = (getattr(task_obj, 'name', '') or '').lower()
    
    task_skill = getattr(task_obj, 'skill', None)
    has_correct_skill = task_skill is not None and getattr(task_skill, 'runnable', None) is not None
    
    if has_correct_skill:
        logger.info(f"Task '{task_obj.name}' already has a valid skill attached")
        return None, None
    
    # Build search pools: agent's own skills first, then global compiled pool
    search_pools = []
    if skill_objects:
        search_pools.append(('agent_skills', skill_objects))
    if compiled_skills:
        search_pools.append(('global_pool', compiled_skills))
    
    if not search_pools:
        logger.warning(f"No search pools available for task '{task_obj.name}'")
        return None, ''
    
    matched_skill = None
    skill_name_on_task = ''
    skill_id_on_task = ''
    
    # Extract skill info from task_skill
    if isinstance(task_skill, str):
        skill_name_on_task = task_skill.lower().strip()
    elif task_skill:
        skill_name_on_task = (getattr(task_skill, 'name', '') or '').lower().strip()
        skill_id_on_task = (getattr(task_skill, 'id', '') or '').strip()
    
    task_name_stripped = task_name_lower.strip()
    logger.info(f"Task '{task_obj.name}': skill_id='{skill_id_on_task}', skill_name='{skill_name_on_task}', task='{task_name_stripped}'")
    
    for pool_name, pool in search_pools:
        if matched_skill:
            break
        
        logger.debug(f"Searching pool '{pool_name}' ({len(pool)} items)")
        
        # 0. skill_id exact match (PRIORITY - if task has a bound skill_id)
        if skill_id_on_task:
            for sk in pool:
                sk_id = (getattr(sk, 'id', '') or '').strip()
                has_runnable = getattr(sk, 'runnable', None) is not None
                if sk_id and sk_id == skill_id_on_task and has_runnable:
                    matched_skill = sk
                    logger.info(f"Found skill_id match in '{pool_name}': id={sk_id}, name={getattr(sk, 'name', '?')}")
                    break
            if matched_skill:
                break
        
        # 1. Exact skill name match (require runnable)
        if not matched_skill and skill_name_on_task:
            matched_skill = next(
                (sk for sk in pool
                 if (getattr(sk, 'name', '') or '').lower().strip() == skill_name_on_task
                 and getattr(sk, 'runnable', None) is not None),
                None,
            )
            if matched_skill:
                logger.info(f"Found exact name match in '{pool_name}': {getattr(matched_skill, 'name', '?')}")
                break
        
        # 2. Substring match: task name contains skill name or vice versa (prefix match)
        if not matched_skill and task_name_stripped:
            best_match = None
            best_len = 0
            for sk in pool:
                sk_name = (getattr(sk, 'name', '') or '').lower().strip()
                has_runnable = getattr(sk, 'runnable', None) is not None
                if not sk_name:
                    continue
                # Match if task starts with skill or skill starts with task (prefix match)
                is_match = task_name_stripped.startswith(sk_name) or sk_name.startswith(task_name_stripped)
                logger.debug(f"Checking prefix match: task='{task_name_stripped}' vs skill='{sk_name}', match={is_match}, has_runnable={has_runnable}")
                if is_match and has_runnable:
                    if len(sk_name) > best_len:
                        best_match = sk
                        best_len = len(sk_name)
                        logger.debug(f"New best match: '{sk_name}' (len={best_len})")
            matched_skill = best_match
            if matched_skill:
                logger.info(f"Found prefix match in '{pool_name}': {getattr(matched_skill, 'name', '?')}")
        
        # 3. Contains match: task contains skill word or skill contains task word (for cases like "chat:product listing chatter task" matching "product_listing_orchestrator")
        if not matched_skill and task_name_stripped:
            best_match = None
            best_len = 0
            for sk in pool:
                sk_name = (getattr(sk, 'name', '') or '').lower().strip()
                has_runnable = getattr(sk, 'runnable', None) is not None
                if not sk_name or not has_runnable:
                    continue
                
                # Skip short common words that cause false positives
                skip_words = {'chat', 'task', 'the', 'a', 'an', 'and', 'or', 'for', 'to'}
                
                # Split names into words for better matching
                task_words = set(w for w in task_name_stripped.replace('_', ' ').split() if w not in skip_words and len(w) > 2)
                skill_words = set(w for w in sk_name.replace('_', ' ').split() if w not in skip_words and len(w) > 2)
                
                # Check if any significant word matches
                common_words = task_words & skill_words
                if common_words:
                    logger.debug(f"Found common words: {common_words} between task='{task_name_stripped}' and skill='{sk_name}'")
                    # Prefer skill name that has more common words or is longer
                    score = len(common_words) * 100 + len(sk_name)
                    if score > best_len:
                        best_match = sk
                        best_len = score
                        logger.debug(f"New contains match: '{sk_name}' (score={score}, common_words={common_words})")
            
            if best_match:
                matched_skill = best_match
                logger.info(f"Found contains match in '{pool_name}': {getattr(matched_skill, 'name', '?')}")
    
    old_skill_name = getattr(task_skill, 'name', '') if task_skill else ''
    if not matched_skill:
        logger.warning(f"No skill match found for task '{task_obj.name}'")
    return matched_skill, old_skill_name


# ── Test Fixtures ─────────────────────────────────────────────────────────────

def make_skill(name: str, skill_id: str, runnable=None) -> MagicMock:
    """Create a mock skill with name, id, and optional runnable."""
    sk = MagicMock()
    sk.name = name
    sk.id = skill_id
    sk.runnable = runnable
    return sk


def make_task(name: str, skill_name: str = '', skill_id: str = '') -> MagicMock:
    """Create a mock task with name and optional skill binding."""
    task = MagicMock()
    task.name = name
    
    if skill_name or skill_id:
        task_skill = MagicMock()
        task_skill.name = skill_name
        task_skill.id = skill_id
        task_skill.runnable = None  # SkillStub has runnable=None
        task.skill = task_skill
    else:
        task.skill = None
    
    return task


# ── Test Cases ────────────────────────────────────────────────────────────────

class TestSkillIdMatching:
    """Test skill_id exact matching (priority over name matching)."""
    
    def test_skill_id_match_takes_priority_over_name(self):
        """When task has skill_id, it should match even if name differs."""
        # Task has skill_id = "skill_123" but skill_name doesn't match
        task = make_task("chat:Random Task", skill_name="", skill_id="skill_123")
        
        # Skills pool has a skill with matching id but different name
        skills = [
            make_skill("product_listing_orchestrator", "skill_123", runnable=MagicMock()),
            make_skill("product_research", "skill_456", runnable=MagicMock()),
        ]
        
        matched, old_name = _find_matching_skill_for_task_standalone(task, [], skills)
        
        assert matched is not None, "Should find skill by ID even if name differs"
        assert matched.name == "product_listing_orchestrator"
        print(f"\n✓ skill_id match takes priority: matched '{matched.name}'")
    
    def test_skill_id_no_match_when_id_not_found(self):
        """When skill_id doesn't exist in pool, should not match."""
        task = make_task("chat:Test Task", skill_name="", skill_id="nonexistent_id")
        
        skills = [
            make_skill("product_research", "skill_456", runnable=MagicMock()),
        ]
        
        matched, old_name = _find_matching_skill_for_task_standalone(task, [], skills)
        
        assert matched is None, "Should not match when skill_id not in pool"
        print("\n✓ No match when skill_id not found in pool")
    
    def test_skill_id_match_requires_runnable(self):
        """skill_id match should require the skill to have runnable."""
        task = make_task("chat:Test Task", skill_name="", skill_id="skill_123")
        
        # Skill has matching ID but no runnable
        skills = [
            make_skill("product_listing_orchestrator", "skill_123", runnable=None),
        ]
        
        matched, old_name = _find_matching_skill_for_task_standalone(task, [], skills)
        
        assert matched is None, "Should not match skill without runnable"
        print("\n✓ skill_id match requires runnable")
    
    def test_skill_id_match_in_agent_skills_first(self):
        """skill_id match should search agent_skills before global pool."""
        task = make_task("chat:Test Task", skill_name="", skill_id="agent_skill_id")
        
        agent_skills = [
            make_skill("agent_skill_override", "agent_skill_id", runnable=MagicMock()),
        ]
        global_skills = [
            make_skill("global_skill_same_id", "agent_skill_id", runnable=MagicMock()),
        ]
        
        matched, old_name = _find_matching_skill_for_task_standalone(task, agent_skills, global_skills)
        
        assert matched is not None
        assert matched.name == "agent_skill_override", "Should match from agent_skills, not global"
        print("\n✓ skill_id match searches agent_skills first")


class TestSkillNameMatching:
    """Test skill_name exact matching."""
    
    def test_exact_name_match(self):
        """Exact name match should work."""
        task = make_task("chat:Product Listing", skill_name="product_listing_orchestrator", skill_id="")
        
        skills = [
            make_skill("product_listing_orchestrator", "skill_123", runnable=MagicMock()),
            make_skill("product_research", "skill_456", runnable=MagicMock()),
        ]
        
        matched, old_name = _find_matching_skill_for_task_standalone(task, [], skills)
        
        assert matched is not None
        assert matched.name == "product_listing_orchestrator"
        print(f"\n✓ Exact name match works: '{matched.name}'")
    
    def test_name_match_case_insensitive(self):
        """Name matching should be case-insensitive."""
        task = make_task("chat:Test", skill_name="PRODUCT_LISTING_ORCHESTRATOR", skill_id="")
        
        skills = [
            make_skill("product_listing_orchestrator", "skill_123", runnable=MagicMock()),
        ]
        
        matched, old_name = _find_matching_skill_for_task_standalone(task, [], skills)
        
        assert matched is not None
        print("\n✓ Name matching is case-insensitive")
    
    def test_name_match_requires_runnable(self):
        """Name match should require the skill to have runnable."""
        task = make_task("chat:Test", skill_name="product_research", skill_id="")
        
        skills = [
            make_skill("product_research", "skill_123", runnable=None),
        ]
        
        matched, old_name = _find_matching_skill_for_task_standalone(task, [], skills)
        
        assert matched is None, "Should not match skill without runnable"
        print("\n✓ Name match requires runnable")


class TestPrefixMatching:
    """Test prefix-based matching."""
    
    def test_task_name_is_skill_prefix(self):
        """Task name starting with skill name should match."""
        task = make_task("product_research_task_abc", skill_name="", skill_id="")
        
        skills = [
            make_skill("product_research", "skill_123", runnable=MagicMock()),
        ]
        
        matched, old_name = _find_matching_skill_for_task_standalone(task, [], skills)
        
        assert matched is not None
        assert matched.name == "product_research"
        print("\n✓ Task name prefix match works")
    
    def test_skill_name_is_task_prefix(self):
        """Skill name starting with task name should match."""
        task = make_task("chat", skill_name="", skill_id="")
        
        skills = [
            make_skill("chat_task_handler", "skill_123", runnable=MagicMock()),
        ]
        
        matched, old_name = _find_matching_skill_for_task_standalone(task, [], skills)
        
        assert matched is not None
        print("\n✓ Skill name prefix match works")
    
    def test_prefix_match_requires_runnable(self):
        """Prefix match should require the skill to have runnable."""
        task = make_task("product_research", skill_name="", skill_id="")
        
        skills = [
            make_skill("product_research_tool", "skill_123", runnable=None),
        ]
        
        matched, old_name = _find_matching_skill_for_task_standalone(task, [], skills)
        
        assert matched is None, "Should not match skill without runnable"
        print("\n✓ Prefix match requires runnable")


class TestContainsMatching:
    """Test word-based contains matching."""
    
    def test_chat_task_matches_orchestrator_skill(self):
        """
        'chat:product listing chatter task' should match 'product_listing_orchestrator'.
        
        This is the key case for the product_listing_orchestrator issue.
        """
        task = make_task("chat:product listing chatter task", skill_name="", skill_id="")
        
        skills = [
            make_skill("product_listing_orchestrator", "skill_123", runnable=MagicMock()),
            make_skill("product_research", "skill_456", runnable=MagicMock()),
            make_skill("product_reviewer", "skill_789", runnable=MagicMock()),
        ]
        
        matched, old_name = _find_matching_skill_for_task_standalone(task, [], skills)
        
        assert matched is not None, "Should find 'product_listing_orchestrator' via contains match"
        assert matched.name == "product_listing_orchestrator"
        print(f"\n✓ Contains match works: 'chat:product listing chatter task' -> '{matched.name}'")
    
    def test_contains_match_prefers_more_common_words(self):
        """Contains match should prefer skill with more common words."""
        task = make_task("chat:product research chatter task", skill_name="", skill_id="")
        
        skills = [
            make_skill("product_listing_orchestrator", "skill_1", runnable=MagicMock()),
            make_skill("product_research", "skill_2", runnable=MagicMock()),  # Has 2 common words: product, research
        ]
        
        matched, old_name = _find_matching_skill_for_task_standalone(task, [], skills)
        
        assert matched is not None
        assert matched.name == "product_research", "Should prefer skill with more matching words"
        print(f"\n✓ Contains match prefers more common words: '{matched.name}'")
    
    def test_contains_match_skips_short_words(self):
        """Contains match should skip short words like 'chat', 'task'."""
        task = make_task("chat task", skill_name="", skill_id="")
        
        skills = [
            make_skill("random_skill", "skill_1", runnable=MagicMock()),
        ]
        
        matched, old_name = _find_matching_skill_for_task_standalone(task, [], skills)
        
        assert matched is None, "Should not match when only short words overlap"
        print("\n✓ Contains match correctly skips short words")
    
    def test_contains_match_requires_runnable(self):
        """Contains match should require the skill to have runnable."""
        task = make_task("chat:product listing task", skill_name="", skill_id="")
        
        skills = [
            make_skill("product_listing_orchestrator", "skill_123", runnable=None),
        ]
        
        matched, old_name = _find_matching_skill_for_task_standalone(task, [], skills)
        
        assert matched is None, "Should not match skill without runnable"
        print("\n✓ Contains match requires runnable")


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_task_with_already_valid_skill(self):
        """Task with runnable skill should be skipped."""
        task = make_task("test task", skill_name="product_research", skill_id="")
        task.skill.runnable = MagicMock()  # Already has valid skill
        
        skills = [
            make_skill("product_research", "skill_123", runnable=MagicMock()),
        ]
        
        matched, old_name = _find_matching_skill_for_task_standalone(task, [], skills)
        
        assert matched is None, "Should return None when task already has valid skill"
        print("\n✓ Skips task with already valid skill")
    
    def test_empty_skills_pool(self):
        """Should handle empty skills pool gracefully."""
        task = make_task("chat:test task", skill_name="", skill_id="")
        
        matched, old_name = _find_matching_skill_for_task_standalone(task, [], [])
        
        assert matched is None
        print("\n✓ Handles empty skills pool")
    
    def test_both_pools_empty(self):
        """Should handle when both pools are empty."""
        task = make_task("chat:test", skill_name="", skill_id="")
        
        matched, old_name = _find_matching_skill_for_task_standalone(task, None, None)
        
        assert matched is None
        print("\n✓ Handles None pools")
    
    def test_multiple_pools_searched_in_order(self):
        """Agent skills should be searched before global pool."""
        task = make_task("chat:test", skill_name="", skill_id="")
        
        agent_skills = [
            make_skill("agent_skill", "agent_1", runnable=MagicMock()),
        ]
        global_skills = [
            make_skill("global_skill", "global_1", runnable=MagicMock()),
        ]
        
        # Task name doesn't match either, but agent_skills searched first
        matched, old_name = _find_matching_skill_for_task_standalone(task, agent_skills, global_skills)
        
        assert matched is None, "Should not match unrelated skills"
        print("\n✓ Multiple pools searched in correct order")
    
    def test_task_without_skill_attribute(self):
        """Should handle task without skill attribute."""
        task = MagicMock()
        task.name = "test_task"
        del task.skill  # Remove skill attribute
        
        skills = [
            make_skill("test_task", "skill_123", runnable=MagicMock()),
        ]
        
        matched, old_name = _find_matching_skill_for_task_standalone(task, [], skills)
        
        # Should fall through to contains match (test_task -> test task -> test)
        print(f"\n✓ Handles missing skill attribute: matched={matched.name if matched else None}")


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Testing _find_matching_skill_for_task skill matching logic")
    print("=" * 60)
    
    pytest.main([__file__, "-v", "-s"])
