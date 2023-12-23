from PySide6.QtCore import (Signal, Qt, QPointF)
from PySide6.QtGui import QFont, QColor, QPalette

from enum import Enum
import json
from typing import List
import uuid
from typing import Dict


class EnumItemType(Enum):
    Normal = 1
    Text = 2
    Arrow = 3

    @staticmethod
    def enum_name(obj):
        if isinstance(obj, Enum):
            return obj.name
        raise TypeError(f"{obj} is not JSON serializable of EnumItemType")


class DiagramBase:
    @staticmethod
    def build_uuid():
        return str(uuid.uuid4())

    @staticmethod
    def font_weight_to_enum_name(obj):
        if isinstance(obj, QFont.Weight):
            return obj.name
        raise TypeError(f"{obj} is not JSON serializable of QFont Weight")

    @staticmethod
    def enum_name_to_font_weight(name):
        return QFont.Weight[name]

    @staticmethod
    def font_encode(font: QFont) -> dict:
        font_dict = {
            "family": font.family(),
            "pointSize": font.pointSize(),
            "weight": DiagramBase.font_weight_to_enum_name(font.weight()),
            "italic": font.italic(),
            "underline": font.underline(),
            # "strikeOut": font.strikeOut(),
            # "fixedPitch": font.fixedPitch(),
            # "kerning": font.kerning(),
            # "overline": font.overline(),
            # "capitalization": font.capitalization(),
            # "hintingPreference": font.hintingPreference(),
            # "letterSpacingType": font.letterSpacingType(),
            # "letterSpacing": font.letterSpacing(),
            # "wordSpacing": font.wordSpacing(),
        }

        return font_dict

    @staticmethod
    def font_decode(obj_font: dict):
        font = QFont()

        font.setFamily(obj_font["family"])
        font.setPointSize(obj_font["pointSize"])
        font.setWeight(DiagramBase.enum_name_to_font_weight(obj_font["weight"]))
        font.setItalic(obj_font["italic"])
        font.setUnderline(obj_font["underline"])
        return font

    @staticmethod
    def position_encode(position: QPointF) -> dict:
        return {"x": position.x(), "y": position.y()}

    @staticmethod
    def position_decode(position_dict: dict):
        return QPointF(position_dict["x"], position_dict["y"])

    @staticmethod
    def path_points_encode(path_points: List[QPointF]) -> []:
        result = []
        for point in path_points:
            result.append(DiagramBase.position_encode(point))

        # print(f"path_points_encode: {result}")
        return result

    @staticmethod
    def path_points_decode(path_points_dict: []) -> []:
        points: List[QPointF] = []
        for point_dict in path_points_dict:
            points.append(DiagramBase.position_decode(point_dict))

        # print(f"path_points_decode: {points}")
        return points

    @staticmethod
    def color_encode(color: QColor):
        # color_dict = {
        #     "r": color.red(),
        #     "g": color.green(),
        #     "b": color.blue(),
        #     "a": color.alpha()
        # }
        # return color_dict

        color_name = color.name()
        # print(f"encode color name {color_name}")
        return color_name

    @staticmethod
    def color_decode(color_dict: dict) -> QColor:
        # return QColor(color_dict["r"], color_dict["g"], color_dict["b"], color_dict["a"])

        palette = QPalette()
        palette.setColor(QPalette.WindowText, QColor(color_dict))
        color = palette.color(QPalette.WindowText)
        # print(f"decode color {color}")

        return color


