from skill.steps.step_base import StepBase
from enum import Enum


class EnumMouseClickAction(Enum):
    SingleClick = "single click"
    DoubleClick = "double click"
    RightClick = "right click"
    DragDrop = "drag drop"


class EnumMouseClickOffsetFrom(Enum):
    Left = "left"
    Top = "top"
    Right = "right"
    Bottom = "bottom"
    Center = "center"


class EnumMouseClickOffsetUnit(Enum):
    Pixel = "pixel"
    Box = "box"
    Screen = "screen"


class StepMouseClick(StepBase):
    TYPE_KEY = "Mouse Click"

    def __init__(self, stepN=0, action=EnumMouseClickAction.SingleClick, action_args=None, saverb=True, screen=None,
                 target=None, target_type=None, template=None, nth=None, offset_from=EnumMouseClickOffsetFrom.Top,
                 offset=0.0, offset_unit=EnumMouseClickOffsetUnit.Screen, move_pause=None, post_wait=0.0,
                 post_move=None):
        super().__init__(stepN)

        self.type = self.TYPE_KEY
        self.action: EnumMouseClickAction = action
        self.action_args = action_args
        self.save_rb: bool = saverb
        self.screen = screen
        self.target_name = target
        self.target_type = target_type
        self.text = template
        self.nth = nth
        self.offset_from: EnumMouseClickOffsetFrom = offset_from
        self.offset_unit: EnumMouseClickOffsetUnit = offset_unit
        self.offset: float = offset
        self.move_pause = move_pause
        self.post_move = post_move
        self.post_wait: float = post_wait

    def gen_step(self, stepN, **kwargs):
        self.post_wait = float(self.post_wait)
        self.offset = float(self.offset)
        json_step = super().gen_step(stepN)

        return json_step

    def to_obj(self, obj_dict):
        super().to_obj(obj_dict)

        self.action = EnumMouseClickAction(self.action)
        self.offset_from = EnumMouseClickOffsetFrom(self.offset_from)
        self.offset_unit = EnumMouseClickOffsetUnit(self.offset_unit)
