from skill.steps.step_base import StepBase


class StepWait(StepBase):
    TYPE_KEY = "Wait"

    def __init__(self, stepN=0, wait=0.0, random_min=0, random_max=0):
        super().__init__(stepN)

        self.type = self.TYPE_KEY
        self.random_min = random_min
        self.random_max = random_max
        self.time: float = wait

    def gen_step(self, stepN):
        self.time = float(self.time)
        json_step = super().gen_step(stepN)

        return json_step

if __name__ == '__main__':
    step = StepWait(0, 5, 0, 0)

    print(step.gen_step())
    print(StepWait.TYPE_KEY)
