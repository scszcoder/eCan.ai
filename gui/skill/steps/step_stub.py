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
    def __init__(self, stepN, sname, fname, fargs):
        super().__init__(stepN)

        self.type = "Stub"
        self.stub_name: str = sname
        self.func_name: str = fname
        self.fargs: str = fargs

