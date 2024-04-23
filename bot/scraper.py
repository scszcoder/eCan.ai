import json
from bs4 import BeautifulSoup
import pyautogui
import numpy as np
import re
import random
from calendar import isleap
import cv2
from productsData import *
from scraperAmz import *
from Logger import *



class ADDR:
    def __init__(self):
        self.street1 = ''
        self.street2 = ''
        self.street3 = ''
        self.city = ''
        self.state = ''
        self.country = ''
        self.zip = ''
        self.type = ''          # 'R' for residential, 'B' for business

    def setStreet1(self, st1):
        self.street1 = st1

    def setStreet2(self, st2):
        self.street2 = st2

    def setStreet3(self, st3):
        self.street3 = st3

    def setCity(self, city):
        self.city = city

    def setState(self, st):
        self.state = st

    def setCountry(self, country):
        self.country = country

    def setZip(self, zip):
        self.zip = zip

    def setType(self, type):
        self.type = type

    def toJson(self):
        return {
            "street1": self.street1,
            "street2": self.street2,
            "street3": self.street3,
            "city": self.city,
            "state": self.state,
            "country": self.country,
            "zip": self.zip,
            "type": self.type
        }

class PERSON:
    def __init__(self):
        self.first_name = ''
        self.last_name = ''
        self.suffix = ''
        self.birth_year = 0
        self.birth_month = 0
        self.birth_day = 0
        self.phones = ''
        self.addresses = []
        self.emails = []
        self.used = False
        self.user = ''
        self.used_date = ''

    def setType(self, type):
        self.type = type

    def toJson(self):
        return {
            "first_name": self.first_name,
            "last_name": self.last_name,
            "suffix": self.suffix,
            "birthday": self.birth_year,
            "phones": self.phones,
            "emails": self.emails,
            "addresses": self.addresses
        }


def get_birth_month(month_word):
    month = 0
    if month_word == 'Jan':
        month = 1
    elif month_word == 'Feb':
        month = 2
    elif month_word == 'Mar':
        month = 3
    elif month_word == 'Apr':
        month = 4
    elif month_word == 'May':
        month = 5
    elif month_word == 'Jun':
        month = 6
    elif month_word == 'Jul':
        month = 7
    elif month_word == 'Aug':
        month = 8
    elif month_word == 'Sep':
        month = 9
    elif month_word == 'Oct':
        month = 10
    elif month_word == 'Nov':
        month = 11
    elif month_word == 'Dec':
        month = 12
    return month


def get_month_days(year, month):
    days = 0
    if month == 1:
        month = 31
    elif month == 'Feb':
        month = 28
        if isleap(year):
            month = 29
    elif month == 'Mar':
        month = 31
    elif month == 'Apr':
        month = 30
    elif month == 'May':
        month = 31
    elif month == 'Jun':
        month = 30
    elif month == 'Jul':
        month = 31
    elif month == 'Aug':
        month = 31
    elif month == 'Sep':
        month = 30
    elif month == 'Oct':
        month = 31
    elif month == 'Nov':
        month = 30
    elif month == 'Dec':
        month = 31
    return days



# input: screen save file name.
# output: on the screen saving image, find and return the location of the file name input box.
def find_file_name_box(sfn):
    output = [[0, 0, 0], [0, 0, 0]]
    image = cv2.imread(sfn)
    # mat full star, 0.8, match empty star 0.80, match half star 0.8.
    template = cv2.imread('c:/temp/aidata/fileName1.jpg')
    icon_height = template.shape[0]
    icon_width = template.shape[1]
    log3("icon size: "+str(icon_height)+" "+str(icon_width))
    result = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
    loc = np.where(result >= 0.85)
    count = 0
    match = None
    # get the full star match count.
    for pt in zip(*loc[::-1]):  # Swap columns and rows
        count = count + 1

    if count > 0:
        match = (loc[0][0], loc[1][0])

    log3("found match: "+json.dumps(match))
    if match:
        input_loc = (match[0] + int(0.5 * icon_height), match[1]+2*icon_width)
    else:
        log3("ERROR: unrecognized file dialog screen......")

    return input_loc






def subfinder(mylist, pattern):
    match_loc = []
    for i in range(len(mylist) - len(pattern) + 1):
        if mylist[i] == pattern[0] and mylist[i:i+len(pattern)] == pattern:
            match_loc.append(i)
    return match_loc


