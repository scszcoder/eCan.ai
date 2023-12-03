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
    def __init__(self, stepN, action, action_args, saverb, screen, target, target_type, template, nth, offset_from,
                 offset, offset_unit, move_pause, post_wait, post_move):
        super().__init__(stepN)

        self.type = "Mouse Click"
        self.action = action
        self.action_args = action_args
        self.save_rb = saverb
        self.screen = screen
        self.target_name = target
        self.target_type = target_type
        self.text = template
        self.nth = nth
        self.offset_from = offset_from
        self.offset_unit = offset_unit
        self.offset = offset
        self.move_pause = move_pause
        self.post_move = post_move
        self.post_wait = post_wait
