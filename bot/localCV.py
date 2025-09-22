import pytesseract
from pytesseract import Output
import os
import imutils
from PIL import Image
from datetime import datetime
import asyncio
from textUtils import CLICKABLE, BLOCK, PARAGRAPH, LINE, WORD
from concurrent.futures import ProcessPoolExecutor
import json
from utils.lazy_import import lazy
from utils.logger_helper import get_traceback
from utils.logger_helper import logger_helper as logger


class PythonObjectEncoder(json.JSONEncoder):
    """Custom JSON Encoder that allows encoding of un-serializable objects
    For object types which the json module cannot natively serialize, if the
    object type has a __repr__ method, serialize that string instead.
    Usage:
        >>> example_unserializable_object = {'example': set([1,2,3])}
        >>> print(json.dumps(example_unserializable_object,
                             cls=PythonObjectEncoder))
        {"example": "set([1, 2, 3])"}
    """

    def default(self, obj):
        if isinstance(obj, (list, dict, str, int, float, bool, type(None))):
            return json.JSONEncoder.default(self, obj)
        elif hasattr(obj, '__repr__'):
            return obj.__repr__()
        else:
            return json.JSONEncoder.default(self, obj.__repr__())


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, lazy.np.integer):
            return int(obj)
        if isinstance(obj, lazy.np.floating):
            return float(obj)
        if isinstance(obj, lazy.np.ndarray):
            return obj.tolist()
        return super(NumpyEncoder, self).default(obj)

cpu_nums = os.cpu_count()
icon_match_executor = ProcessPoolExecutor(max_workers=cpu_nums)  # Optimize based on CPU cores

def cleanup_executor():
    """清理进程池执行器"""
    global icon_match_executor
    if icon_match_executor:
        icon_match_executor.shutdown(wait=True)
        icon_match_executor = None

# 注册清理函数
import atexit
atexit.register(cleanup_executor)

def remove_duplicates(dicts, threshold=10):
    """
    Remove coordinates that are very close to each other, prioritizing lower score entries.

    Args:
    - dicts: List of dictionaries, each containing a 'score' and 'locations'.
    - threshold: Distance threshold for considering coordinates as the same.

    Returns:
    - List of dictionaries with filtered coordinates.
    """

    def is_too_close(coord1, coord2):
        return abs(coord1[0] - coord2[0]) <= threshold and abs(coord1[1] - coord2[1]) <= threshold

    # Sort the dictionaries by score in descending order
    dicts.sort(key=lambda x: x['score'], reverse=True)

    result = []

    # Dictionary to keep track of added coordinates to avoid duplicates
    added_coords = []

    for entry in dicts:
        filtered_locations = []
        for coord in entry['locs']:
            if not any(is_too_close(coord, added_coord) for added_coord in added_coords):
                filtered_locations.append(coord)
                added_coords.append(coord)

        if filtered_locations:
            for loc in filtered_locations:
                box = [loc[0], loc[1], loc[0] + entry['shape'][1], loc[1] + entry['shape'][0]]
                result.append({'name': entry['name'], 'type': 'anchor icon', 'text': '', 'text_data': '',
                               'score': format(entry['score'], '.2f'), 'scale': format(entry['scale'], '.2f'),
                               'box': box})

    return result


def img_has_match(result, thresh):
    found_match = False
    (ys, xs) = lazy.np.where(result >= thresh)

    if len(xs) > 0 and len(ys) > 0:
        found_match = True

    return found_match


# SC note: - CCORR is the fastest, but not as accurate.
def match_icon(data):
    import cv2
    image, template = data
    # return cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
    # return cv2.matchTemplate(image, template, cv2.TM_CCOEFF)
    # return cv2.matchTemplate(image, template, cv2.TM_SQDIFF)
    # return cv2.matchTemplate(image, template, cv2.TM_SQDIFF_NORMED)
    # return cv2.matchTemplate(image, template, cv2.TM_CCORR)
    return cv2.matchTemplate(image, template, cv2.TM_CCORR_NORMED)


