from skill.steps.step_base import StepBase


class StepGoto(StepBase):
    def __init__(self, stepN, gotostep, inpipe, returnstep):
        super().__init__(stepN)

        self.type = "Goto"
        self.goto = gotostep