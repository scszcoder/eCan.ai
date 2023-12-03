from skill.steps.step_base import StepBase
from enum import Enum


class EnumFillDataType(Enum):
    Assign = "assign"
    Copy = "copy"
    Append = "append"
    Prepend = "prepend"
    Merge = "merge"
    Clear = "clear"
    Pop = "pop"


class StepFillData(StepBase):
    def __init__(self, stepN, fill_type, src, sink, result):
        super().__init__(stepN)

        self.type = "Fill Data"
        self.fill_type = fill_type
        self.src = src
        self.to = sink
        self.result = result

    # TODO from is keyword, shoud replace other word
    def gen_step(self):
        json_step = super().gen_step()
        json_step.replace("src", "from")

        return json_step

