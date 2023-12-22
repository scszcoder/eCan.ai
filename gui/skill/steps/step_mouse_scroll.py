from skill.steps.step_base import StepBase
from enum import Enum


class EnumMouseScrollAction(Enum):
    ScrollUp = "scroll up"
    ScrollDown = "scroll down"


class EnumMouseScrollUnit(Enum):
    Raw = "raw"
    Screen = "screen"


class StepMouseScroll(StepBase):
    TYPE_KEY = "Mouse Scroll"

    def __init__(self, stepN=0, action=None, screen=None, val=None, unit=None, resolution=None, ran_min=None,
                 ran_max=None, postwait=None, break_here=None):
        super().__init__(stepN)

        self.type = self.TYPE_KEY
        self.action: EnumMouseScrollAction = action  # scroll up/scroll down
        self.screen = screen
        self.amount = val
        self.resolution = resolution
        self.random_min = ran_min
        self.random_max = ran_max
        self.breakpoint = break_here
        self.postwait = postwait
        self.unit: EnumMouseScrollUnit = unit  # raw/screen

    def to_obj(self, obj_dict):
        super().to_obj(obj_dict)

        self.action = EnumMouseScrollAction(self.action)
        self.unit = EnumMouseScrollUnit(self.unit)
