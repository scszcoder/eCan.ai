# This is a sample Python script.

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.
import os, sys, time, argparse
import subprocess
import cv2
from PIL import ImageFont, ImageDraw, Image
import numpy as np
from pdf2image import convert_from_path
# import win32print
import datetime
from basicSkill import *


def genWinPrinterLocalReformatPrintSkill(worksettings, page, sect, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_printer_local_print", "win", "1.0", "AIPPS LLC", "PUBWINCHROMEETSY001",
                                          "Reformat Default Shipping Label and Print them On Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_printer_local_print/reformat_print", "", this_step)
    psk_words = psk_words + step_words



    this_step, step_words = genStepStub("end skill", "public/win_printer_local_print/reformat_print", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    print("DEBUG", "generated skill for windows file operation...." + psk_words)

    return this_step, psk_words


def genStepPrintLabels(labdir, printer, stat_name, stepN):
    stepjson = {
        "type": "Print Labels",
        "action": "Print Labels",
        "label_dir": labdir,
        "printer": printer,
        "print_status": stat_name
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def processPrintLabel(step, i):
    ex_stat = "success:0"
    try:
        print("Printing label, will do some processing before printing. .....")
        symTab[step["print_status"]] = print_labels(step["label_dir"], step["printer"])
    except:
        ex_stat = "ErrorPrintLabel:" + str(i)

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


# add padding/margin to an image.
# text loc is in tuple format (x, y), relative to the top left corner
def add_text(iimg, text, text_loc, font = cv2.FONT_HERSHEY_SIMPLEX, fontScale = 1, color = (255, 0, 0), thickness = 2):
    # Using cv2.putText() method
    texted_img = cv2.putText(iimg, text, text_loc, font, fontScale, color, thickness, cv2.LINE_AA)
    return texted_img


# Press the green button in the gutter to run the script.
def print_labels(label_dir, printer):

    today = datetime.today()
    yesterday = today - datetime.timedelta(days=1)

    today_string = yesterday.strftime("%Y%m%d")
    working_dir = 'C:/EbayOrders/Teco/orders/' + today_string + '/'
    print(working_dir)
    for file in os.listdir(working_dir):
        if file.startswith("ebay-label") and file.endswith(".pdf"):
            print(file)

            # convert pdf to image
            images = convert_from_path(working_dir+file)

            for i in range(len(images)):
                # Save pages as images in the pdf
                images[i].save(working_dir+'page' + str(i) + '.jpg', 'JPEG')

            sub = file.split('_')
            # print(sub)
            if len(sub) >= 5:
                first = sub[1]
                last = sub[2]
                prod = sub[3]
                num = sub[4].split('.')[0]

                img = cv2.imread(working_dir + 'page0.jpg')
                result = img.copy()
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
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
                    print("x,y,w,h:", x, y, w, h)

                # save resulting image
                # cv2.imwrite(working_dir+'rect.jpg', result)

                # show thresh and result
                # cv2.imshow("bounding_box", result)


                # crop out the ROI which is bounded by the rectangle.
                cropped_image = img[y:y+h, x:x+w]

                if (h > w):
                    cropped = cv2.rotate(cropped_image, cv2.cv2.ROTATE_90_CLOCKWISE).copy()
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
                text = prod + '_X_' + num
                # -- coding: utf-8
                # text = '钱包'
                text_rel_loc = (400, 700)
                text_image = add_text(resized_cropped_image, text, text_rel_loc, cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
                # cv2.imwrite(working_dir+'texted.png', text_image)

                # put 2 image into a new image
                # 1st image located at (150, 90)
                o_image = gen_img(resized_cropped, text_image)
                # cv2.imwrite(working_dir+'final.png', o_image)

                # save the result into a pdf file using PIL.
                p_image = Image.fromarray(o_image)
                pdff_name = first+last+'_'+prod+'_x_'+num+'.pdf'
                pdf_name = working_dir+pdff_name
                p_image.save(pdf_name, save_all=True)
                wpdf_name = pdf_name.replace('/', r'\\\\')

                # print out the files.
                # YOU CAN PUT HERE THE NAME OF YOUR SPECIFIC PRINTER INSTEAD OF DEFAULT
                # currentprinter = win32print.GetDefaultPrinter()
                # print(currentprinter)

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
                       '-sDEVICE=mswinpr2 '
                ghostscript = args + wpdf_name
                subprocess.call(ghostscript, shell=True)
            else:
                print('file name format error:' + file)