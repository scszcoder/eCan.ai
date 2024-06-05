from gui.skill.steps.step_base import StepBase


class StepKeyInput(StepBase):
    TYPE_KEY = "Key Input"

    def __init__(self, stepN=0, action=None, saverb=True, val=None, loc=None, wait_after=0.0):
        super().__init__(stepN)

        self.type = self.TYPE_KEY
        self.action = action
        self.action_value = val
        self.save_rb: bool = saverb
        self.location = loc
        self.wait_after: float = wait_after

    def gen_step(self, stepN, **kwargs):
        self.wait_after = float(self.wait_after)
        json_step = super().gen_step(stepN)

        return json_step

