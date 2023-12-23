from skill.steps.step_base import StepBase
from enum import Enum


class StepSearchScroll(StepBase):
    TYPE_KEY = "Search Scroll"

    def __init__(self, stepN=0, screen=None, anchor=None, at_loc=None, target_loc=None, flag=None, resolution=None,
                 postwait=None, site=None):
        super().__init__(stepN)

        self.type = self.TYPE_KEY
        self.action = "Search Scroll"
        self.anchor = anchor
        self.at_loc = at_loc
        self.target_loc = target_loc
        self.screen = screen
        self.resolution = resolution
        self.postwait = postwait
        self.site = site
        self.flag = flag
