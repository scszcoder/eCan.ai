from gui.skill.steps.step_base import StepBase
from bot.basicSkill import STEP_GAP


class StepCallFunction(StepBase):
    TYPE_KEY = "Call Function"

    def __init__(self, stepN=0, fname=None, fargs=None, output=None):
        super().__init__(stepN)

        self.type = self.TYPE_KEY
        self.fname = fname
        self.fargs = fargs
        self.return_to = stepN + STEP_GAP
        self.output = output
