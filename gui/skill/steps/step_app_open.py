from skill.steps.step_base import StepBase
from enum import Enum


class EnumAppOpenAction(Enum):
    Run = "run"
    Cmd = "cmd"


class EnumAppOpenTargetType(Enum):
    Browser = "browser"
    Shell = "shell"
    Icon = "Icon"
    Custom = "custom"


class EnumAppOpenTargetLink(Enum):
    RarExe = "rarexe"
    Explorer = "explorer"
    WebSite = "web site"


class EnumAppOpenCArgsType(Enum):
    Direct = "direct"
    Expr = "expr"
    Custom = "custom"


class StepAppOpen(StepBase):
    def __init__(self, stepN, action, saverb, target_type, target_link, anchor_type, anchor_value, cargs_type, args, wait):
        super().__init__(stepN)

        self.type = "App Open"
        self.action = action   # enum: run, cmd
        self.save_rb = saverb
        self.target_type = target_type   # enum: browser, shell, other
        self.target_link = target_link   # enum: website, exe path
        self.anchor_type = anchor_type
        self.anchor_value = anchor_value
        self.cargs_type = cargs_type  # enum: direct, shell
        self.cargs = args
        self.wait = wait
