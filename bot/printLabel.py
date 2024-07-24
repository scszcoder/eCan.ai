# This is a sample Python script.
import json
import os
import subprocess
from datetime import datetime
import asyncio
import win32print
import win32api
import traceback
import time

import numpy as np
# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.

from PIL import Image, ImageFont, ImageDraw
import cv2
from pdf2image import convert_from_path
from concurrent.futures import ThreadPoolExecutor

from bot.basicSkill import genStepHeader, DEFAULT_RUN_STATUS, symTab, STEP_GAP, genStepStub, genStepCallExtern, genStepCreateData
from bot.Logger import log3
import fitz


def genWinPrinterLocalReformatPrintSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_printer_local_print", "win", "1.0", "AIPPS LLC", "PUBWINCHROMEETSY001",
                                          "Reformat Default Shipping Label and Print them On Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_printer_local_print/reformat_print", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global f_op\nformat = fin[0]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global label_path\nlabel_path = fin[1]\nprint('label_path:', label_path)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global printer_name\nprinter_name = fin[2]\nprint('printer_name:', printer_name)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global orders\norders = fin[3]\nprint('orders:', orders)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global product_book\nproduct_book = fin[4]\nprint('product_book:', product_book)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepCreateData("bool", "endOfOrdersPage", "NA", False, this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "font_dir", "NA", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCreateData("int", "font_size", "NA", 28, this_step)
    psk_words = psk_words + step_words


    # this_step, step_words = genStepCreateData("expr", "shipToSummeries", "NA", "[]", this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    # psk_words = psk_words + step_words


    #labdir, printer, ecsite, order_data, product_book, font_dir, font_size, stat_name, stepN
    this_step, step_words = genStepPrintLabels("label_path", "printer_name", "ecsite", "orders", "product_book", "font_dir", "font_size", "print_status", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_printer_local_print/reformat_print", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows file operation...." + psk_words)

    return this_step, psk_words


def genStepPrintLabels(labdir, printer, ecsite, order_data, product_book, font_dir, font_size, stat_name, stepN):
    stepjson = {
        "type": "Print Labels",
        "action": "Print Labels",
        "label_dir": labdir,
        "printer": printer,
        "ecsite": ecsite,
        "order_data": order_data,
        "product_book": product_book,
        "font_dir": font_dir,
        "font_size": font_size,
        "print_status": stat_name
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



async def processPrintLabels(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        log3("Printing label, will do some processing before printing. .....")
        symTab[step["print_status"]] = await win_print_labels1(symTab[step["labels_dir"]], symTab[step["printer"]], symTab[step["ecsite"]])
    except:
        ex_stat = "ErrorPrintLabel:" + str(i)
        log3(ex_stat)

    return (i + 1), ex_stat



# add padding/margin to an image.
# color is in tuple format (R, G, B)
def add_padding(pil_img, top, right, bottom, left, color):
    width, height = pil_img.size
    new_width = width + right + left
    new_height = height + top + bottom
    padded_image = Image.new(pil_img.mode, (new_width, new_height), color)
    result = pil_img.copy()
    result.paste(padded_image, (left, top))
    return padded_image


# this function stack 2 image on top of itself with 40 pixel of padding in between.
# ------------------------------------------------------
# |                                        ^           |
# |<-----> h_pad (horizontal margin)       | v_pad     |
# |                                        v  Vertical |
# |       ------------------------------------  margin |
# |       |                                  |         |
# |       |          image 1                 |         |
# |       |                                  |         |
# |       ------------------------------------         |
# |                        ^                           |
# |                        | Padding                   |
# |                        v                           |
# |       ------------------------------------         |
# |       |                                  |         |
# |       |          image 2                 |         |
# |       |                                  |         |
# |       ------------------------------------         |
# |                                                    |
# |                                                    |
# ------------------------------------------------------
def gen_img(img1, img2, top_left_margin=(150, 90), padding = 40):
    images = []
    max_width = 0  # find the max width of all the images
    all_height = 0  # the total height of the images (vertical stacking)

    images.append(img1)
    images.append(img2)

    for img in images:
        # open all images and find their sizes
        img_width = img.shape[1]
        img_height = img.shape[0]
        if img_width > max_width:
            max_width = img_width
        #add all the images heights
        all_height += img_height
    # create a new array (blank image) with a size large enough to contain all the images
    # also add padding size for all the images except the last one
    v_pad = top_left_margin[1]
    h_pad = top_left_margin[0]
    final_image = np.zeros((all_height+(len(images)-1)*padding + 2*v_pad, max_width + 2*h_pad, 3), dtype=np.uint8)
    final_image.fill(255)
    current_y = v_pad   # keep track of where your current image was last placed in the y coordinate
    current_x = h_pad

    for image in images:
        # add an image to the final array and increment the y coordinate
        h = image.shape[0]
        w = image.shape[1]
        final_image[current_y:h+current_y, current_x:w+current_x, :] = image
        # add the padding between the images
        current_y += h + padding
    return final_image

# var is a json dictionary of var_name, var_value pairs
def gen_variation_text(vars, found_product, site):
    v_text = "v"
    for var_name in vars:
        v_text = v_text + found_product["variations"][site][var_name]["note_text"]
        if isinstance(vars[var_name], str):
            v_text = v_text + found_product["variations"][site][vars[var_name]]["note_text"]
        else:
            #this is a numerical value.
            v_text = v_text + str(vars[var_name])
    return v_text

# add padding/margin to an image.
# text loc is in tuple format (x, y), relative to the top left corner
def gen_note_text(site, order_data, product_book):
    note_text = ""
    for j, ord_prod in enumerate(order_data):
        found_product = next((prod for i, prod in enumerate(product_book) if prod.getPIDBySite(site) == ord_prod.getProductId), None)
        note_text = note_text + found_product["note_short_name"]
        note_text = note_text + "_"
        note_text = note_text + gen_variation_text(ord_prod.getVariations(), found_product, site)
        note_text = note_text + "_"
        note_text = note_text + str(ord_prod.getQuantity())
        if j != len(order_data) - 1:
            note_text = note_text + "_"

    return note_text


def reformat_label_pdf(working_dir, pdffile, site, order_data, product_book, font_full_path, font_size):
    print("pdf to img start....", working_dir + pdffile)
    # images = convert_from_path(working_dir + pdffile)
    document = fitz.open(working_dir + pdffile)

    page = document.load_page(0)  # Assuming adding text to the first page
    pix = page.get_pixmap()

    # Convert to image using OpenCV
    image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    pil_image = np.array(image)

    print("pdf to img done....", working_dir + pdffile)

    sub = pdffile.split('_')
    prefix = pdffile.split(".")[0]
    # log3(json.dumps(sub))
    if len(sub) >= 5:
        site = sub[0]
        first = sub[1]
        last = sub[2]
        prod = sub[3]
        num = sub[4].split('.')[0]

        # img = cv2.imread(working_dir + 'page0.jpg')
        result = pil_image.copy()
        # gray = cv2.cvtColor(pil_image, cv2.COLOR_BGR2GRAY)
        # gray = cv2.bilateralFilter(gray, 11, 17, 17)
        gray = cv2.cvtColor(pil_image, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 11, 17, 17)

        kernel = np.ones((5, 5), np.uint8)
        erosion = cv2.erode(gray, kernel, iterations=2)
        kernel = np.ones((4, 4), np.uint8)
        dilation = cv2.dilate(erosion, kernel, iterations=2)

        edged = cv2.Canny(dilation, 30, 200)

        contours = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = contours[0] if len(contours) == 2 else contours[1]
        # print(str(len(contours)) + ' rects are found....')

        for cntr in contours:
            x, y, w, h = cv2.boundingRect(cntr)
            cv2.rectangle(result, (x, y), (x + w, y + h), (0, 0, 255), 2)
            log3("x,y,w,h:" + str(x) + " " + str(y) + " " + str(w) + " " + str(h))

        # save resulting image
        # cv2.imwrite(working_dir+'rect.jpg', result)

        # show thresh and result
        # cv2.imshow("bounding_box", result)

        # crop out the ROI which is bounded by the rectangle.
        cropped_image = pil_image[y:y + h, x:x + w]

        if (h > w):
            cropped = cv2.rotate(cropped_image, cv2.ROTATE_90_CLOCKWISE).copy()
            cropped_image = cropped.copy()
        else:
            cropped = cropped_image.copy()

        # cv2.imshow("crop", cropped_image)
        # cv2.imwrite(working_dir+'contour1.png', cropped_image)

        # now need to scale to image to a standard 1100x550 (WxH)
        target_width = 1100
        target_height = 750
        target_dim = (target_width, target_height)

        # resize image
        resized_cropped = cv2.resize(cropped, target_dim, interpolation=cv2.INTER_AREA)
        resized_cropped_image = resized_cropped.copy()

        # add some text note to the image,
        text = gen_note_text(site, order_data, product_book)

        text_rel_loc = (400, 700)
        # font_full_path = "C:/Users/songc/PycharmProjects/ecbot/resource/fonts/Noto_Serif_SC/static/NotoSerifSC-Medium.ttf"
        default_font_name = "arial.ttf"
        text_image = add_text_to_img(resized_cropped_image, text, text_rel_loc, font_full_path, default_font_name, font_size)
        # cv2.imwrite(working_dir+'texted.png', text_image)

        # put 2 image into a new image
        # 1st image located at (150, 90)
        o_image = gen_img(resized_cropped, text_image)
        # cv2.imwrite(working_dir+'final.png', o_image)

        # save the result into a pdf file using PIL.
        p_image = Image.fromarray(o_image)
        pdff_name = prefix + '_r2p.pdf'
        pdf_name = working_dir + pdff_name
        p_image.save(pdf_name, save_all=True)
        wpdf_name = pdf_name.replace('/', r'\\\\')

    return pdf_name, wpdf_name
# Press the green button in the gutter to run the script.
def win_print_labels0(label_dir, printer, site, order_data, product_book, txt_font_path, txt_font_size):

    working_dir = label_dir
    log3(working_dir)
    for file in os.listdir(working_dir):
        if file.startswith(site) and file.endswith(".pdf"):
            log3(file)

            pdf_name, wpdf_name = reformat_label_pdf(working_dir, file, site, order_data, product_book, txt_font_path, txt_font_size)

            # print out the files.
            # YOU CAN PUT HERE THE NAME OF YOUR SPECIFIC PRINTER INSTEAD OF DEFAULT
            if printer == "":
                currentprinter = win32print.GetDefaultPrinter()
            else:
                currentprinter = printer

            log3(currentprinter)

            # the following command print silently.
            # C:\"Program Files"\gs\gs9.54.0\bin\gswin64c.exe  -dPrinted -dNoCancel -dBATCH -dNOPAUSE -dNOSAFER -q -dNumCopies=1 -dQueryUser=3 -sDEVICE=mswinpr2  testImage.pdf
            args = '"C:\\\\Program Files\\\\gs\\\\gs9.54.0\\\\bin\\\\gswin64c" ' \
                   '-dPrinted ' \
                   '-dNoCancel ' \
                   '-dBATCH ' \
                   '-dNOPAUSE ' \
                   '-dNOSAFER ' \
                   '-q ' \
                   '-dFitPage ' \
                   '-dNumCopies=1 ' \
                   '-dQueryUser=3 ' \
                   '-sDEVICE='
            args = args + currentprinter + ' '
            ghostscript = args + wpdf_name
            subprocess.call(ghostscript, shell=True)
        else:
            log3('file name format error:' + file)


def get_printers():
    return [printer[2] for printer in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]

def print_pdf_sync(file_path, printer_name):
    print(f"Printing {file_path} to {printer_name}")
    if printer_name:
        # Set the specified printer as the default printer
        win32print.SetDefaultPrinter(printer_name)

    # Use the default PDF viewer to print the file
    win32api.ShellExecute(0, "print", file_path, None, ".", 0)

    # Wait for the print job to be sent
    time.sleep(5)

def check_printer_status(printer_name):
    return printer_name in get_printers()

async def print_pdf(file_path, printer_name):
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        await loop.run_in_executor(pool, print_pdf_sync, file_path, printer_name)

def add_text_to_img(in_img, text, text_loc, font_full_path="", default_font_name="arial.ttf", font_size=28):
    print("Adding Text to image:", text)
    pil_image = Image.fromarray(in_img)
    draw = ImageDraw.Draw(pil_image)
    if font_full_path:
        font = ImageFont.truetype(font_full_path, font_size)
    else:
        # font = ImageFont.load_default()
        font = ImageFont.truetype(default_font_name, font_size)

    draw.text(text_loc, text, font=font, fill="Blue")  # Adjust position and text color

    # Convert back to OpenCV format
    image_with_text = np.array(pil_image)

    # Convert back to PDF
    return image_with_text


async def win_print_labels1(label_dir, printers, ecsite, order_data, product_book, txt_font_path, txt_font_size):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        tasks = []
        working_dir = label_dir
        log3("label dir:"+working_dir)
        for pdf_file in os.listdir(working_dir):
            if pdf_file.startswith(ecsite) and pdf_file.endswith(".pdf"):
                log3("working on label:"+pdf_file)
                modified_pdf, wpdf_name = reformat_label_pdf(working_dir, pdf_file, ecsite, order_data, product_book, txt_font_path, txt_font_size)
                if check_printer_status(printers[0]):
                    tasks.append(print_pdf(modified_pdf, printers[0]))
                elif len(printers) > 1 and check_printer_status(printers[1]):
                    tasks.append(print_pdf(modified_pdf, printers[1]))
                elif len(printers) > 2 and check_printer_status(printers[2]):
                    tasks.append(print_pdf(modified_pdf, printers[2]))
                else:
                    print(f"No available printers for {pdf_file}")

        if tasks:
            await asyncio.gather(*tasks)
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorPrintLabels1:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorPrintLabels1: traceback information not available:" + str(e)
        log3(ex_stat)

    return ex_stat

def sync_win_print_labels1(label_dir, printer, ecsite, order_data, product_book, txt_font_path, txt_font_size):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        files_tbp = []

        if printer=="":
            printers = get_printers()
        else:
            printers = [printer]

        print("printers are:", printers)

        working_dir = label_dir
        log3("label dir:"+working_dir)
        for pdf_file in os.listdir(working_dir):
            if pdf_file.startswith(ecsite) and pdf_file.endswith(".pdf"):
                log3("working on label:"+pdf_file)
                modified_pdf, wpdf_name = reformat_label_pdf(working_dir, pdf_file, ecsite, order_data, product_book, txt_font_path, txt_font_size)
                files_tbp.append(modified_pdf)

        if files_tbp:
            for file_path in files_tbp:
                if check_printer_status(printers[0]):
                    print("printing:"+file_path+" on printer: "+printers[0])
                    # print_pdf_sync(file_path, printers[0])
                elif len(printers) > 1 and check_printer_status(printers[1]):
                    print("printing:" + file_path + " on printer: " + printers[1])
                    print_pdf_sync(file_path, printers[1])
                elif len(printers) > 2 and check_printer_status(printers[2]):
                    print("printing:" + file_path + " on printer: " + printers[2])
                    print_pdf_sync(file_path, printers[2])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorPrintLabels1:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorPrintLabels1: traceback information not available:" + str(e)
        log3(ex_stat)

    return ex_stat
