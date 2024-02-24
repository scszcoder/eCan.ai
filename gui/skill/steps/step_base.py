from abc import ABC
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
        self.tag = ""

    def get_dict_attrs(self):
        obj = self.__dict__.copy()
        del obj['stepN']

        return obj

    def gen_json_str(self):
        obj = self.to_dict()

        if self.tag is None or self.tag == "":
            del obj['tag']
        #
        # if self.description is None or  self.description == "":
        #     del obj['description']

        json_str = json.dumps(obj, indent=4)

        return json_str

    # 生成step json 格式接口
    def gen_step(self, stepN, **kwargs):
        self.stepN = stepN
        json_str = self.gen_json_str()
        json_step = ((self.stepN + STEP_GAP), ("\"step " + str(self.stepN) + "\":\n" + json_str + ",\n"))

        return json_step

    # 自定义字段顺序
    def custom_sort(self, key_value):
        key, value = key_value
        if key == 'type':
            return 0  # 将值为 "type" 的键排在前面
        else:
            return 1

    # def convert_obj_attrs_to_str(self, src_obj):
    #     dict_names = {key: None for key in src_obj}
    #     result = []
    #     for key in dict_names.keys():
    #         result.append(key)

    def need_hidden_fields(self):
        return []

    def gen_need_show_attrs(self):
        obj = self.get_dict_attrs()
        for attr in self.need_hidden_fields():
            print("need filter field: ", attr)
            if attr in obj:
                del obj[attr]
        obj = sorted(obj.items(), key=self.custom_sort)

        return dict(obj)

    def attr_type(self, field_name):
        value = getattr(self, field_name)
        print(f" {field_name} attr type = {type(value)}")
        return type(value)

    def set_attr_value(self, attr_key, value):
        print(f"set attrs key ({attr_key}) value ({value})")
        setattr(self, attr_key, value)

    def to_dict(self):
        attrs = self.get_dict_attrs()
        for key, obj in attrs.items():
            if isinstance(obj, Enum):
                attrs[key] = obj.value
            # print(f"{key}, {type(obj)}")
        return attrs

    # json 格式转为step 对象接口
    def to_obj(self, obj_dict):
        for key, value in dict(obj_dict).items():
            setattr(self, key, value)

    @classmethod
    def from_dict(cls, obj_dict):
        from gui.skill.steps.enum_step_type import EnumStepType
        step = EnumStepType.gen_step_obj(obj_dict["type"])
        step.to_obj(obj_dict)

        return step


if __name__ == '__main__':
    from gui.skill.steps.step_stub import StepStub, EnumStubName
    step = StepStub(5)
    # step.stub_name = EnumStubName.EndSkill
    # # step.remark = EnumAnchorType.Text
    # # print(step.attr_type("remark"))
    # # if isinstance(step.remark, EnumAnchorType):
    # #     print("#####")
    # # else:
    # #     print("****")
    # obj = step.to_dict()
    # print(obj)
    #
    # step = StepBase.from_dict(obj)
    # print(step)
    # print(step.type)
    # print(step.stub_name)
    print(step.get_dict_attrs())




