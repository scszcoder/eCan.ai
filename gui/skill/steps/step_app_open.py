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

    def __init__(self, stepN=0, action=EnumAppOpenAction.Cmd, saverb=True, target_type=EnumAppOpenTargetType.Custom,
                 target_link=EnumAppOpenTargetLink.WebSite, anchor_type=EnumAnchorType.Text, anchor_value="None",
                 cargs_type=EnumAppOpenCArgsType.Custom, args="", wait=0):
        super().__init__(stepN)

        self.type = self.TYPE_KEY
        self.action: EnumAppOpenAction = action
        self.save_rb: bool = saverb
        self.target_type: EnumAppOpenTargetType = target_type   # enum: browser, shell, other
        self.target_link: EnumAppOpenTargetLink = target_link   # enum: website, exe path
        self.anchor_type: EnumAnchorType = anchor_type
        self.anchor_value = anchor_value
        self.cargs_type: EnumAppOpenCArgsType = cargs_type
        self.cargs = args
        self.wait: int = wait

    def to_obj(self, obj_dict):
        super().to_obj(obj_dict)

        self.action = EnumAppOpenAction(self.action)
        self.target_type = EnumAppOpenTargetType(self.target_type)
        self.target_link = EnumAppOpenTargetLink(self.target_link)
        self.anchor_type = EnumAnchorType(self.anchor_type)
        self.cargs_type = EnumAppOpenCArgsType(self.cargs_type)
