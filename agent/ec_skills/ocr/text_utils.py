import json
import numpy as np


class TXT_DATA:
    def __init__(self, txt, top, left, bottom, right, line, conf):
        super().__init__()
        self.text = txt
        self.box = (top, left, bottom, right)
        self.line = line
        self.confidene = conf


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64, np.float32)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)



class CLICKABLE:
    def __init__(self, cname, txt, left, top, right, bottom, ctype, txtD, scale=1.00):
        super().__init__()
        self.text = txt
        self.box = (left, top, right, bottom, left + int((right - left) / 2), top + int((bottom - top) / 2))
        self.type = ctype
        self.clickable_name = cname
        self.links = []
        self.text_data = txtD
        self.scale = scale
        self.associates = []
        self.indices = [0, 0]

    def set_name(self, item_name):
        self.clickable_name = item_name

    def set_text(self, text):
        self.text = text

    def get_text(self):
        return self.text

    def get_indices(self):
        return self.indices

    def set_type(self, type):
        self.type = type

    def set_scale(self, scale):
        self.scale = scale

    def get_scale(self):
        return self.scale

    def get_type(self):
        return self.type

    def get_contents(self):
        return self.links

    def add_contents(self, ptr):
        self.links.append(ptr)

    def set_contents(self, contents):
        self.links.extend(contents)

    def get_name(self):
        return self.clickable_name

    def get_associates(self):
        return self.associates

    def add_associate(self, anch):
        self.associates.append(anch)

    def set_box(self, left, top, right, bottom):
        self.box = (left, top, right, bottom, int((right - left) / 2), int((bottom - top) / 2))

    def get_box(self):
        return self.box

    def get_box_area(self):
        return (self.box[2] - self.box[0]) * (self.box[3] - self.box[1])

    def get_txt_data(self):
        return self.text_data

    def set_indices(self, indices):
        self.indices = indices

    def toJson(self):
        return {
            "name": self.clickable_name,
            "text": self.text,
            "type": self.type,
            "box": list(self.box),
            "indices": self.indices,
        }

    def toJsonString(self):
        return json.dumps(self.toJson())

    def print(self):
        print("clickable name:", self.clickable_name)
        print("clickable text:", self.text)
        print("clickable type:", self.type)
        print("clickable box:", self.box)
        print("indices:", self.indices)
        print("++++++end of print clickable+++++++++")


class RHT_TAG:
    def __init__(self, id):
        super().__init__()
        self.paragraphs = []
        self.icons = []
        self.imgs = []
        self.id = id
        self.type = "p"

    def add_paragraph(self, para):
        self.paragraphs.append(para)

    def print(self):
        print("==================== Block# " + str(self.number) + "====================")
        if len(self.paragraphs) > 0:
            for p in self.paragraphs:
                p.print()

    def set_box(self, box):
        self.box = box

    def get_paragraphs(self):
        return (self.paragraphs)


class BLOCK:
    def __init__(self, block_num):
        super().__init__()
        self.paragraphs = []
        self.number = block_num
        self.box = []

    def add_paragraph(self, para):
        self.paragraphs.append(para)

    def print(self):
        print("==================== Block# " + str(self.number) + "====================")
        if len(self.paragraphs) > 0:
            for p in self.paragraphs:
                p.print()

    def set_box(self, box):
        self.box = box

    def get_paragraphs(self):
        return (self.paragraphs)

    def remove_dummy_paragraph_at(self, idx):
        self.paragraphs.pop(idx)
        # need to re-adjust geometry box[], but since it's dummy line, maybe nothing needs to be done.


