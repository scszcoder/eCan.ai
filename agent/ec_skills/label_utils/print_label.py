# This is a sample Python script.
import json
import os
import subprocess
from datetime import datetime
import asyncio
# import win32print
# import win32api
import traceback
import time

from utils.lazy_import import lazy
# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.

from PIL import Image, ImageFont, ImageDraw
from pdf2image import convert_from_path
from concurrent.futures import ThreadPoolExecutor

from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
import fitz


async def reformat_and_print_labels(mainwin, args):  # type: ignore
    try:
        logger.debug("fullfill_ebay_orders started....", args["input"])
        new_orders = []
        fullfilled_orders = []
        format = args["input"]["format"]
        printer_name = args["input"]["printer_name"]
        label_dir = args["input"]["label_dir"]
        orders = args["input"]["orders"]
        product_book = args["input"]["product_book"]
        font_dir = args["input"]["font_dir"]
        font_size = args["input"]["font_size"]

        if options.get("use_ads", False):
            webdriver = connect_to_adspower(mainwin, url)
            if webdriver:
                mainwin.setWebDriver(webdriver)
        else:
            webdriver = mainwin.getWebDriver()

        if webdriver:
            print("fullfill_ebay_orders:", site)
            site_results = selenium_search_component(webdriver, pf, sites[site])
            ebay_new_orders = scrape_ebay_orders(webdriver)
            logger.debug("ebay_new_orders:", ebay_new_orders)

        print_status = await win_print_labels1(label_dir, printer, ecsite, order_data, product_book, txt_font_path, txt_font_size)


        msg = f"completed in fullfilling ebay new orders: {len(new_orders)} new orders came in, {len(fullfilled_orders)} orders processed."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"new_orders": new_orders, "fullfilled_orders": fullfilled_orders}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorFullfillEbayOrders")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]




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
    final_image = lazy.np.zeros((all_height+(len(images)-1)*padding + 2*v_pad, max_width + 2*h_pad, 3), dtype=lazy.np.uint8)
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
def geVariationText(vars, found_product, site):
    v_text = "v"
    for var_name in vars:
        v_text = v_text + found_product["listings"][site]["variations"][var_name]["note_text"]
        if isinstance(vars[var_name], str):
            v_text = v_text + found_product["listings"][site]["variations"]["vals"][vars[var_name]]["note_text"]
        else:
            #this is a numerical value.
            v_text = v_text + str(vars[var_name])
    return v_text


def geVariationFName(vars, found_product, site):
    v_text = "v"
    for var_name in vars:
        v_text = v_text + var_name[0].upper() + var_name[1:]
        if isinstance(vars[var_name], str):
            v_text = v_text + vars[var_name][0].upper()+vars[var_name][1:]
        else:
            #this is a numerical value.
            v_text = v_text + str(vars[var_name])
    return v_text



# add padding/margin to an image.
# text loc is in tuple format (x, y), relative to the top left corner
def genNoteText(site, order_data, product_book):
    note_text = ""
    for j, ord_prod in enumerate(order_data.getProducts()):
        found_product = next((prod for i, prod in enumerate(product_book) if prod["listings"][site]["asin"] == ord_prod.getPid()), None)
        note_text = note_text + found_product["note text"]
        note_text = note_text + "_"
        note_text = note_text + geVariationText(ord_prod.getVariations(), found_product, site)
        note_text = note_text + "_"
        note_text = note_text + str(ord_prod.getQuantity())
        if j != len(order_data) - 1:
            note_text = note_text + "_"

    return note_text

def genPVQSText(site, order_data, product_book):
    name_text = ""
    for j, ord_prod in enumerate(order_data.getProducts()):
        found_product = next((prod for i, prod in enumerate(product_book) if prod["listings"][site]["asin"] == ord_prod.getPid()), None)
        name_text = name_text + found_product["short_name"]
        name_text = name_text + "_"
        name_text = name_text + geVariationFName(ord_prod.getVariations(), found_product, site)
        name_text = name_text + "_"
        name_text = name_text + str(ord_prod.getQuantity())
        if j != len(order_data) - 1:
            name_text = name_text + "_"

    return name_text
def reformat_label_pdf(working_dir, pdffile, site, order_data, product_book, font_full_path, font_size):
    import cv2
    print("pdf to img start....", working_dir + pdffile)
    # images = convert_from_path(working_dir + pdffile)
    document = fitz.open(working_dir + pdffile)
    pdf_names = []
    wpdf_names = []

    all_orders = []
    for page in order_data:
        all_orders = all_orders + page["ol"]


    for i in range(document.page_count):
        page = document.load_page(i)  # Assuming adding text to the first page
        pix = page.get_pixmap()

        # Convert to image using OpenCV
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        pil_image = lazy.np.array(image)

        print("pdf to img done....", working_dir + pdffile)

        # sub = pdffile.split('_')
        name_parts = all_orders[i].getRecipientName().split()
        fn = name_parts[0]
        ln = name_parts[len(name_parts)-1]
        r_name = fn+"_"+ln+"_"

        pvqs_name = genPVQSText(site, all_orders[i], product_book)

        prefix = "ebay_"+r_name+pvqs_name
        # logger.debug(json.dumps(sub))


        # img = cv2.imread(working_dir + 'page0.jpg')
        result = pil_image.copy()
        # gray = cv2.cvtColor(pil_image, cv2.COLOR_BGR2GRAY)
        # gray = cv2.bilateralFilter(gray, 11, 17, 17)
        gray = cv2.cvtColor(pil_image, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 11, 17, 17)

        kernel = lazy.np.ones((5, 5), lazy.np.uint8)
        erosion = cv2.erode(gray, kernel, iterations=2)
        kernel = lazy.np.ones((4, 4), lazy.np.uint8)
        dilation = cv2.dilate(erosion, kernel, iterations=2)

        edged = cv2.Canny(dilation, 30, 200)

        contours = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = contours[0] if len(contours) == 2 else contours[1]
        # print(str(len(contours)) + ' rects are found....')

        for cntr in contours:
            x, y, w, h = cv2.boundingRect(cntr)
            cv2.rectangle(result, (x, y), (x + w, y + h), (0, 0, 255), 2)
            logger.debug("[reformat_label_pdf] x,y,w,h:" + str(x) + " " + str(y) + " " + str(w) + " " + str(h))

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
        text = genNoteText(site, all_orders[i], product_book)

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
        pdf_names.append(pdf_name)
        wpdf_names.append(wpdf_name)

    return pdf_names, wpdf_names
