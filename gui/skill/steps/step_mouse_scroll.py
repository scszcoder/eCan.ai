from gui.skill.steps.step_base import StepBase
from enum import Enum


class EnumMouseScrollAction(Enum):
    ScrollUp = "scroll up"
    ScrollDown = "scroll down"


class EnumMouseScrollUnit(Enum):
    Raw = "raw"
    Screen = "screen"


class StepMouseScroll(StepBase):
    TYPE_KEY = "Mouse Scroll"

    def __init__(self, stepN=0, action=EnumMouseScrollAction.ScrollDown, screen="screen_info", val=30, unit=EnumMouseScrollUnit.Screen, resolution=None, ran_min=0,
                 ran_max=0, postwait=0.5, break_here=False):
        super().__init__(stepN)

        self.type = self.TYPE_KEY
        self.action: EnumMouseScrollAction = action  # scroll up/scroll down
        self.screen = screen
        self.amount: int = val
        self.resolution = resolution
        self.random_min: int = ran_min
        self.random_max: int = ran_max
        self.breakpoint: bool = break_here
        self.postwait: float = postwait
        self.unit: EnumMouseScrollUnit = unit  # raw/screen

    def gen_step(self, stepN, **kwargs):
        self.postwait = float(self.postwait)
        self.amount = int(self.amount)
        self.random_min = int(self.random_min)
        self.random_max = int(self.random_max)
        json_step = super().gen_step(stepN)

        return json_step

    def to_obj(self, obj_dict):
        super().to_obj(obj_dict)

        self.action = EnumMouseScrollAction(self.action)
        self.unit = EnumMouseScrollUnit(self.unit)
