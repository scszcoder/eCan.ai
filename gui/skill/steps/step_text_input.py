from skill.steps.step_base import StepBase
from enum import Enum


class EnumTextInputType(Enum):
    Var = "var"
    List = "List"


class StepTextInput(StepBase):
    TYPE_KEY = "Text Input"

    def __init__(self, stepN=0, txt_type=EnumTextInputType.Var, saverb=True, txt=None, speed=0.0, key_after=None,
                 wait_after=None):
        super().__init__(stepN)

        self.type = self.TYPE_KEY
        self.txt_type: EnumTextInputType = txt_type
        self.save_rb: bool = saverb
        self.text = txt
        self.speed: float = speed
        self.key_after = key_after
        self.wait_after = wait_after
