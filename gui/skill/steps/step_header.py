import json

from skill.steps.step_base import StepBase, STEP_GAP


class StepHeader(StepBase):
    TYPE_KEY = "Header"

    def __init__(self, stepN, name, os, version, author, skid, description):
        super().__init__(stepN)

        self.type = self.TYPE_KEY
        self.name = name
        self.os = os
        self.version = version
        self.author = author
        self.skid = skid
        self.description = description

    def gen_step(self):
        obj = self.__dict__.copy()
        del obj['stepN']  # delete 'stepN' field
        if self.remark is None:
            del obj['remark']
        json_str = json.dumps(obj, indent=4)
        json_step = ((self.stepN + STEP_GAP), ("\"header\":\n" + json_str + ",\n"))

        return json_step


if __name__ == '__main__':
    step = StepHeader("win_file_local_open_save_as", "win", "1.0", "AIPPS LLC", "PUBWINFILEOP001",
                "File Open Dialog Handling for Windows.", 0)

    print(step.gen_step())
