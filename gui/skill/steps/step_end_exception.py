from gui.skill.steps.step_base import StepBase


class StepEndException(StepBase):
    TYPE_KEY = "End Exception"

    def __init__(self, stepN=0, cause=None, cdata=None):
        super().__init__(stepN)

        self.type = self.TYPE_KEY
        self.cause = cause
        self.cdata = cdata