# find a specific kind of icon in an image
# iconFile: icon template file
# targetFile: file to be searched.
# multi-scale search of the icon with the image.
# SC 2023-07-06, currently run takes ~4 seconds, which is extremely expensive.
#                1) so idea is to memorized successfully scale factor for each computer.... so that later runs will be done once only.
#                2) really we need to match minimum icons, we should use text as much as possible.....
# def match_template(aname, iconFile, targetImage, factor, log=False):
# def match_template(aname, icon, targetImage, factor, log=False):
def match_template(aname, icon, targetImage, factor, logger):
    import cv2
    # aname, icon, targetImage, factor = mt_input
    # global logger
    logger.debug("matching icon: " + aname + "....")

    match_results = []
    outData = {"level": [], "page_num": [], "block_num": [], "par_num": [], "line_num": [], "word_num": [], "left": [],
               "top": [], "width": [], "height": [], "conf": [], "text": []}
    # filewords = os.path.basename(iconFile).split(".")
    # iconName = filewords[0]
    # iconText="(ICON)" + iconName
    # print("matching... ", iconFile)
    # img1 = cv2.imread(iconFile)  # queryImage
    img1 = icon
    # img2 = cv2.imread(targetFile)  # trainImage

    # template = img1
    template = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)

    # blurredT = cv2.GaussianBlur(template, (7, 7), 0)
    # _, threshT = cv2.threshold(blurredT, 0.0, 255.0, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    # template = threshT

    # template = cv2.Canny(template, 50, 200)
    (tH, tW) = template.shape[:2]
    logger.debug("icon dimension tH: " + str(tH) + " tW: " + str(tW))

    # loop over the images to find the template in
    # for imagePath in glob.glob(args["images"] + "/*.jpg"):

    # load the image, convert it to grayscale, and initialize the
    # bookkeeping variable to keep track of the matched region

    # gray = img2
    logger.debug("base image dimension::" + json.dumps(targetImage.shape))
    gray = cv2.cvtColor(targetImage, cv2.COLOR_BGR2GRAY)
    # edged = cv2.Canny(gray, 50, 200)
    edged = gray
    # blurred = cv2.GaussianBlur(gray, (7, 7), 0)
    # #thresh = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 21, 10)
    # #_, thresh = cv2.threshold(blurred, 0.0, 255.0, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    # thresh = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 4)
    # gray = thresh

    found = None
    bestResult = None
    (bestH, bestW) = (0, 0)
    # loop over the scales of the image
    if factor.get(aname) == None:
        if factor.get('all') == None:
            search_space = lazy.np.linspace(0.6, 1.5, 12)[::-1]
        elif len(factor.get('all')) == 1:
            if factor['all'][0] == 0.0:
                search_space = lazy.np.linspace(0.6, 1.5, 12)[::-1]
            else:
                search_space = factor['all']
        else:
            search_space = factor['all']
    else:
        search_space = factor[aname]

    logger.debug("search scales::" + str(len(search_space)))

    try:
        allresults = []
        resizedTemplates = []

        for scale in search_space:
            # resize the image according to the scale, and keep track
            # of the ratio of the resizing
            # resized = imutils.resize(gray, width=int(gray.shape[1] * scale))
            resized = imutils.resize(template, width=int(template.shape[1] * scale))

            # blurredT = cv2.GaussianBlur(resized, (7, 7), 0)
            # _, threshT = cv2.threshold(blurredT, 0.0, 255.0, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
            # resized = threshT

            # r = gray.shape[1] / float(resized.shape[1])
            r = template.shape[1] / float(resized.shape[1])
            # if the resized image is smaller than the template, then break
            # from the loop
            # if resized.shape[0] < tH or resized.shape[1] < tW:
            #    break

            # detect edges in the resized, grayscale image and apply template
            # matching to find the template in the image
            # edged = cv2.Canny(resized, 50, 200)
            # resizedEdged = cv2.Canny(resized, 50, 200)
            resizedEdged = resized
            resizedTemplates.append(resizedEdged)

            # edged = resized
            # edged = gray
            # result = cv2.matchTemplate(edged, template, cv2.TM_CCOEFF)

            result = cv2.matchTemplate(edged, resizedEdged, cv2.TM_CCOEFF_NORMED)

            # print(result)
            # print("hello???")

            # with NonDaemonPool(processes=4) as apool:
            # results = apool.map(match_icon, [(edged, icon) for icon in resizedTemplates])

            # for result in results:
            (_, maxVal, _, maxLoc) = cv2.minMaxLoc(result)

            clone = edged.copy()

            # for (x, y) in zip(xCoords, yCoords):
            #     # draw the bounding box on the image
            #     cv2.rectangle(clone, (x, y), (x + tW, y + tH),
            #                   (255, 0, 0), 3)
            #

            # log0("found "+str(maxVal)+"::"+json.dumps(maxLoc)+"::"+str(r)+"::"+str(scale))

            # check to see if the iteration should be visualized
            # if log:
            #     # draw a bounding box around the detected region
            #     clone = np.dstack([edged, edged, edged])
            #
            #     cv2.rectangle(clone, (maxLoc[0], maxLoc[1]),
            #                   (maxLoc[0] + tW, maxLoc[1] + tH), (0, 0, 255), 2)

            # if we have found a new maximum correlation value, then update
            # the bookkeeping variable
            if found is None or maxVal > found[0]:
                found = (maxVal, maxLoc, r)
                best_scale = scale
                bestResult = result
                (bestH, bestW) = resized.shape[:2]

            allresults.append((r, maxVal, maxLoc, scale, result, resized.shape[:2], clone))
            print("done with 1 round.....")

        # sort all results by maxVal min to max
        sorted_results = sorted(allresults, key=lambda c: c[1])

        qualified_results = [e for e in sorted_results if img_has_match(e[4], 0.5)]
        # log0("found # of qualified: "+json.dumps(qualified_results))

        matched_effectives = []
        for matched_result in sorted_results:
            # unpack the bookkeeping variable and compute the (x, y) coordinates
            # of the bounding box based on the resized ratio
            (maxVal, maxLoc, r) = (matched_result[1], matched_result[2], matched_result[0])
            # print("found best", maxVal, "::", maxLoc, "::", r)

            (bestW, bestH) = matched_result[5]

            (yCoords, xCoords) = lazy.np.where(matched_result[4] >= 0.85)
            # print(len(xCoords))
            # print(len(yCoords))
            clone = cv2.cvtColor(matched_result[6], cv2.COLOR_GRAY2BGR)
            # zip() converts iterables into tuple.
            for (x, y) in zip(xCoords, yCoords):
                # draw the bounding box on the image
                cv2.rectangle(clone, (x, y), (x + bestW, y + bestH), (255, 0, 0), 3)

            (startX, startY) = (int(maxLoc[0] * r), int(maxLoc[1] * r))
            (endX, endY) = (int((maxLoc[0] + tW) * r), int((maxLoc[1] + tH) * r))
            # draw a bounding box around the detected result and display the image

            cv2.rectangle(targetImage, (startX, startY), (endX, endY), (0, 0, 255), 2)

            wi = 0
            li = 0
            xyCoords = zip(xCoords, yCoords)
            sorted_xyCoords = sorted(xyCoords, key=lambda c: c[1])
            # log0("sorted xy coords:"+sorted_xyCoords)

            # now need to do a round of filtering to remove the duplicated results (i.e. pixel location off by within 5 pixel either in x or y direction)
            last_effective_xy = (-100, -100)
            effective = []
            one_row = []
            for (x, y) in sorted_xyCoords:

                if y - last_effective_xy[1] > bestH * 0.5:
                    # print("start a new line")
                    # examine the current row.
                    if len(one_row) > 0:
                        sorted_one_row = sorted(one_row, key=lambda c: c[0])

                        nc = len(sorted_one_row)
                        last_x = -100
                        for i in range(nc):
                            if sorted_one_row[i][0] - last_x > 8:
                                effective.append((sorted_one_row[i][0], sorted_one_row[i][1]))
                                last_effective_xy = (x, y)
                            last_x = sorted_one_row[i][0]
                    # start a new Row, and put current location into the new row.
                    one_row = []
                    one_row.append((x, y))
                    last_effective_xy = (x, y)
                else:
                    # print("add to one row")
                    one_row.append((x, y))

            # process the last row...
            if len(one_row) > 0:
                sorted_one_row = sorted(one_row, key=lambda c: c[0])
                nc = len(sorted_one_row)
                last_x = -100
                for i in range(nc):
                    if sorted_one_row[i][0] - last_x > 8:
                        effective.append((sorted_one_row[i][0], sorted_one_row[i][1]))
                    last_x = sorted_one_row[i][0]

            # log0("after removing duplicates effective:"+json.dumps(effective))

            if len(effective) > 0:
                matched_effectives.append(
                    {"name": aname, "score": matched_result[1], "scale": matched_result[3], "type": "anchor icon",
                     "shape": matched_result[5], "locs": effective})

        # one more round of filtering of potential duplicates....
        logger.debug("effecitves:" + json.dumps(matched_effectives, cls=NumpyEncoder))

        match_results = remove_duplicates(matched_effectives)

    except Exception as e:
        errMsg = get_traceback(e, "ErrorMatchTemplate")
        logger.error(errMsg)

    logger.debug(aname + " match_results:" + json.dumps(match_results, cls=NumpyEncoder))
    return match_results

