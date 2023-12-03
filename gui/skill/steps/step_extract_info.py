from skill.steps.step_base import StepBase
from enum import Enum


class StepExtractInfo(StepBase):
    def __init__(self, stepN, template, settings, sink, page, sect, theme, page_data, option=""):
        super().__init__(stepN)

        self.type = "Extract Info"
        self.settings = settings
        self.template = template
        self.option = option
        self.data_sink = sink
        self.page = page
        self.page_data_info = page_data
        self.theme = theme
        self.section = sect
