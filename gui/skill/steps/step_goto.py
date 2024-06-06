from gui.skill.steps.step_base import StepBase


class StepGoto(StepBase):
    TYPE_KEY = "Goto"

    def __init__(self, stepN=0, gotostep=None, inpipe=None, returnstep=None):
        super().__init__(stepN)

        self.type = self.TYPE_KEY
        self.goto = gotostep