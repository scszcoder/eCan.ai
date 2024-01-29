from skill.steps.step_base import StepBase
from enum import Enum


class EnumCreateDataType(Enum):
    Int = "int"
    String = "string"
    Float = "float"
    Bool = "bool"
    Obj = "obj"
    Expr = "expr"


class StepCreateData(StepBase):
    TYPE_KEY = "Create Data"

    def __init__(self, stepN=0, dtype=EnumCreateDataType.Int, dname=None, keyname="NA", keyval=None):
        super().__init__(stepN)

        self.type = self.TYPE_KEY
        self.data_type: EnumCreateDataType = dtype
        self.data_name = dname
        self.key_name = keyname
        self.key_value = keyval

    def to_obj(self, obj_dict):
        super().to_obj(obj_dict)

        self.data_type = EnumCreateDataType(self.data_type)
