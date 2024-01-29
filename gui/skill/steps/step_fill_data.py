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
    Blank = ""


class StepFillData(StepBase):
    TYPE_KEY = "Fill Data"

    def __init__(self, stepN=0, fill_type=None, src=None, sink=None, result=False):
        super().__init__(stepN)

        self.type = self.TYPE_KEY
        self.fill_type: EnumFillDataType = fill_type
        self.from_ = src
        self.to = sink
        self.result: bool = result

    # TODO from is keyword, should replace other word
    def gen_step(self, stepN, **kwargs):
        json_step = super().gen_step(stepN)
        json_step.replace("from_", "from")

        return json_step

    def to_obj(self, obj_dict):
        super().to_obj(obj_dict)

        self.fill_type = EnumFillDataType(self.fill_type)

