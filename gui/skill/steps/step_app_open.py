from skill.steps.step_base import StepBase, EnumAnchorType
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
    TYPE_KEY = "App Open"

    def __init__(self, stepN=0, action=None, saverb=None, target_type=None, target_link=None, anchor_type=None,
                 anchor_value=None, cargs_type=None, args=None, wait=0):
        super().__init__(stepN)

        self.type = self.TYPE_KEY
        self.action = action   # enum: run, cmd
        self.save_rb = saverb
        self.target_type: EnumAppOpenTargetType = target_type   # enum: browser, shell, other
        self.target_link = target_link   # enum: website, exe path
        self.anchor_type: EnumAnchorType = anchor_type
        self.anchor_value = anchor_value
        self.cargs_type = cargs_type  # enum: direct, shell
        self.cargs = args
        self.wait = wait