class PARAGRAPH:
    def __init__(self, par_num):
        super().__init__()
        self.lines = []
        self.number = par_num
        self.area = 0
        self.box = (0, 0, 0, 0)
        self.leftmost = 100000
        self.rightmost = 0
        self.topmost = 100000
        self.bottommost = 0
        self.para_text = ""

    def add_line(self, line):
        self.lines.append(line)
        self.para_text = self.para_text + line.get_line_text() + "\n"

        if line.get_top() < self.topmost:
            self.topmost = line.get_top()
        if line.get_bottom() > self.bottommost:
            self.bottommost = line.get_bottom()
        if line.get_left() < self.leftmost:
            self.leftmost = line.get_left()
        if line.get_right() > self.rightmost:
            self.rightmost = line.get_right()
        self.box = (self.leftmost, self.topmost, self.rightmost, self.bottommost)
        self.area = (self.rightmost - self.leftmost) * (self.bottommost - self.topmost)

    def remove_dummy_line_at(self, idx):
        self.lines.pop(idx)
        # need to readjust geometry, as well as words and words indexes, well for dummy line, maybe nothing need to done....

    def set_number(self, par_num):
        self.number = par_num

    def get_number(self):
        return self.number

    def get_box(self):
        return (self.box)

    def get_lines(self):
        return (self.lines)

    def add_line_at(self, loc, line):
        self.lines.insert(loc, line)
        if line.get_top() < self.topmost:
            self.topmost = line.get_top()
        if line.get_bottom() > self.bottommost:
            self.bottommost = line.get_bottom()
        if line.get_left() < self.leftmost:
            self.leftmost = line.get_left()
        if line.get_right() > self.rightmost:
            self.rightmost = line.get_right()
        self.box = (self.leftmost, self.topmost, self.rightmost, self.bottommost)
        self.area = (self.rightmost - self.leftmost) * (self.bottommost - self.topmost)
        # now need to reconstruct paragraph text.
        self.reconstruct_text()

        # print("paragraph add line at", loc)

    def set_line_at(self, loc, line):
        self.lines[loc] = line
        if line.get_top() < self.topmost:
            self.topmost = line.get_top()
        if line.get_bottom() > self.bottommost:
            self.bottommost = line.get_bottom()
        if line.get_left() < self.leftmost:
            self.leftmost = line.get_left()
        if line.get_right() > self.rightmost:
            self.rightmost = line.get_right()
        self.box = (self.leftmost, self.topmost, self.rightmost, self.bottommost)
        self.area = (self.rightmost - self.leftmost) * (self.bottommost - self.topmost)
        self.reconstruct_text()
        # print("paragraph set line at", loc)

    def get_last_line(self):
        return (self.lines[len(self.lines) - 1])

    def get_first_line(self):
        return (self.lines[0])

    def get_para_text(self):
        return (self.para_text)

    def print(self):
        print("++++++++++++++++paragraph# " + str(self.number) + "++++++++++++++++")
        if len(self.lines) > 0:
            print("box[" + str(self.leftmost) + ", " + str(self.topmost) + ", " + str(self.rightmost) + ", " + str(
                self.bottommost) + ", " + "]")
            for l in self.lines:
                l.print()
                l.print_segs()
        print(" -->> end of p# " + str(self.number))

    def reverse_lines(self):
        # reverse the order of the lines.
        self.lines.reverse()
        self.para_text = ""
        for l in self.lines:
            self.para_text = self.para_text + l.get_line_text() + "\n"

    def reconstruct_text(self):
        self.para_text = ""
        for l in self.lines:
            self.para_text = self.para_text + l.get_line_text() + "\n"


