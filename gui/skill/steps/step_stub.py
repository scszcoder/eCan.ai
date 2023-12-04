from skill.steps.step_base import StepBase
from enum import Enum


class EnumStubName(Enum):
    StartSkill = "start skill"
    EndSkill = "end skill"
    Function = "function"
    EndFunction = "end function"
    Else = "else"
    EndLoop = "end loop"
    EndCondition = "end condition"


class StepStub(StepBase):
    TYPE_KEY = "Stub"

    def __init__(self, stepN=0, sname=None, fname=None, fargs=None):
        super().__init__(stepN)

        self.type = self.TYPE_KEY
        self.stub_name: EnumStubName = sname
        self.func_name: str = fname
        self.fargs: str = fargs

