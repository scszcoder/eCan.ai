from abc import ABC, abstractmethod
from basicSkill import STEP_GAP
import json


class StepBase(ABC):
    def __init__(self, stepN):
        self.stepN = stepN
        self.type = None
        self.remark = None

    # @abstractmethod
    def gen_step(self):
        obj = self.__dict__.copy()
        del obj['stepN']  # delete 'stepN' field
        if self.remark is None:
            del obj['remark']
        json_str = json.dumps(obj, indent=4)
        json_step = ((self.stepN + STEP_GAP), ("\"step " + str(self.stepN) + "\":\n" + json_str + ",\n"))

        return json_step