def loadImg(imageFile):
    import cv2
    if isinstance(imageFile, str):  # If it's a file path, load the image
        img = cv2.imread(imageFile)         # Load target image
    else:
        img = imageFile
    return img

def local_match_template(anames, iconFiles, imageFile, factor, logger):
    """ Perform template matching locally using OpenCV. """
    # logger = LoggerUtil().get_logger()  # Ensure logger is initialized inside worker
    # logger.debug(f"Matching icon: {args[0]}....")
    logger.debug("time stamp4D1: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    print("Performing local template matching anchors...", anames)
    print("imageFile...", imageFile)
    print("iconFiles...", iconFiles)
    print("factor...", factor)
    if isinstance(imageFile, str):
        img = loadImg(imageFile)
    else:
        img = imageFile

    icons = [loadImg(iconFile) for iconFile in iconFiles]  # Load icon templates

    icon_clickables = []
    for aname, icon in zip(anames, icons):
        logger.debug("time stamp4D4: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

        matches = match_template(aname, icon, img, factor, logger)  # Run template matching
        logger.debug("time stamp4D5: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

        for match in matches:
            icon_clickables.append(
                CLICKABLE(
                    match["name"], match["text"], match["box"][0], match["box"][1],
                    match["box"][2], match["box"][3], match["type"], match["text_data"], match["scale"]
                )
            )
    logger.debug("time stamp4D9: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    return icon_clickables

async def local_run_icon_matching(anames, iconFiles, imageFile, factor, logger):
    """ Run local icon matching using OpenCV. """
    print("Starting local ICON MATCH...")
    logger.debug("time stamp4D0: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    loop = asyncio.get_running_loop()
    # result = await loop.run_in_executor(icon_match_executor, local_match_template, anames, iconFiles, imageFile, factor, logger)
    result = local_match_template(anames, iconFiles, imageFile, factor, logger)

    return result

# re-org raw data into block/paragraph/line hierarchy
# ibi is initial block index.
def gen_block_data(raw, logger, wc=0, pi=0, ibi=0):
    box = []
    block_by_idxs = []
    n = len(raw['block_num'])
    # print("there are total of " + str(n) + "blocks")
    block_idxs = BLOCK(ibi)
    block_idx = ibi
    par_idxs = PARAGRAPH(pi)
    par_idx = pi
    line_idxs = LINE(0)
    line_idx = 0
    box_left = raw['left'][0]
    box_top = raw['top'][0]
    box_right = raw['left'][0] + raw['width'][0]
    box_bottom = raw['top'][0] + raw['height'][0]
    logger.debug(f"Initial Index: wc -  {wc}, pi - {pi}, ibi -  {ibi}")
    for i in range(n):
        if raw['text'][i].strip() != "":  # only process this word if usefull
            new_word = WORD(i, raw['text'][i], (
            raw['left'][i], raw['top'][i], (raw['left'][i] + raw['width'][i]), (raw['top'][i] + raw['height'][i])))
            # print("this word:", raw['block_num'][i], raw['par_num'][i], raw['line_num'][i])
            if raw['block_num'][i] == block_idx:
                if raw['par_num'][i] == par_idx:
                    if raw['line_num'][i] == line_idx:
                        # print("save word number" + str(i))
                        line_idxs.add_word(wc + i, new_word)
                    else:
                        # print("para ", str(par_idx), " adding line:", line_idx)
                        par_idxs.add_line(line_idxs)
                        # line_idxs.print()

                        line_idx = raw['line_num'][i]
                        # print("now onto line # " + str(line_idx))
                        line_idxs = LINE(line_idx)
                        line_idxs.add_word(wc + i, new_word)

                        # update block bound box data every time we change line.
                        if raw['top'][i] < box_top:
                            box_top = raw['top'][i]

                        if raw['left'][i] < box_left:
                            box_left = raw['left'][i]

                        if raw['left'][i - 1] + raw['width'][i - 1] > box_right:
                            box_right = raw['left'][i - 1] + raw['width'][i - 1]

                        if raw['top'][i - 1] + raw['height'][i - 1] > box_right:
                            box_right = raw['top'][i - 1] + raw['height'][i - 1]

                else:
                    # print("para ", str(par_idx), " adding line:", line_idx)
                    par_idxs.add_line(line_idxs)
                    # par_idxs.print()
                    # print("blk ", str(block_idx), " adding para:", par_idx)
                    block_idxs.add_paragraph(par_idxs)

                    par_idx = raw['par_num'][i]
                    par_idxs = PARAGRAPH(par_idx)
                    # print("new paragraph now " + str(par_idx))

                    line_idx = 0
                    line_idxs = LINE(line_idx)
                    line_idxs.add_word(wc + i, new_word)

            else:
                if i > 0:
                    # finish the current block..
                    # print("para ", str(par_idx), " adding line:", line_idx)
                    par_idxs.add_line(line_idxs)
                    # print("blk ", str(block_idx), " adding para:", par_idx)
                    block_idxs.add_paragraph(par_idxs)

                    if raw['left'][i - 1] + raw['width'][i - 1] > box_right:
                        box_right = raw['left'][i - 1] + raw['width'][i - 1]

                    if raw['top'][i - 1] + raw['height'][i - 1] > box_right:
                        box_right = raw['top'][i - 1] + raw['height'][i - 1]

                    box = [box_left, box_top, box_right, box_bottom]
                    block_idxs.set_box(box)
                    block_by_idxs.append(block_idxs)
                    # print("blk size2: " + str(len(block_by_idxs)))

                # start a new bound box for the new block.
                box_left = raw['left'][i]
                box_top = raw['top'][i]
                box_right = raw['left'][i] + raw['width'][i]
                box_bottom = raw['top'][i] + raw['height'][i]

                block_idx = raw['block_num'][i]
                block_idxs = BLOCK(block_idx)

                par_idx = 0
                par_idxs = PARAGRAPH(par_idx)

                line_idx = 0
                line_idxs = LINE(line_idx)
                line_idxs.add_word(wc + i, new_word)
                # print("start new block")

    # process the last block.
    # print("para ", str(par_idx), " adding line:", line_idx)
    par_idxs.add_line(line_idxs)
    # print("blk ", str(block_idx), " adding para:", par_idx)
    block_idxs.add_paragraph(par_idxs)

    if raw['left'][i - 1] + raw['width'][i - 1] > box_right:
        box_right = raw['left'][i - 1] + raw['width'][i - 1]

    if raw['top'][i - 1] + raw['height'][i - 1] > box_right:
        box_right = raw['top'][i - 1] + raw['height'][i - 1]

    box = [box_left, box_top, box_right, box_bottom]
    block_idxs.set_box(box)

    block_by_idxs.append(block_idxs)

    return block_by_idxs

# get rid of all empty space junk entries from the tesseract output.
def remove_junks(txt_info):
    non_junk_indices = [i for i in range(len(txt_info['text'])) if txt_info['text'][i].strip() != ""]
    for k in list(txt_info.keys()):
        txt_info[k] = [item for j, item in enumerate(txt_info[k]) if j in non_junk_indices]


def is_dark_mode(img, logger, threshold=0.75):
    """
    Determine if an image is in dark mode.

    Parameters:
    - image_path: Path to the image.
    - threshold: Fraction of pixels that need to be dark to consider the image in dark mode.

    Returns:
    - True if in dark mode, False otherwise.
    """

    # Read the image
    # img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)

    # Check if the image is valid
    # if img is None:
    #     raise ValueError("Invalid image path")

    # Compute the fraction of dark pixels. A pixel is considered 'dark' if its grayscale value is less than 128.
    dark_fraction = lazy.np.sum(img < 128) / (img.shape[0] * img.shape[1])
    logger.debug(f"dark_fraction: {dark_fraction}")

    return dark_fraction > threshold


def print_block_data(raw, blk_by_idxs):
    n = len(blk_by_idxs)
    print("blk size: " + str(n))
    for i in range(n):
        # print the block
        blk_by_idxs[i].print()


# this is very useful for images with low contrast: light colored text on light colord background, or dark colored text on dark colored background.
def enhance(img):
    import cv2
    # print("img:", img)

    im = img.astype(lazy.np.float32)
    im = im / 255  # rescale
    im = 1 - im  # inversion. ink is the signal, white paper isn't

    # some "sensor noise" for demo, if you want to look at intermediate results
    # im += lazy.np.random.normal(0.0, 0.02, size=im.shape)

    # squares/rectangles
    # morph_kernel = cv.getStructuringElement(shape=cv.MORPH_RECT, ksize=(5,5))
    morph_kernel = lazy.np.ones((5, 5))

    # opencv's ellipses are ugly as sin
    # alternative:
    # import skimage.morphology
    # morph_kernel = skimage.morphology.octagon(5,2)

    # estimates intensity of text
    dilated = cv2.dilate(im, kernel=morph_kernel, iterations=1)
    eroded = cv2.erode(dilated, kernel=morph_kernel, iterations=1)

    # tweak this threshold to catch faint text but not background
    # textmask = (dilated >= 0.15)
    textmask = (eroded >= 0.15)
    # 0.05 catches background noise of 0.02
    # 0.25 loses some text

    # rescale text pixel intensities
    # this will obviously magnify noise around faint text
    # enhanced = im /
    # print("eroded:", eroded)
    # enhanced = im / eroded
    enhanced = lazy.np.where(eroded > 0, im / eroded, im)

    # copy unmodified background back in
    # (division magnified noise on background)
    enhanced[~textmask] = im[~textmask]

    # invert again for output
    output = 1 - enhanced
    outimg = Image.fromarray((output * 255.0).astype(lazy.np.uint8))

    return outimg

def check_dummy_line(line):
    dummyl = True

    number_indexes = [i for i, x in enumerate(line.get_words()) if x.get_text() and not x.get_text().isspace()]
    if len(number_indexes) > 0:
        dummyl = False

    return dummyl


def flatten_lines(blk_data, logger):
    lines = []
    processed = 0
    for blk in blk_data:
        if len(blk.get_paragraphs()) > 0:
            for p in blk.get_paragraphs():
                if len(p.get_lines()) > 0:
                    for l in p.get_lines():
                        processed = processed + 1
                        if check_dummy_line(l) == False:
                            lines.append(l)
    logger.debug("lines processed: " + str(processed) + ", dummy lines filtered out: " + str(processed - len(lines)))
    return lines


# divide line into line segments separated by predefined inter-word space gap
def segmentize_line(line, logger, gap_factor=3):
    # print("SEGMENTIZING ", line.get_line_text())
    words = line.get_words()
    word_idxs = line.get_word_idxs()
    n = len(words)
    seg_idx = 0
    seg = LINE(seg_idx)
    last_loc = words[0].get_loc()[0]
    new_lines = []

    n_chars = sum([len(w.get_text()) for w in words])
    # print("word chars:", n_chars, [len(w.get_text()) for w in words])

    all_word_width = sum([w.get_width() for w in words])
    # print("word widths:", all_word_width, [w.get_width() for w in words])
    char_width = int(all_word_width / n_chars)
    word_gap = char_width * gap_factor
    # print("word gap:", char_width, gap_factor, word_gap)
    logger.debug("-------working on a line ----------<<"+line.get_line_text()+">>")
    for i in range(n):
        if words[i].get_text() and not words[i].get_text().isspace():
            # if the word is NOT dummy (i.e. empty string or space string), if dummy, then simply do nothing and skip over it.
            # char_width = (words[i].get_loc()[2] - words[i].get_loc()[0]) / len(words[i].get_text())  # string width / # of char is single char width
            this_loc = words[i].get_loc()[0]
            # print("char width: " + str(char_width),  end = '')
            # if i > 0:
            #     print("this word:", words[i].get_text(), "this loc:", words[i].get_loc(), "last word:", words[i-1].get_text(), "last loc:", words[i-1].get_loc())
            # else:
            #     print("this word:", words[i].get_text(), "this loc:", words[i].get_loc(), "last word: None", "last loc:", "None")
            if this_loc - last_loc <= word_gap:
                # print(", close to the previous " + str(last_loc), end='')
                if len(seg.get_words()) > 0 and seg_idx == 0:
                    # set left boundry for the very first effective word segment.
                    seg_idx = word_idxs[i]
                    seg.set_number(seg_idx)
                # this word is within proxity of the previous word. then add the word the current segment.
                # print("add word to segment....")
                seg.add_word(word_idxs[i], words[i])

            else:
                # print(", too far from previous " + str(last_loc), end='')
                # we're starting a new segment now., first add the current segment to the line,
                # then start a new segment and add this word to the new segment.
                if len(seg.get_words()) > 0:
                    # deal with the special situation of a bunch of leading dummy char on a line before the 1st actual word.
                    new_lines.append(seg)

                    # line.add_line_seg(seg)
                    # print("add the segment into the line[", seg.get_line_text(), "] to [", line.get_line_text(), "]")
                    # print("seg bound:[" + str(seg.get_left()) + ", " + str(seg.get_right()) + "] " + "top: " + str(seg.get_top()) + " bottom: " + str(seg.get_bottom()))
                # print("start a new seg.....")
                seg_idx = word_idxs[i]
                seg = LINE(seg_idx)
                seg.add_word(word_idxs[i], words[i])

            # now update the last location.
            last_loc = words[i].get_loc()[2]
            # print("update last loc, top, bottom....."+ str(last_loc) + " " + str(line.get_top()) + " " + str(line.get_bottom()))
        # else:
        #     print("dummy word......")
    # at the end of the line, add the last segment.
    # print("seg bound:[" + str(seg.get_left()) + ", " + str(seg.get_right()) + "] ")
    new_lines.append(seg)
    # line.add_line_seg(seg)
    logger.debug(f"segmented into {len(new_lines)} lines.....")
    for nl in new_lines:
        nl.print()
    logger.debug("vvvvvvvvvvvvvvvvvvvv line add segment vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv")

    return new_lines


def segmentize_lines(lines, logger):
    split_lines = []
    for line in lines:
        if len(line.get_words()) > 0:
            line_segs = segmentize_line(line, logger,2)
            split_lines = split_lines + line_segs

    return split_lines


# input: image bytes
# output: a list of top-bottom left to right sorted LINEs data structure, one can search thru.
async def image2text_lines(img):
    import cv2
    img = loadImg(img)

    imgShape = img.shape
    rawImageDimension = (img.shape[1], img.shape[0])
    # set up scaling, eventhought this is not used in this particular algorithm.
    wscale_percent = 100  # percent of original size
    hscale_percent = 100
    width = int(img.shape[1] * wscale_percent / 100)
    height = int(img.shape[0] * hscale_percent / 100)
    dim = (width, height)

    # resize/scale the image
    resized = cv2.resize(img, dim, interpolation=cv2.INTER_AREA)

    # convert color image to gray image.
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

    logger.debug("pong pong pong????")
    logger.debug("time stamp3A: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    # inv_img = cv2.bitwise_not(gray)
    # ret, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)

    # thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    # if is_dark_mode(img):
    #     print("+++++++++++DARK BACKGROND++++++++++++++++++++++++++++++++++++++++++")
    #     thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY , 21, 6)
    #     thresh = 255-thresh
    #     page_info = pytesseract.image_to_data(thresh, output_type=Output.DICT, config="--oem 1 --psm 6")
    # else:
    #     page_info = pytesseract.image_to_data(gray, output_type=Output.DICT)

    # start of sc optimization comment out - 2024/05/05
    if is_dark_mode(img, logger):
        logger.debug("extract in DARK mode......")
        img2 = enhance(gray)
        logger.debug("time stamp3AB0: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        th2 = cv2.threshold(lazy.np.array(img2), 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
        logger.debug("time stamp3AB1: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        # page_info2 = pytesseract.image_to_data(th2, output_type=Output.DICT, lang="chi_sim")
        page_info2 = pytesseract.image_to_data(th2, output_type=Output.DICT)
        page_info = page_info2
    else:
        logger.debug("extract in LIGHT mode......")
        # page_info1 = pytesseract.image_to_data(th2, output_type=Output.DICT, lang="chi_sim")
        page_info1 = pytesseract.image_to_data(gray, output_type=Output.DICT)
        page_info = page_info1

    # page_info = remote_ocr(img_file)
    logger.debug("pageInfoooo::" + json.dumps(page_info))

    remove_junks(page_info)
    logger.debug("time stamp3C: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    print("extracted texts: ", page_info)

    raw_blk_data = gen_block_data(page_info)
    print("time stamp3C1: ", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    # blk_data = test_block_data()
    print_block_data(page_info, raw_blk_data)
    # print("***************************************************************")
    print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>time stamp3D: ", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    # blk_remove_dummy_lines(raw_blk_data)
    all_lines = flatten_lines(raw_blk_data)

    resegmented = segmentize_lines(all_lines, logger)

    logger.debug("time stamp3C0: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    
    return resegmented

# given image - output text and matched icons
#aname - anchor name (icon name)
#iconFile - icon template image file
#imageFile - image file or bytes data
# icon_templates is in the following data structure:
# [{"name": "***", "templates": ["file name0", "file name1"...]}....]
# factor is scale factor {} will cause search to search a spectrum of size factor
#
async def image2objects(img, icon_templates):
    return {
        "text_lines": await image2text_lines(img),
        "icons": await local_run_icon_matching(anames, iconFiles, imageFile, factor, logger)
    }


