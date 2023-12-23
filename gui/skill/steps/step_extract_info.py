from skill.steps.step_base import StepBase
from enum import Enum


class StepExtractInfo(StepBase):
    TYPE_KEY = "Extract Info"

    def __init__(self, stepN=0, template=None, settings=None, sink=None, page=None, sect=None, theme=None,
                 page_data=None, option=""):
        super().__init__(stepN)

        self.type = self.TYPE_KEY
        self.settings = settings
        self.template = template
        self.option = option
        self.data_sink = sink
        self.page = page
        self.page_data_info = page_data
        self.theme = theme
        self.section = sect
