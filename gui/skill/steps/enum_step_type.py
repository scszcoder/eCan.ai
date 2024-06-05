from enum import Enum

from skill.steps.step_app_open import StepAppOpen
from skill.steps.step_call_function import StepCallFunction
from skill.steps.step_check_condition import StepCheckCondition
from skill.steps.step_create_data import StepCreateData
from skill.steps.step_end_exception import StepEndException
from skill.steps.step_execption_handler import StepExceptionHandler
from skill.steps.step_extract_info import StepExtractInfo
from skill.steps.step_fill_data import StepFillData
from skill.steps.step_goto import StepGoto
from skill.steps.step_key_input import StepKeyInput
from skill.steps.step_mouse_click import StepMouseClick
from skill.steps.step_mouse_scroll import StepMouseScroll
from skill.steps.step_repeat import StepRepeat
from skill.steps.step_return import StepReturn
from skill.steps.step_search_scroll import StepSearchScroll
from skill.steps.step_stub import StepStub
from skill.steps.step_text_input import StepTextInput
from skill.steps.step_text_to_number import StepTextToNumber
from skill.steps.step_use_skill import StepUseSkill
from skill.steps.step_wait import StepWait


# enum step format: (name, (key, class))
class EnumStepType(Enum):
    # Halt = ("Halt", None)
    Wait = (StepWait.TYPE_KEY, StepWait)
    # SaveHtml = ("Save Html", None)
    # Browse = ("Browse", None)
    TextToNumber = (StepTextToNumber.TYPE_KEY, StepTextToNumber)
    ExtractInfo = (StepExtractInfo.TYPE_KEY, StepExtractInfo)
    TextInput = (StepTextInput.TYPE_KEY, StepTextInput)
    MouseClick = (StepMouseClick.TYPE_KEY, StepMouseClick)
    MouseScroll = (StepMouseScroll.TYPE_KEY, StepMouseScroll)
    # "Calibrate Scroll"
    # "Text Line Location Record"
    KeyInput = (StepKeyInput.TYPE_KEY, StepKeyInput)
    AppOpen = (StepAppOpen.TYPE_KEY, StepAppOpen)
    CreateData = (StepCreateData.TYPE_KEY, StepCreateData)
    FillData = (StepFillData.TYPE_KEY, StepFillData)
    # LoadData = ("Load Data", None)
    # SaveData = ("Save Data", None)
    CheckCondition = (StepCheckCondition.TYPE_KEY, StepCheckCondition)
    Repeat = (StepRepeat.TYPE_KEY, StepRepeat)
    Goto = (StepGoto.TYPE_KEY, StepGoto)
    CallFunction = (StepCallFunction.TYPE_KEY, StepCallFunction)
    Return = (StepReturn.TYPE_KEY, StepReturn)
    UseSkill = (StepUseSkill.TYPE_KEY, StepUseSkill)
    # OverloadSkill = ("Overload Skill", None)
    Stub = (StepStub.TYPE_KEY, StepStub)
    # CallExtern = ("Call Extern", StepCallExtern)
    ExceptionHandler = (StepExceptionHandler.TYPE_KEY, StepExceptionHandler)
    EndException = (StepEndException.TYPE_KEY, StepEndException)
    # SearchAnchorInfo = ("Search Anchor Info", None)
    # SearchWorkLine = ("Search Word Line", None)
    # "FillRecipients"
    SearchScroll = (StepSearchScroll.TYPE_KEY, StepSearchScroll)
    # SevenZip = ("Seven Zip", None)
    # ListDir = ("List Dir", None)
    # CheckExistence = ("Check Existence", None)
    # CreateDir = ("Create Dir", None)
    # PrintLable = ("Print Label", None)
    # "AMZ Search Products"
    # "AMZ Scrape PL Html"
    # "AMZ Browse Details"
    # "AMZ Scrape Details Html"
    # "AMZ Browse Reviews"
    # "AMZ Scrape Reviews Html"
    # "AMZ Scrape Orders Html"
    # "EBAY Scrape Orders Html"
    # "ETSY Scrape Orders"
    # "Etsy Get Order Clicked Status"
    # "Etsy Set Order Clicked Status"
    # "Etsy Find Screen Order"
    # "Etsy Remove Expanded"
    # "Etsy Extract Tracking"
    # "Etsy Add Page Of Order"
    # "GS Scrape Labels"
    # "GS Extract Zipped"
    # "Prep GS Order"
    # "AMZ Match Products"

    def name(self):
        return self.value[0]

    def type_key(self):
        return self.value[0]

    @staticmethod
    def gen_step_obj(type_key):
        for name, member in EnumStepType.__members__.items():
            key, cls = member.value
            if key == type_key and cls is not None:
                return cls()

        return None

    @staticmethod
    def items():
        items = []
        for name, member in EnumStepType.__members__.items():
            items.append(member.value)

        return items

    @staticmethod
    def need_end_step_stub_type_keys():
        return [EnumStepType.CheckCondition.type_key(),
                EnumStepType.Repeat.type_key(),
                EnumStepType.CallFunction.type_key(),
                EnumStepType.Stub.type_key()]

    @staticmethod
    def belong_io_step_type_keys():
        return [EnumStepType.TextInput.type_key(),
                EnumStepType.ExtractInfo.type_key(),
                EnumStepType.KeyInput.type_key(),
                EnumStepType.FillData.type_key()]

    @staticmethod
    def belong_start_end_step_type_keys():
        return [EnumStepType.Stub.type_key()]

    @staticmethod
    def belong_condition_step_type_keys():
        return [EnumStepType.CheckCondition.type_key()]

    @staticmethod
    def belong_process_step_type_keys():
        keys = []
        for key, value in EnumStepType.items():
            if (key not in EnumStepType.belong_condition_step_type_keys()
                    and key not in EnumStepType.belong_start_end_step_type_keys()
                    and key not in EnumStepType.belong_io_step_type_keys()):
                keys.append(key)

        return keys


if __name__ == '__main__':
    print(EnumStepType.Wait.value)
    key, cls = EnumStepType.Wait.value
    print(cls().time)

    obj = EnumStepType.gen_step_obj("Wait")
    print(obj.time)

    print(EnumStepType.Wait.type_key())

    print("########")
    print(EnumStepType.need_end_step_stub_type_keys())
