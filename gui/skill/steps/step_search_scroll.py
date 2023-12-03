from skill.steps.step_base import StepBase
from enum import Enum


class StepSearchScroll(StepBase):
    def __init__(self, stepN, screen, anchor, at_loc, target_loc, flag, resolution, postwait, site):
        super().__init__(stepN)

        self.type = "Search Scroll"
        self.action = "Search Scroll"
        self.anchor = anchor
        self.at_loc = at_loc
        self.target_loc = target_loc
        self.screen = screen
        self.resolution = resolution
        self.postwait = postwait
        self.site = site
        self.flag = flag
