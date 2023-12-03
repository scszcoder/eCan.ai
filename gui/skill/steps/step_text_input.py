from skill.steps.step_base import StepBase
from enum import Enum


class EnumTextInputType(Enum):
    Var = "var"
    List = "List"


class StepTextInput(StepBase):
    def __init__(self, stepN, txt_type, saverb, txt, speed, key_after, wait_after):
        super().__init__(stepN)

        self.type = "Text Input"
        self.txt_type = txt_type
        self.save_rb = saverb
        self.text = txt
        self.speed = speed
        self.key_after = key_after
        self.wait_after = wait_after