class LINE:
    def __init__(self, line_num):
        super().__init__()
        self.line_segs = []
        self.number = line_num
        self.raw_words = []
        self.raw_word_idxs = []  # just for sanity debugging reference, with raw word already includes loc information, this will not be usefull anymore....
        self.top = 100000
        self.bottom = 0
        self.left = 100000
        self.right = 0
        self.line_text = ""
        self.is_seg = False

    def add_line_seg(self, seg):
        self.line_segs.append(seg)

    def get_id(self):
        return (self.number)

    def get_segs(self):
        return (self.line_segs)

    def get_is_seg(self):
        return (self.is_seg)

    def add_word(self, i, word):
        self.raw_words.append(word)
        self.raw_word_idxs.append(i)
        self.line_text = self.line_text + word.get_text() + " "
        # update geometry on this line/line seg.    word loc [left, top, right, bottom]
        # print("add word line text:", self.line_text)
        if word.get_loc()[0] < self.left:
            self.left = word.get_loc()[0]

        if word.get_loc()[2] > self.right:
            self.right = word.get_loc()[2]

        if word.get_loc()[1] < self.top:
            self.top = word.get_loc()[1]

        if word.get_loc()[3] > self.bottom:
            self.bottom = word.get_loc()[3]

    def get_words(self):
        return (self.raw_words)

    def get_word_idxs(self):
        return (self.raw_word_idxs)

    def get_top(self):
        return (self.top)

    def get_bottom(self):
        return (self.bottom)

    def get_line_text(self):
        return (self.line_text)

    def get_number(self):
        return (self.number)

    def set_top(self, intop):
        self.top = intop

    def set_bottom(self, inbottom):
        self.bottom = inbottom

    def get_height(self):
        return (self.bottom - self.top)

    def get_word_loc(idx, raw):
        return (raw["left"], raw["top"], raw["left"] + raw["width"], raw["top"] + raw["height"])

    def set_number(self, line_num):
        self.number = line_num

    def set_left(self, inleft):
        self.left = inleft

    def set_right(self, inright):
        self.right = inright

    def set_words(self, words):
        self.raw_words = words

    def set_word_indices(self, word_indices):
        self.raw_word_idxs = word_indices

    def set_line_text(self, line_txt):
        self.line_text = line_txt

    def get_left(self):
        return self.left

    def get_right(self):
        return self.right

    def get_width(self):
        return (self.right - self.left)

    def get_box(self):
        return (self.left, self.top, self.right, self.bottom)

    def get_idx_by_word(self, word):
        i = self.raw_words.index(word)
        return (self.raw_word_idxs.append(i))

    def append_word_list(self, inseg):
        self.raw_words.extend(inseg.get_words())
        self.raw_word_idxs.extend(inseg.get_word_idxs())
        self.line_text = self.line_text + inseg.get_line_text()
        # print("appended line text:", self.line_text)

        if inseg.get_right() > self.right:
            self.right = inseg.get_right()

        if inseg.get_right() < self.top:
            self.top = inseg.get_top()

        if inseg.get_bottom() > self.bottom:
            self.bottom = inseg.get_bottom()

    def replace_word(self, widx, new_word):
        self.raw_words[widx] = new_word

    def prepend_word_list(self, inseg):
        inwords = inseg.get_words()
        inwords.extend(self.raw_words)
        self.raw_words = inwords
        inwordidxs = inseg.get_word_idxs()
        inwordidxs.extend(self.raw_word_idxs)
        self.raw_word_idxs = inwordidxs

        self.line_text = inseg.get_line_text() + self.line_text
        # print("prepended line text:", self.line_text)

        if inseg.get_left() < self.left:
            self.left = inseg.get_left()

        if inseg.get_right() < self.top:
            self.top = inseg.get_top()

        if inseg.get_bottom() > self.bottom:
            self.bottom = inseg.get_bottom()

    def shrink_to_seg0(self):
        # by definition this method assumes multi-segment on this line, remove segs 1 ... N
        for i in range(1, len(self.line_segs)):
            self.line_segs.pop(1)
        # re-set text
        self.line_text = self.line_segs[0].get_line_text()
        wc = len(self.line_segs[0].get_words())
        # now reset word list and word index list.
        self.raw_words = [j for i, j in enumerate(self.raw_words) if i < wc]
        self.raw_word_idxs = [j for i, j in enumerate(self.raw_word_idxs) if i < wc]
        # now reset geometry
        self.right = self.line_segs[0].get_right()
        self.top = self.line_segs[0].get_top()
        self.bottom = self.line_segs[0].get_bottom()

    def print(self):
        print("line ", str(self.number), ":", self.line_text, " []:", self.get_box())

    def print_segs(self):
        if len(self.line_segs) > 0:
            print("line segssss: ")
            for seg in self.line_segs:
                print(" [", end='')
                print(seg.line_text, end='')
                print("] ", end='')
                print("(L: " + str(seg.get_left()) + " , R: " + str(seg.get_right()) + " , T: " + str(
                    self.top) + " , B: " + str(self.bottom) + " )", end='')
            print("")
        else:
            print("[no seg????]")

    def print_line_and_segs(self):
        # print("..............................................")
        self.print_segs()


