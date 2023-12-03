from skill.steps.step_base import StepBase
from enum import Enum


class EnumCreateDataType(Enum):
    Int = "int"
    String = "string"
    Float = "float"
    Obj = "obj"


class StepCreateData(StepBase):
    def __init__(self, stepN, dtype, dname, keyname, keyval):
        super().__init__(stepN)

        self.type = "Create Data"
        self.data_type = dtype
        self.data_name = dname
        self.key_name = keyname
        self.key_value = keyval
