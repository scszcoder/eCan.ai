import json
import os

from PySide6.QtWidgets import QMenu

from gui.skfc.diagram_item_arrow import DiagramArrowItem
from gui.skfc.diagram_item_normal import DiagramNormalItem
from gui.skfc.diagram_item_text import DiagramTextItem
from gui.skfc.skfc_base import EnumItemType
from skill.steps.enum_step_type import EnumStepType
from skill.steps.step_goto import StepGoto
from skill.steps.step_header import StepHeader
from skill.steps.step_stub import StepStub, EnumStubName
# from typing import TYPE_CHECKING
# if TYPE_CHECKING:
from skill.steps.step_base import StepBase


class SkFCSkd:
    def __init__(self):
        super().__init__()

        self.diagram_item_map_stepN = {}

    @staticmethod
    def encode_skd_dict(items, sk_info, indent=None):
        json_dict = {
            "sk_info": sk_info,
            "items": items
        }
        json_str = json.dumps(json_dict, indent=indent)
        print(f"encode sdk dict to json str: {json_str}")

        return json_str

    @staticmethod
    def decode_skd_dict(json_str):
        print(f"decode skd json to dict {json_str}")
        skd_dict = json.loads(json_str)
        items = skd_dict["items"]
        sk_info = skd_dict["sk_info"] if "sk_info" in skd_dict else None

        return items, sk_info

    def gen_psk_file(self, skd_file_path, psk_file_dir):
        if not os.path.exists(skd_file_path):
            print(f"File {skd_file_path} not exist")
            return

        # 打开指定路径的文件，假设文件以文本模式打开，编码为utf-8
        with open(skd_file_path, 'r', encoding='utf-8') as file:
            # 使用read()方法一次性读取文件的全部内容
            file_content = file.read()

        if file_content:
            # 使用json模块将字符串转换为字典
            data = json.loads(file_content)
            sk_info, psk_words = self.gen_psk_file(json.dumps(data))
            psk_file_path = os.path.join(psk_file_dir, sk_info.skname + ".psk")
            if psk_file_path:
                with open(psk_file_path, 'w') as file:
                    file.write(psk_words)
                    print(f'save psk file to {psk_file_path}')

    def gen_psk_file(self, json_str):
        items, sk_info = self.decode_skd_dict(json_str)

        diagram_items = self.decode_diagram_items(items)

        start_diagram_item = self.get_start_skill_diagram_item(diagram_items)
        psk_words = self.gen_psk_body(sk_info, start_diagram_item, None)

        return sk_info, psk_words

    def decode_diagram_items(self, encoded_items, context_menu: QMenu = None):
        arrow_diagram_items = []
        diagram_items = []
        for item in encoded_items:
            diagram_item = None
            str_item_type = item["item_type"]
            enum_item_type = EnumItemType[str_item_type]

            if enum_item_type == EnumItemType.Text:
                diagram_item = DiagramTextItem.from_dict(item, context_menu)
            elif enum_item_type == EnumItemType.Normal:
                diagram_item = DiagramNormalItem.from_dict(item, context_menu)
            elif enum_item_type == EnumItemType.Arrow:
                diagram_item = DiagramArrowItem.from_dict(item, context_menu)
                arrow_diagram_items.append(diagram_item)
            else:
                print(f"diagram scene from json error item type {enum_item_type}")

            if diagram_item is not None:
                diagram_items.append(diagram_item)

        for arrow_diagram_item in arrow_diagram_items:
            start_item = self.get_normal_item_by_uuid(arrow_diagram_item.start_item_uuid, diagram_items)
            arrow_diagram_item.add_start_item(start_item)

            end_item = self.get_normal_item_by_uuid(arrow_diagram_item.end_item_uuid, diagram_items)
            arrow_diagram_item.add_end_item(end_item)

        return diagram_items

    def get_normal_item_by_uuid(self, uuid, diagram_items):
        for item in diagram_items:
            if isinstance(item, DiagramNormalItem) and item.uuid == uuid:
                return item

        return None

    def get_start_skill_diagram_item(self, diagram_items):
        for item in diagram_items:
            if isinstance(item, DiagramNormalItem):
                step = item.step
                if step and step.type == EnumStepType.Stub.type_key():
                    if isinstance(step, StepStub):
                        if step.stub_name == EnumStubName.StartSkill or step.stub_name == EnumStubName.StartSkillMain:
                            return item

        return None

    def get_diagram_item_stepN(self, item):
        for key, value in self.diagram_item_map_stepN.items():
            if value == item:
                return key

        return None

    def get_next_item_steps(self, stepN, worksettings, next_diagram_item):
        this_step = stepN
        temp_steps_stack = []
        existed_next_stepN = self.get_diagram_item_stepN(next_diagram_item)

        # 替换为goto，如果是已经执行过的step
        if existed_next_stepN:
            step = next_diagram_item.step
            if step.tag is not None and step.tag != "":
                this_step, step_words = StepGoto(gotostep=step.tag).gen_step(this_step)
                temp_steps_stack.append(step_words)
            else:
                print("ERROR::::: goto step->", step, " tag is null")
        else:
            this_step, steps_stack = self.gen_skill_steps(next_diagram_item, worksettings, this_step)
            temp_steps_stack.extend(steps_stack)

        return this_step, temp_steps_stack

    def gen_skill_stub_steps(self):
        pass

    def gen_psk_body(self, sk_info, start_diagram_item, worksettings):
        psk_words = "{"
        first_step = 0

        # header
        this_step, step_words = StepHeader(first_step, sk_info.skname, sk_info.sktype, sk_info.os, sk_info.version,
                                           sk_info.author, sk_info.skid, sk_info.description).gen_step(first_step)
        psk_words = psk_words + step_words

        # body steps
        sorted_steps_stack = []
        if start_diagram_item:
            self.diagram_item_map_stepN = {}
            this_step, steps_stack = self.gen_skill_steps(start_diagram_item, worksettings, this_step)
            sorted_steps_stack.extend(steps_stack)

            step_words = ''.join(sorted_steps_stack)
            psk_words = psk_words + step_words
        else:
            print("Error No Start Skill Step Diagram Item")

        # dummy
        psk_words = psk_words + "\"dummy\" : \"\"}"
        print(psk_words)

        return psk_words

    def gen_skill_steps(self, diagram_item, worksettings, stepN):
        sorted_steps_stack = []
        this_step = stepN

        self.diagram_item_map_stepN[this_step] = diagram_item
        step = diagram_item.step
        this_step, step_words = step.gen_step(this_step, settings=worksettings)
        sorted_steps_stack.append(step_words)
        if step.tag is not None and step.tag != "":
            this_step, step_words = StepStub(sname=EnumStubName.Tag, fname=step.tag).gen_step(this_step)
            sorted_steps_stack.append(step_words)
        # print(f"gen step {step.type}; {this_step}")

        if diagram_item.diagram_type == DiagramNormalItem.Conditional:
            true_next_item = diagram_item.get_next_diagram_item(True)
            if true_next_item:
                this_step, steps_stack = self.get_next_item_steps(this_step, worksettings, true_next_item)
                sorted_steps_stack.extend(steps_stack)
            else:
                print(f"condition {diagram_item} true next item is none")

            this_step, step_words = StepStub(sname=EnumStubName.Else).gen_step(this_step)
            sorted_steps_stack.append(step_words)

            false_next_item = diagram_item.get_next_diagram_item(False)
            if false_next_item:
                this_step, steps_stack = self.get_next_item_steps(this_step, worksettings, false_next_item)
                sorted_steps_stack.extend(steps_stack)
            else:
                print(f"condition {diagram_item} false next item is none")
        else:
            next_item = diagram_item.get_next_diagram_item()
            if next_item:
                this_step, steps_stack = self.get_next_item_steps(this_step, worksettings, next_item)
                sorted_steps_stack.extend(steps_stack)
            else:
                print(f"{diagram_item} next item is none")

        # need end stub steps
        if step.type in EnumStepType.need_end_step_stub_type_keys():
            if step.type == EnumStepType.CheckCondition.type_key():
                this_step, step_words = StepStub(sname=EnumStubName.EndCondition).gen_step(this_step)
                sorted_steps_stack.append(step_words)
            elif step.type == EnumStepType.Repeat.type_key():
                this_step, step_words = StepStub(sname=EnumStubName.EndLoop).gen_step(this_step)
                sorted_steps_stack.append(step_words)
            elif step.type == EnumStepType.CallFunction.type_key():
                this_step, step_words = StepStub(sname=EnumStubName.EndFunction).gen_step(this_step)
                sorted_steps_stack.append(step_words)
            elif step.type == EnumStepType.Stub.type_key():
                if step.stub_name == EnumStubName.StartSkill or step.stub_name == EnumStubName.StartSkillMain:
                    this_step, step_words = StepStub(sname=EnumStubName.EndSkill).gen_step(this_step)
                    sorted_steps_stack.append(step_words)

        # print(this_step, sorted_steps_stack)
        return this_step, sorted_steps_stack

# SkFCSkd().gen_psk_file(skd_file, psk_file_dir)


class StepItems:
    def __init__(self):
        self.steps = []
        self.step_map = {}

    def add_step(self, step: StepBase, key: str):
        if key in self.step_map:
            raise ValueError(f"Key '{key}' already exists in the collection.")

        self.steps.append(step)
        self.step_map[key] = step

    def get_step_by_key(self, key: str) -> StepBase:
        if key not in self.step_map:
            raise KeyError(f"Key '{key}' not found in the collection.")

        return self.step_map[key]

    def __len__(self):
        return len(self.steps)

    def __iter__(self):
        return iter(self.steps)


# class StepQueue:
#     def __init__(self):
#         super().__init__()
#         self.queue = []
#
#     def enqueue(self, step: StepBase):
#         self.queue.append(step)
#
#     def dequeue(self):
#         if len(self.queue) < 1:
#             return None
#         return self.queue.pop(0)
#
#     def size(self):
#         return len(self.queue)
#
#     def insert(self, position, step: StepBase):
#         self.queue.insert(position, step)
#
#     def find(self, value):
#         try:
#             position = self.queue.index(value)
#             return position
#         except ValueError:
#             return -1
