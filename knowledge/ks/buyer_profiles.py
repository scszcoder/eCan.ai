"""用户画像: what a buyer has said about the person the item is for -- who
(themselves, a daughter, a gift), age, height, size, budget, occasion, likes --
built up as the chat goes on, so a recommendation or size answer can use what
was said turns ago (the Q&A turn only carries the last few messages).

The end user is often not the buyer (a gift, a child), and one buyer can shop
for several people, so a buyer has one profile per recipient; the last one
mentioned is current.

Read by rules from each buyer message: no model call, nothing added to the
reply time. Kept only on this PC, one JSON file per store, and a buyer not
heard from in RETAIN_DAYS is dropped. Only what helps recommend is kept, plus
the buyer's chat nickname so the owner can tell buyers apart (no phone,
address or anything else). The store owner can see,
correct and delete profiles (商品知识 -> 顾客画像); a field the owner set is
never overwritten by what the rules read later.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

RETAIN_DAYS = 30
MAX_PREFS = 6
# One lock for every instance: the service makes a new BuyerProfiles per call,
# and two buyers' turns in one store write the same file.
_LOCK = threading.Lock()

# (word in the message, recipient label, gender it implies)
_WHO: List[Tuple[str, str, str]] = [
    ("女儿", "女儿", "女"), ("闺女", "女儿", "女"), ("儿子", "儿子", "男"),
    ("女宝", "宝宝", "女"), ("男宝", "宝宝", "男"), ("宝宝", "宝宝", ""), ("孩子", "孩子", ""), ("小孩", "孩子", ""),
    ("老公", "老公", "男"), ("老婆", "老婆", "女"), ("男朋友", "男朋友", "男"), ("女朋友", "女朋友", "女"),
    ("妈妈", "妈妈", "女"), ("我妈", "妈妈", "女"), ("爸爸", "爸爸", "男"), ("我爸", "爸爸", "男"),
    ("父母", "父母", ""), ("老人", "老人", ""), ("朋友", "朋友", ""), ("同事", "同事", ""),
    ("侄子", "侄子", "男"), ("侄女", "侄女", "女"), ("外甥女", "外甥女", "女"), ("外甥", "外甥", "男"),
    ("孙子", "孙子", "男"), ("孙女", "孙女", "女"),
    ("我自己", "自己", ""), ("自己穿", "自己", ""), ("自己用", "自己", ""),
]
_GIFT = ("送人", "送礼", "礼物", "送给")
_GENDER = (("男孩", "男"), ("男童", "男"), ("男生", "男"), ("女孩", "女"), ("女童", "女"), ("女生", "女"))
_OCCASIONS = ("生日", "开学", "上学", "幼儿园", "过年", "春节", "旅游", "运动", "跑步", "婚礼", "毕业", "上班",
              "夏天", "冬天", "春秋")
_PREFS = ("粉色", "红色", "蓝色", "黑色", "白色", "灰色", "绿色", "黄色", "紫色", "卡其", "纯棉", "宽松", "修身",
          "加绒", "薄款", "厚款", "防晒", "透气", "可爱", "简约", "运动风", "休闲")

_AGE = re.compile(r"(\d{1,2})\s*(?:周岁|岁)")
_MONTHS = re.compile(r"(\d{1,2})\s*个月")
# About the person, not the product: "身高120" / "120高", never "裤长90cm";
# "穿M码", never "这件M码有吗"; "体重50斤", never "10斤装".
_HEIGHT = re.compile(r"(?:身高|个子)\s*(\d{2,3})|(\d{2,3})\s*(?:cm|厘米|公分)?\s*(?:高|的个子)", re.I)
_HEIGHT_M = re.compile(r"(?:身高|个子)\s*([12])\s*米\s*(\d{0,2})|([12])\s*米\s*(\d{1,2})\s*(?:高|的个子)")
_WEIGHT = re.compile(r"(\d{2,3}(?:\.\d)?)\s*(斤|kg|公斤|千克)(?!装)", re.I)
_SIZE = re.compile(r"穿\s*(X{0,3}S|M|X{0,4}L|\dXL|\d{3})\s*码?(?![A-Za-z])", re.I)
_BUDGET = re.compile(r"预算\s*(\d{2,5})|(\d{2,5})\s*(?:元|块)\s*(以内|以下|之内|左右)|(\d{2,5})\s*(以内|以下|之内)")

FIELDS = ("gender", "age", "height", "weight", "size", "budget", "occasion", "prefs")
FIELD_LABELS = {"gender": "性别", "age": "年龄", "height": "身高", "weight": "体重", "size": "尺码",
                "budget": "预算", "occasion": "场合", "prefs": "偏好"}


def read_message(text: str) -> Tuple[str, Dict[str, Any], bool]:
    """(recipient named in *text* or "", fields read from it, is a gift)."""
    t = str(text or "")
    who, fields = "", {}
    for word, label, gender in _WHO:
        if word in t:
            who = label
            if gender:
                fields["gender"] = gender
            break
    for word, gender in _GENDER:
        if word in t:
            fields.setdefault("gender", gender)
            break
    m = _AGE.search(t)
    if m and 0 < int(m.group(1)) < 100:
        fields["age"] = f"{int(m.group(1))}岁"
    else:
        m = _MONTHS.search(t)
        if m and 0 < int(m.group(1)) <= 36:
            fields["age"] = f"{int(m.group(1))}个月"
    m = _HEIGHT_M.search(t)
    if m:
        metres, rest = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        fields["height"] = f"{int(metres) * 100 + int((rest or '0').ljust(2, '0'))}cm"
    else:
        m = _HEIGHT.search(t)
        cm = int(m.group(1) or m.group(2)) if m else 0
        if 45 <= cm <= 210:
            fields["height"] = f"{cm}cm"
    m = _WEIGHT.search(t)
    if m:
        fields["weight"] = f"{m.group(1)}{m.group(2)}"
    m = _SIZE.search(t)
    if m:
        fields["size"] = m.group(1).upper()
    m = _BUDGET.search(t)
    if m:
        if m.group(1):
            fields["budget"] = f"{m.group(1)}元以内"
        elif m.group(2):
            fields["budget"] = f"{m.group(2)}元{m.group(3)}"
        else:
            fields["budget"] = f"{m.group(4)}元{m.group(5)}"
    occasions = [o for o in _OCCASIONS if o in t]
    if occasions:
        fields["occasion"] = "、".join(occasions[:2])
    prefs = [p for p in _PREFS if p in t]
    if prefs:
        fields["prefs"] = prefs
    return who, fields, any(g in t for g in _GIFT)


def _safe_name(store_id: str) -> str:
    safe = "".join(c for c in str(store_id or "") if c.isalnum() or c in "-_.")
    return safe or "_"


class BuyerProfiles:
    def __init__(self, folder: str):
        self.folder = os.path.join(folder, "buyer_profiles")

    def _path(self, store_id: str) -> str:
        return os.path.join(self.folder, f"{_safe_name(store_id)}.json")

    def _load(self, store_id: str) -> Dict[str, Any]:
        try:
            with open(self._path(store_id), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        cutoff = time.time() - RETAIN_DAYS * 86400
        return {k: v for k, v in data.items() if isinstance(v, dict) and float(v.get("last_contact") or 0) >= cutoff}

    def _save(self, store_id: str, data: Dict[str, Any]) -> None:
        os.makedirs(self.folder, exist_ok=True)
        dest = self._path(store_id)
        tmp = dest + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, dest)

    def note(self, store_id: str, customer_id: str, text: str, display_name: str = "",
             save: bool = True) -> Optional[Dict[str, Any]]:
        """Read one buyer message into the buyer's profile; the profile after it
        (None without a store or buyer). save=False: work it out, keep nothing."""
        store_id, customer_id = str(store_id or "").strip(), str(customer_id or "").strip()
        if not store_id or not customer_id:
            return None
        who, fields, gift = read_message(text)
        with _LOCK:
            data = self._load(store_id)
            prof = data.get(customer_id) or {"recipients": {}, "current": ""}
            prof["last_contact"] = time.time()
            if display_name:
                prof["name"] = str(display_name)[:40]
            key = who or prof.get("current") or ("送礼" if gift else "")
            if key or fields:
                key = key or "未说明"
                rec = prof["recipients"].setdefault(key, {"fields": {}, "owner_set": []})
                if gift:
                    rec["gift"] = True
                for f, v in fields.items():
                    if f in rec.get("owner_set", []):
                        continue
                    if f == "prefs":
                        v = list(dict.fromkeys(list(rec["fields"].get("prefs") or []) + v))[-MAX_PREFS:]
                    rec["fields"][f] = v
                prof["current"] = key
            data[customer_id] = prof
            if save:
                self._save(store_id, data)
        return prof

    def get(self, store_id: str, customer_id: str) -> Optional[Dict[str, Any]]:
        return self._load(str(store_id or "")).get(str(customer_id or ""))

    def list(self, store_id: str) -> List[Dict[str, Any]]:
        data = self._load(store_id)
        return [{"customer_id": cid, **prof, "summary": describe(prof)}
                for cid, prof in sorted(data.items(), key=lambda kv: -float(kv[1].get("last_contact") or 0))]

    def set_fields(self, store_id: str, customer_id: str, recipient: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        """The owner's correction: these fields win over what the rules read
        later; an empty value removes the field (and the owner's lock on it)."""
        with _LOCK:
            data = self._load(store_id)
            prof = data.get(customer_id)
            if prof is None:
                raise KeyError(customer_id)
            rec = prof["recipients"].setdefault(recipient or "未说明", {"fields": {}, "owner_set": []})
            for f, v in (fields or {}).items():
                if f not in FIELDS:
                    continue
                locked = set(rec.get("owner_set") or [])
                if v in ("", None, []):
                    rec["fields"].pop(f, None)
                    locked.discard(f)
                else:
                    rec["fields"][f] = v
                    locked.add(f)
                rec["owner_set"] = sorted(locked)
            self._save(store_id, data)
            return prof

    def delete(self, store_id: str, customer_id: str, recipient: str = "") -> bool:
        """Forget a buyer (or one of the buyer's recipients)."""
        with _LOCK:
            data = self._load(store_id)
            prof = data.get(customer_id)
            if prof is None:
                return False
            if recipient:
                prof["recipients"].pop(recipient, None)
                if prof.get("current") == recipient:
                    prof["current"] = next(iter(prof["recipients"]), "")
            else:
                data.pop(customer_id)
            self._save(store_id, data)
            return True


def _value(f: str, v: Any) -> str:
    return "、".join(v) if isinstance(v, list) else str(v)


def describe(prof: Dict[str, Any]) -> str:
    recs = prof.get("recipients") or {}
    if not recs:
        return ""
    cur = prof.get("current") or next(iter(recs))
    parts = []
    for name in [cur] + [n for n in recs if n != cur]:
        rec = recs.get(name) or {}
        fl = rec.get("fields") or {}
        body = "，".join(f"{FIELD_LABELS[f]}{_value(f, fl[f])}" if f in ("budget", "occasion", "prefs", "weight")
                        else _value(f, fl[f]) for f in FIELDS if fl.get(f))
        who = "自己用" if name == "自己" else ("对象未说明" if name == "未说明" else f"给{name}买")
        if rec.get("gift") and name != "送礼":
            who += "（送礼）"
        parts.append(who + (f"：{body}" if body else ""))
    head = "[顾客画像]（根据顾客之前说的话整理，推荐和尺码按这个来；不确定就问）"
    return head + " 当前：" + parts[0] + ("；之前还提到：" + "；".join(parts[1:3]) if len(parts) > 1 else "")
