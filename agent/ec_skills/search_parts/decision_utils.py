import json
from asteval import Interpreter
# cost,
# availability, (lead time)
# quality, (defects, ppm),
# standards compliance
# technical performance - {

# }

def calc_score(result):
    score = 0
    aeval = Interpreter()

    if result:
        for k, v in result.items():
            variables = {"x": result[k]["raw_value"]}
            partial_raw_score = aeval(result[k]['score_formula'], variables)
            print("partial_raw_score", partial_raw_score, partial_raw_score*result[k]["weight"])

            result[k]["score"] = partial_raw_score
            score += result[k]["score"]*result[k]["weight"]

    print("final score", score)
    return score