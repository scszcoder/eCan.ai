from skill.steps.step_base import StepBase
from enum import Enum


class EnumStubName(Enum):
    StartSkill = "start skill"
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

    def get_dict_attrs(self):
        obj = super().get_dict_attrs()
        del obj['tag']

        return obj

    def to_obj(self, obj_dict):
        super().to_obj(obj_dict)
        self.stub_name = EnumStubName(self.stub_name)

    def attr_type(self, attr_name):
        print(repr(self.stub_name))
        if attr_name == repr(self.stub_name):
            return Enum

        return str


if __name__ == '__main__':
    step = StepStub()
    print(step.stub_name)
    step.stub_name = EnumStubName("end skill")
    print(step.stub_name)

    # print(type(stub_name))
    # print(stub_name)
    # print(type(EnumStubName.StartSkill))
    #
    # print(step.gen_attrs())
    # print(step.attr_type("stub_name"))

    print(step.gen_step(0))

