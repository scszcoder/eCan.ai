from abc import ABC, abstractmethod
from enum import Enum

from basicSkill import STEP_GAP
import json


class EnumAnchorType(Enum):
    Text = "text"
    Icon = "icon"
    IconGroup = "icon group"


class EnumAnchorMethod(Enum):
    Distinct = 0
    Polygon = 1
    Line = 2
    Group = 3


class StepBase(ABC):

    def __init__(self, stepN=0):
        self.stepN = stepN
        self.type = None
        self.remark: EnumAnchorType = None

    # @abstractmethod
    def gen_step(self):
        obj = self.__dict__.copy()
        del obj['stepN']  # delete 'stepN' field
        if self.remark is None:
            del obj['remark']
        json_str = json.dumps(obj, indent=4)
        json_step = ((self.stepN + STEP_GAP), ("\"step " + str(self.stepN) + "\":\n" + json_str + ",\n"))

        return json_step

    def custom_sort(self, key_value):
        key, value = key_value
        if key == 'type':
            return 0  # 将值为 "type" 的键排在前面
        else:
            return 1

    def gen_attrs(self):
        obj = self.__dict__.copy()
        del obj['stepN']

        obj = sorted(obj.items(), key=self.custom_sort)

        return dict(obj)

    def attr_type(self, field_name):
        value = getattr(self, field_name)
        print(f" {field_name} attr type = {type(value)}")
        return type(value)


if __name__ == '__main__':
    step = StepBase()
    # step.remark = EnumAnchorType.Text
    print(step.attr_type("remark"))
    if isinstance(step.remark, EnumAnchorType):
        print("#####")
    else:
        print("****")
