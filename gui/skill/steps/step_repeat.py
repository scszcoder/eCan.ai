from gui.skill.steps.step_base import StepBase


class StepRepeat(StepBase):
    TYPE_KEY = "Repeat"

    def __init__(self, stepN=0, condition=None, count=0, end=None, lc_name=None):
        super().__init__(stepN)

        self.type = self.TYPE_KEY
        self.lc_name = lc_name
        self.until = condition
        self.count: int = count
        self.end = end
