from skill.steps.step_base import StepBase
from enum import Enum


class EnumMouseScrollAction(Enum):
    ScrollUp = "scroll up"
    ScrollDown = "scroll down"


class EnumMouseScrollUnit(Enum):
    Raw = "raw"
    Screen = "screen"


class StepMouseScroll(StepBase):
    def __init__(self, stepN, action, screen, val, unit, resolution, ran_min, ran_max, postwait, break_here):
        super().__init__(stepN)

        self.type = "Mouse Scroll"
        self.action = action  # scroll up/scroll down
        self.screen = screen
        self.amount = val
        self.resolution = resolution
        self.random_min = ran_min
        self.random_max = ran_max
        self.breakpoint = break_here
        self.postwait = postwait
        self.unit = unit  # raw/screen
