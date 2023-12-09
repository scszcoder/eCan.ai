from skill.steps.step_base import StepBase
from enum import Enum


class EnumStubName(Enum):
    StartSkill = "start skill"
    Function = "function"
    Else = "else"
    EndSkill = "end skill"
    EndFunction = "end function"
    EndLoop = "end loop"
    EndCondition = "end condition"


class StepStub(StepBase):
    TYPE_KEY = "Stub"

    def __init__(self, stepN=0, sname=EnumStubName.StartSkill, fname=None, fargs=None):
        super().__init__(stepN)

        self.type: str = self.TYPE_KEY
        self.stub_name: EnumStubName = sname
        self.func_name: str = fname
        self.fargs: str = fargs

