from gui.skfc.skfc_base import EnumSkType
from gui.skill.steps.step_base import StepBase
from enum import Enum


class EnumStubName(Enum):
    StartSkill = "start skill"
    StartSkillMain = "start skill main"
    Function = "function"
    Else = "else"
    Break = "break"
    EndSkill = "end skill"
    EndFunction = "end function"
    EndLoop = "end loop"
    EndCondition = "end condition"
    DefFunction = "def function"
    Tag = "tag"


class StepStub(StepBase):
    TYPE_KEY = "Stub"

    def __init__(self, stepN=0, sname=EnumStubName.StartSkill, fname=None, fargs=None):
        super().__init__(stepN)

        self.type: str = self.TYPE_KEY
        self.stub_name: EnumStubName = sname
        self.func_name: str = fname
        self.fargs: str = fargs

    def need_hidden_fields(self):
        if self.stub_name == EnumStubName.EndSkill:
            return [
                "func_name",
                "fargs"
            ]
        else:
            return [

            ]

    def to_obj(self, obj_dict):
        super().to_obj(obj_dict)
        self.stub_name = EnumStubName(self.stub_name)

    def attr_type(self, attr_name):
        print(repr(self.stub_name))
        if attr_name == repr(self.stub_name):
            return Enum

        return str

    def filter_enum_show_items(self, sktype, enum):
        items = super().filter_enum_show_items(sktype, enum)
        filtered_items = []
        if enum is EnumStubName:
            for name, member in items:
                print(name, member)
                if sktype == EnumSkType.Main.value:
                    if name in [EnumStubName.EndSkill.name,
                                EnumStubName.StartSkillMain.name]:
                        filtered_items.append((name, member))
                else:
                    if name in [EnumStubName.StartSkill.name,
                                EnumStubName.EndSkill.name]:
                        filtered_items.append((name, member))

        return filtered_items


if __name__ == '__main__':
    step = StepStub()
    print(step.stub_name)
    step.stub_name = EnumStubName("end skill")
    print(step.stub_name)

    # print(type(stub_name))
    # print(stub_name)
    # print(type(EnumStubName.StartSkill))
    #
    # print(step.gen_need_show_attrs())
    # print(step.attr_type("stub_name"))

    print(step.gen_step(0))