def get_last_names(html_file):
    last_names = []
    # parse the last name page to obtain a list of last names.
    soup = BeautifulSoup(html_file, 'html.parser')
    log3(json.dumps(soup))

    atags = soup.find_all('a')
    pn_i = [i for i, t in enumerate(atags) if len(t.contents) == 1 and not t.contents[0].name]
    pn = np.array(atags)[pn_i].tolist()
    n = (o.contents[0] for o in pn)

    start = subfinder(n, ['Name', 'Phone'], 'Address')
    end_name = subfinder(n, ['1'])
    end_number = subfinder(n, ['A', 'B', 'C'])

    start_idx = start[0]+3

    if len(end_name) == 0:
        # this means that the last names are only enough to fill one page.
        end_idx = end_number[0]
    else:
        end_idx = end_name[0]

    last_names_i = [i for i, ln in enumerate(n) if i > start_idx and i < end_idx ]
    log3(json.dumps(last_names_i))
    last_names = np.array(n)[last_names_i].tolist()
    log3(json.dumps(last_names))
    log3(str(len(last_names)))

    return last_names


def get_first_name_pages(html_file):
    num_pages = 1
    # parse the last name page to obtain a list of last names.
    soup = BeautifulSoup(html_file, 'html.parser')
    log3(json.dumps(soup))

    atags = soup.find_all('a')
    pn_i = [i for i, t in enumerate(atags) if len(t.contents) == 1 and not t.contents[0].name]
    pn = np.array(atags)[pn_i].tolist()
    n = (o.contents[0] for o in pn)

    end_name = subfinder(n, ['1'])
    end_number = subfinder(n, ['A', 'B', 'C'])

    if len(end_name) != 0:
        # this means that the last names are only enough to fill one page.
        num_pages_idx = end_number[0] - 1
        num_pages = n[num_pages_idx]

    return num_pages


def get_first_names(html_file):
    full_names = []
    # parse the last name page to obtain a list of last names.
    soup = BeautifulSoup(html_file, 'html.parser')
    log3(json.dumps(soup))

    atags = soup.find_all('a')
    pn_i = [i for i, t in enumerate(atags) if len(t.contents) == 1 and not t.contents[0].name]
    pn = np.array(atags)[pn_i].tolist()
    n = (o.contents[0] for o in pn)

    start = subfinder(n, ['Name', 'Phone'], 'Address')
    end_name = subfinder(n, ['1'])
    end_number = subfinder(n, ['A', 'B', 'C'])

    start_idx = start[0]+3

    if len(end_name) == 0:
        # this means that the last names are only enough to fill one page.
        end_idx = end_number[0]
    else:
        end_idx = end_name[0]

    last_names_i = [i for i, ln in enumerate(n) if i > start_idx and i < end_idx ]
    log3(json.dumps(last_names_i))
    full_names = np.array(n)[last_names_i].tolist()
    log3(json.dumps(full_names))
    log3(str(len(full_names)))

    return full_names




def get_details_info(html_file):
    usr = PERSON()
    addr = ADDR()
    soup = BeautifulSoup(html_file, 'html.parser')
    # all useful information are here:
    useful = soup.findAll('div', {"class": lambda t: t in ('content-label h5', 'content-value')})
    ageuseful = soup.findAll('span', {"class": 'content-value'})
    agewords = ageuseful[0].text.split(' ')
    usr.birth_year = int(agewords[3][0:4])
    usr.birth_month = get_birth_month(agewords[2][1:4])
    days = get_month_days(usr.birth_year, usr.birth_month)
    usr.birth_day = random.randrange(1, days+1)

    # log3(agewords[0][1:4])     # ’age'
    # log3(agewords[1])          # age in number
    # log3(agewords[2][1:4])     # birth month
    # log3(agewords[3][0:4])     # birth year

    for item in useful:
        atags = item.find_all('a')
        if len(atags) == 0:
            # deal with email related stuff here
            if re.search('[a-zA-Z].*\@.*\.[a-zA-Z]', item.text):
                usr.emails.append(re.search('[a-zA-Z].*\@.*\..*[a-zA-Z]', item.text).group())
            elif re.search('Age', item.text):
                astring = re.search('Age', item.text).group()
                log3(astring)
        else:
            for x in atags:
                a = x.find_all('span')
                for l in a:
                    if l.get('itemprop') == 'streetAddress':
                        addr.street = l.text
                    elif l.get('itemprop') == 'addressLocality':
                        addr.city = l.text
                    elif l.get('itemprop') == 'addressRegion':
                        addr.state = l.text
                    elif l.get('itemprop') == 'postalCode':
                        addr.zip = l.text
                if (addr.street != ''):
                    usr.addresses.append(addr)

    return usr


