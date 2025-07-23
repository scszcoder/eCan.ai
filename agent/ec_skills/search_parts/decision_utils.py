import json
from asteval import Interpreter
# cost,
# availability, (lead time)
# quality, (defects, ppm),
# standards compliance
# technical performance - {

# }

def calc_component_score(component, context=None):
    aeval = Interpreter()
    if context is None:
        context = {}

    # If this is a nested component (dict of subcomponents)
    if isinstance(component.get("raw_value"), dict):
        sub_score = 0
        total_weight = 0
        # Recursively calculate subcomponent scores
        for subname, subcomp in component["raw_value"].items():
            score = calc_component_score(subcomp, context)
            weight = subcomp.get("weight", 1)
            sub_score += score * weight
            total_weight += weight
            # Update context with sub-score if needed by parent formula
            context[subname] = score
        if total_weight > 0:
            sub_score = sub_score / total_weight
        # Calculate parent-level score formula if present
        if component.get("score_formula"):
            context["performance"] = sub_score  # (or change to match the subcomponent key)
            try:
                score = aeval(component["score_formula"], context)
            except Exception:
                score = sub_score
        else:
            score = sub_score
    else:
        # Regular component
        # Try formula
        score = None
        if component.get("score_formula"):
            # Build context for formula
            formula_vars = {
                component["name"]: component["raw_value"],
                "price": component["raw_value"],
                "current": component["raw_value"],
                "speed": component["raw_value"]
            }
            formula_vars.update(context)  # Parent context
            try:
                score = aeval(component["score_formula"], formula_vars)
            except Exception:
                score = 0
        # Or lookup table
        elif component.get("score_lut"):
            lut = component["score_lut"]
            # Try to find the closest value in LUT or use raw_value directly
            rv = str(component["raw_value"])
            score = lut.get(rv, 0)
        else:
            # Fallback: use raw_value as score
            score = component["raw_value"]

    return score

def calc_overall_score(system_def):
    total_score = 0
    total_weight = 0
    for comp in system_def["components"]:
        score = calc_component_score(comp)
        weight = comp.get("weight", 1)
        total_score += score * weight
        total_weight += weight
    if total_weight == 0:
        return 0
    return total_score / total_weight