# Press the green button in the gutter to run the script.
def win_print_labels0(label_dir, printer, site, order_data, product_book, txt_font_path, txt_font_size):

    working_dir = label_dir
    logger.debug("[win_print_labels0] working_dir: ", working_dir)
    for file in os.listdir(working_dir):
        if file.startswith(site) and file.endswith(".pdf"):
            logger.debug("[win_print_labels0] file: ", file)

            pdf_name, wpdf_name = reformat_label_pdf(working_dir, file, site, order_data, product_book, txt_font_path, txt_font_size)

            # print out the files.
            # YOU CAN PUT HERE THE NAME OF YOUR SPECIFIC PRINTER INSTEAD OF DEFAULT
            if printer == "":
                currentprinter = win32print.GetDefaultPrinter()
            else:
                currentprinter = printer

            logger.debug("[win_print_labels0] current printer: ", currentprinter)

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
            from utils.subprocess_helper import run_no_window
            run_no_window(ghostscript, shell=True)
        else:
            logger.debug('[win_print_labels0] file name format error:' + file)


def get_printers():
    return [printer[2] for printer in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]

def print_pdf_sync(file_path, printer_name):
    logger.debug(f"[print_pdf_sync] Printing {file_path} to {printer_name}")
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
    logger.debug("[add_text_to_img] Adding Text to image:", text)
    pil_image = Image.fromarray(in_img)
    draw = ImageDraw.Draw(pil_image)
    if font_full_path:
        font = ImageFont.truetype(font_full_path, font_size)
    else:
        # font = ImageFont.load_default()
        font = ImageFont.truetype(default_font_name, font_size)

    draw.text(text_loc, text, font=font, fill="Blue")  # Adjust position and text color

    # Convert back to OpenCV format
    image_with_text = lazy.np.array(pil_image)

    # Convert back to PDF
    return image_with_text


async def win_print_labels1(label_dir, printers, ecsite, order_data, product_book, txt_font_path, txt_font_size):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        tasks = []
        working_dir = label_dir
        logger.debug("[win_print_labels1] label dir:"+working_dir)
        for pdf_file in os.listdir(working_dir):
            if pdf_file.startswith(ecsite) and pdf_file.endswith(".pdf"):
                logger.debug("[win_print_labels1]working on label:"+pdf_file)
                modified_pdfs, wpdf_names = reformat_label_pdf(working_dir, pdf_file, ecsite, order_data, product_book, txt_font_path, txt_font_size)
                for modified_pdf in modified_pdfs:
                    if check_printer_status(printers[0]):
                        tasks.append(print_pdf(modified_pdf, printers[0]))
                    elif len(printers) > 1 and check_printer_status(printers[1]):
                        tasks.append(print_pdf(modified_pdf, printers[1]))
                    elif len(printers) > 2 and check_printer_status(printers[2]):
                        tasks.append(print_pdf(modified_pdf, printers[2]))
                    else:
                        print(f"[win_print_labels1] No available printers for {pdf_file}")

        if tasks:
            await asyncio.gather(*tasks)
    except Exception as e:
        # Get the traceback information
        ex_stat = get_traceback(e, "ErrorWinPrintLabels1")
        logger.error(f"{ex_stat}")

    return ex_stat

def sync_win_print_labels1(label_dir, printer, ecsite, order_data, product_book, txt_font_path, txt_font_size):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        files_tbp = []

        if printer=="":
            printers = get_printers()
        else:
            printers = [printer]

        logger.debug("[sync_win_print_labels1] printers are:", printers)

        working_dir = label_dir
        logger.debug("[sync_win_print_labels1] label dir:"+working_dir)
        for pdf_file in os.listdir(working_dir):
            if pdf_file.startswith(ecsite) and pdf_file.endswith(".pdf"):
                logger.debug("[sync_win_print_labels1] working on label:"+pdf_file)
                modified_pdfs, wpdf_names = reformat_label_pdf(working_dir, pdf_file, ecsite, order_data, product_book, txt_font_path, txt_font_size)
                files_tbp = files_tbp + modified_pdfs

        if files_tbp:
            for file_path in files_tbp:
                if check_printer_status(printers[0]):
                    logger.debug("[sync_win_print_labels1] printing:"+file_path+" on printer: "+printers[0])
                    # print_pdf_sync(file_path, printers[0])
                elif len(printers) > 1 and check_printer_status(printers[1]):
                    logger.debug("[sync_win_print_labels1] printing:" + file_path + " on printer: " + printers[1])
                    print_pdf_sync(file_path, printers[1])
                elif len(printers) > 2 and check_printer_status(printers[2]):
                    logger.debug("[sync_win_print_labels1] printing:" + file_path + " on printer: " + printers[2])
                    print_pdf_sync(file_path, printers[2])

    except Exception as e:
        # Get the traceback information
        ex_stat = get_traceback(e, "ErrorSyncWinPrintLabels1")
        logger.error(f"{ex_stat}")

    return ex_stat
