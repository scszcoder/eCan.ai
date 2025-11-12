
from agent.mcp.server.utils.auto_utils import mouseClick, mousePressAndHold


# sd - screen data
# target_name
# template text
# target_type
# nth - which target， if multiple are found
def find_clickable_object(sd, target, template, target_type, nth):
    logger.info("LOOKING FOR:"+json.dumps(target)+"   "+json.dumps(template)+"   "+json.dumps(target_type)+"   "+json.dumps(nth))
    found = {"loc": None}
    if target != "paragraph":           # for anchors and info.
        # reg = re.compile(target+"[0-9]+")
        reg = re.compile(rf"^{target}([0-9]*)$")
        targets = [x for x in sd if (x["name"] == target or reg.match(x["name"].split("!")[0])) and x["type"] == target_type]
    else:
        reg = re.compile(template)
        targets = [x for x in sd if template in x["text"] and x["type"] == target_type and x["name"] == target]
    # grab all instances of the target object.

    logger.info("found targets::"+str(len(targets)))
    objs = []

    # convert possible string to integer
    for o in targets:
        if o["name"] == "paragraph":
            lines = [l for l in o["txt_struct"] if (l["text"] == template or re.search(template, l["text"]))]
            logger.info("found lines::"+str(len(lines)))
            if len(lines) > 0:
                for li, l in enumerate(lines):
                    pat_words = template.strip().split()
                    lreg = re.compile(pat_words[0])
                    logger.info("checking line:"+json.dumps(l)+json.dumps(pat_words))
                    start_word = next((x for x in l["words"] if re.search(pat_words[0], x["text"])), None)
                    logger.info("start_word:"+json.dumps(start_word))
                    if start_word:
                        if len(pat_words) > 1:
                            lreg = re.compile(pat_words[len(pat_words)-1])
                            end_word = next((x for x in l["words"] if x["text"] == pat_words[len(pat_words)-1] or lreg.match(x["text"])), None)
                            logger.info("multi word end_word:"+json.dumps(end_word))
                        else:
                            end_word = start_word
                            logger.info("single word")

                        objs.append({"loc": [int(start_word["box"][1]), int(start_word["box"][0]), int(end_word["box"][3]), int(end_word["box"][2])]})
                        logger.info("objs:"+json.dumps(objs))
        else:
            logger.info("non paragraph:"+json.dumps(o))
            o["loc"] = [int(o["loc"][0]), int(o["loc"][1]), int(o["loc"][2]), int(o["loc"][3])]
            objs.append({"loc": o["loc"]})

    logger.info("objs:"+json.dumps(objs))
    if len(objs) > 1:
        # need to organized found objects into rows and cols, then access the nth object.
        xsorted = sorted(objs, key=lambda x: x["loc"][0], reverse=False)
        ysorted = sorted(objs, key=lambda x: x["loc"][1], reverse=False)
        cell_width = int(sum((c["loc"][2] - c["loc"][0]) for c in xsorted) / len(xsorted))
        cell_height = int(sum((c["loc"][3]-c["loc"][1]) for c in ysorted)/len(ysorted))
        #now calculate the row grid and column grid size
        ncols = 1+math.floor((xsorted[len(xsorted)-1]["loc"][0] - xsorted[0]["loc"][0]) / cell_width)
        nrows = 1+math.floor((ysorted[len(ysorted)-1]["loc"][1] - ysorted[0]["loc"][1]) / cell_height)
        # now place objects into their relavant row and colume position.
        my_array = lazy.np.empty([nrows, ncols], dtype=object)
        for ob in ysorted:
            ri = math.floor((ob["loc"][1] - ysorted[0]["loc"][1])/cell_height)
            ci =  math.floor((ob["loc"][0] - xsorted[0]["loc"][0])/cell_width)
            logger.info("Filling in row:"+str(ri)+" col:"+str(ci))
            my_array[ri, ci] = ob

        # now, take out the nth element
        if type(nth) == list:
            if len(nth) == 2:
                if nth[0] >= 0 and nth[1] >= 0:
                    found = my_array[nth[0], nth[1]]
                elif nth[1] >= 0:
                    found = ysorted[nth[1]]
                else:
                    found = xsorted[nth[0]]
            else:
                found = objs[nth[0]]
        elif type(nth) == str:
            # nth is a variable
            if "[" not in nth and "]" not in nth:
                logger.info("nth as a variable name is:"+str(symTab[nth]))
                found = objs[symTab[nth]]
                logger.info("found object:"+json.dumps(found))
        elif type(nth) == int:
            logger.info("nth as an integer is:"+str(nth))
            found = objs[nth]
        # the code is incomplete at the moment....
    elif len(objs) == 1:
        found = objs[0]

    return found["loc"]

def get_clickable_loc(box, off_from, offset, offset_unit):
    logger.info("get_clickable_loc: "+json.dumps(box)+" :: "+json.dumps(off_from)+" :: "+json.dumps(offset)+" :: "+offset_unit)
    center = box_center(box)
    if offset_unit == "box":
        box_length = box[3] - box[1]
        box_height = box[2] - box[0]
    else:
        box_length = 1
        box_height = 1

    if off_from == "left":
        click_loc = (box[1] - int(offset[0]*box_length), center[0]+int(offset[1]*box_height))
    elif off_from == "right":
        click_loc = (box[3] + int(offset[0]*box_length), center[0]+int(offset[1]*box_height))
    elif off_from == "top":
        click_loc = (center[1] + int(offset[0]*box_length), box[0] - int(offset[1]*box_height))
    elif off_from == "bottom":
        click_loc = (center[1] + int(offset[0]*box_length), box[2] + int(offset[1]*box_height))
    else:
        #offset from center case
        logger.info("CENTER: "+json.dumps(center)+"OFFSET:"+json.dumps(offset))
        click_loc = ((center[1] + int(offset[0]*box_length), center[0] + int(offset[1]*box_height)))

    return click_loc


# sd is the screen data, word is the word to be press and hold on.
def mousePressAndHoldOnScreenWord(sd, word, duration= 12, nth=0):
    # find the word,
    obj_box = find_clickable_object(sd, "paragraph", word, "info", 0)
    if obj_box:
        loc = get_clickable_loc(obj_box, "center", [0, 0], "box")
        if duration:
            mousePressAndHold(loc, duration)
        else:
            mouseClick(loc)