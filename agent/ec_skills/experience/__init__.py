"""Explore-and-learn for browser skills: what worked, scored by a check, and
recipes found by exploring when the same part keeps failing.

A skill keeps its experience in one folder (per platform, say). Each run:

1. ``ExperienceStore.render(data)`` goes into the browser agent's prompt: the
   notes plus the recipes (scripts with when-to-use), with ``__DATA__`` in each
   script replaced by the run's input data.
2. After the run, a check decides which *parts* came out right (title, SKU
   codes, ...). ``grade(results)`` scores the recipes used for those parts and
   counts consecutive failures per part.
3. ``explore_target(results)`` names a part that failed twice in a row (capped
   per day). The skill then runs an explore browser node with a stronger model
   and ``explore_prompt(...)``; it studies where the page keeps that data, tests
   a method (write, read back, revert -- never save) and returns a recipe.
   ``add_recipe(parse_recipe(final))`` stores it as a candidate; the next run
   uses it and the check promotes or retires it.

Nothing here knows about a particular platform, product or skill.
"""
from .store import ExperienceStore, explore_prompt, parse_recipe

__all__ = ["ExperienceStore", "explore_prompt", "parse_recipe"]