class LINE_SEG(LINE):
    def __init__(self, line_num):
        super().__init__(line_num)
        self.icon = False
        self.type = "TEXT"
        self.is_seg = True

    def set_type(self, intype):
        self.type = intype

    def get_type(self, innum):
        return self.type

    def set_number(self, innum):
        self.number = innum

    def print(self):
        print("line seg " + str(self.number) + ":", end='')
        print(" [", end='')
        print(self.line_text, end='')
        print("] ", end='')
        print("(L: " + str(self.get_left()) + " , R: " + str(self.get_right()) + " , T: " + str(
            self.get_top()) + " , B: " + str(self.get_bottom()) + " )", end='')
        print("")


class WORD():
    def __init__(self, word_num, word_txt, word_loc):
        super().__init__()
        self.number = word_num
        self.text = word_txt
        self.loc = word_loc  # [left, top, right, bottom]
        self.left = word_loc[0]
        self.right = word_loc[2]
        self.top = word_loc[1]
        self.bottom = word_loc[3]

    def set_text(self, intxt):
        self.text = intxt

    def set_loc(self, inloc):
        self.loc = inloc
        self.left = inloc[0]
        self.right = inloc[2]
        self.top = inloc[1]
        self.bottom = inloc[3]

    def set_num(self, innum):
        self.number = innum

    def get_text(self):
        return self.text

    def get_loc(self):
        return self.loc

    def get_width(self):
        return (self.right - self.left)

    def get_height(self):
        return (self.bottom - self.top)

    def get_num(self):
        return self.number

    def toJson(self):
        return {
            "number": self.number,
            "text": self.text,
            "loc": self.loc
        }



def info2json(full_info):
    json_full_info = []
    for info in full_info:
        if isinstance(info, dict):
            print("wrong info type>>>>>>:", info)
        box = info.get_box()
        loc = (box[1], box[0], box[3], box[2])

        if info.get_name() == "paragraph":
            txt_struct = []
            for li in info.get_txt_data():
                words = []
                for w in li.get_words():
                    wd = {"num": w.get_num(), "text": w.get_text(), "box": w.get_loc()}
                    words.append(wd)
                l = {"num": li.get_id(), "text": li.get_line_text(), "box": li.get_box(), "words": words}
                txt_struct.append(l)
            newpjson = {"name": info.get_name(), "text": info.get_text(), "loc": loc, "type": info.get_type(),
                        "txt_struct": txt_struct}
        else:
            if info.get_type() == "anchor icon":
                newpjson = {"name": info.get_name(), "text": info.get_text(), "loc": loc, "type": info.get_type(),
                            "scale": info.get_scale()}
            elif "info" in info.get_type():
                print("converting info........")
                associates = []
                for associate in info.get_associates():
                    # the format will be associate anchor name:(box)
                    associates.append({"name": associate.get_name(), "loc": (
                    associate.get_box()[1], associate.get_box()[0], associate.get_box()[3], associate.get_box()[2])})

                if info.get_type() == "info 3":
                    print("converting..... horizontal info line......")
                    li = info.get_txt_data().get_lines()[0]
                    for w in li.get_words():
                        wd = {"num": w.get_num(), "text": w.get_text(), "box": w.get_loc()}
                        words.append(wd)
                    txt_struct = {"num": li.get_id(), "text": li.get_line_text(), "box": li.get_box(), "words": words}

                    newpjson = {"name": info.get_name(), "text": info.get_text(), "loc": loc, "type": info.get_type(),
                                "associates": associates, "txt_struct": txt_struct}
                else:
                    newpjson = {"name": info.get_name(), "text": info.get_text(), "loc": loc, "type": info.get_type(),
                                "associates": associates, "txt_struct": []}
            elif info.get_name() == "swatch":
                newpjson = {"name": info.get_name(), "text": info.get_text(), "loc": loc, "type": info.get_type(),
                            "indices": info.get_indices()}
            else:
                newpjson = {"name": info.get_name(), "text": info.get_text(), "loc": loc, "type": info.get_type()}
        json_full_info.append(newpjson)

    return json_full_info
