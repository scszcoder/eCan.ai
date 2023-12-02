from skill.steps.step_base import StepBase


class StepWait(StepBase):
    def __init__(self, stepN, wait, random_min, random_max):
        super().__init__(stepN)

        self.type = "Wait"
        self.random_min = random_min
        self.random_max = random_max
        self.time = wait


if __name__ == '__main__':
    step = StepWait(0, 5, 0, 0)

    print(step.gen_step())
