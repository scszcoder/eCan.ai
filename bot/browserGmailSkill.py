from bot.basicSkill import genStepHeader, genStepMouseClick, genStepStub, genStepKeyInput, genStepCallExtern, genStepWait, \
    genStepExtractInfo, genStepTextInput, genStepSearchAnchorInfo, genStepCreateData, genStepCheckCondition

from bot.seleniumSkill import *
ADS_BATCH_SIZE = 2

# assumed precondition for this skill:
# ADS power already opened, and webdriver connected, user profile already loaded.
# the starting point of this skill will be check whether gmail tab is already open
# if not, open the tab, and then check the log in status, hopefull, will already
# be logged in, if not go thru log in and hopefully user name and pw already being
# loaded, if not type in user name and pw.
# if captcha is needed, then quit.
# once logged in, randomly open a few emails and click on the sent box and be done.
# hopefully this will keep google happy.
def genWinADSGmailBrowserRefreshSkill(worksettings, stepN, theme):
    psk_words = "{"
    # site_url = "https://www.amazon.com/"

    this_step, step_words = genStepHeader("win_ads_gmail_home_browser_refresh", "win", "1.0", "AIPPS LLC", "PUBWINADSREFRESHGMAIL001",
                                          "Windows ADS Power refresh gmail with webdriver.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_ads_gmail_home/browser_refresh", "", this_step)
    psk_words = psk_words + step_words

    # now open gmail tab if not already，(this step will internall check whether the tab is already open, if open, simply switch to it)
    this_step, step_words = genStepWebdriverGoToTab("web_driver", "gmail", "https://www.gmail.com", "site_result", "site_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    # assume profile file is ready.
    this_step, step_words = genStepCallExtern("global gmail_acct\ngmail_acct = fin[0]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global gmail_pw\ngmail_pw = fin[1]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('Start Refresh Gmail.....', gmail_acct, gmail_pw)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words
    # first try to sign in
    # this_step, step_words = genStepsChromeRefreshGMailSkill(worksettings, this_step, theme)
    this_step, step_words = genStepsWinChromeGmailBrowserSignIn(this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepsWinChromeGmailBrowserRefresh(this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_ads_gmail_home/browser_refresh", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    print("DEBUG", "generated skill for windows ads power gmail routine access....." + psk_words)

    return this_step, psk_words


def genWinADSGmailBrowserAnswerEmailsSkill(worksettings, stepN, theme):
    psk_words = "{"
    # site_url = "https://www.amazon.com/"

    this_step, step_words = genStepHeader("win_ads_gmail_home_browser_answer_emails", "win", "1.0", "AIPPS LLC", "PUBWINADSREFRESHGMAIL002",
                                          "Windows ADS Power answer gmails with webdriver.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_ads_gmail_home/browser_answer_emails", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end skill", "public/win_ads_gmail_home/browser_answer_emails", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    print("DEBUG", "generated skill for windows ads power answer gmails and remove spams....." + psk_words)

    return this_step, psk_words

def genWinADSGmailBrowserSendEmailsSkill(worksettings, stepN, theme):
    psk_words = "{"
    # site_url = "https://www.amazon.com/"

    this_step, step_words = genStepHeader("win_ads_gmail_home_browser_send_emails", "win", "1.0", "AIPPS LLC", "PUBWINADSREFRESHGMAIL003",
                                          "Windows ADS Power send gmail with webdriver.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_ads_gmail_home/browser_send_emails", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end skill", "public/win_ads_gmail_home/browser_send_emails", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    print("DEBUG", "generated skill for windows ads power send gmail....." + psk_words)

    return this_step, psk_words


# assume the gmail screen page/tap is already focused. we simply click on a couple of place to simulate
# mouse activity.
# input : gmail account email site, email addr and pw, backup email and pw
#
def genStepsChromeRefreshGMailSkill(worksettings, stepN, theme):
    psk_words = ""

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, stepN)
    psk_words = psk_words + step_words

    # assume profile file is ready.
    this_step, step_words = genStepCallExtern("global gmail_acct\ngmail_acct = fin[0]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global gmail_pw\ngmail_pw = fin[1]\nprint('gmail_pw:', gmail_pw, gmail_acct)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # os is like windows, macos, linux...
    # this_step, step_words = genStepCallExtern("global back_email_site\nback_email_site = fin[2]", "", "in_line", "", this_step)
    # psk_words = psk_words + step_words
    #
    # # site is like amazon, ebay, etcs....
    # this_step, step_words = genStepCallExtern("global back_email_acct\nback_email_acct = fin[3]", "", "in_line", "", this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepCallExtern("global back_email_pw\nback_email_pw = fin[4]", "", "in_line", "", this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverGoToTab("web_driver", "gmail", "https://mail.google.com/mail/u/0/#inbox", "site_result", "site_flag", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWebdriverExtractInfo("", "sk_work_settings", "screen_info", "ads_browser", "top", theme, this_step, None)
    psk_words = psk_words + step_words


    # this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_browser", "top", theme, this_step, None)
    # psk_words = psk_words + step_words

    # this_step, step_words = genStepSearchAnchorInfo("screen_info", "gmail", "direct", "anchor icon", "any", "useless", "gmail_open", "ads", False, this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("not gmail_open", "", "", this_step)
    psk_words = psk_words + step_words

    # open a new tab to go to gmail
    # open a new tab with hot-key ctrl-t
    this_step, step_words = genStepKeyInput("", True, "ctrl,t", "", 3, this_step)
    psk_words = psk_words + step_words

    # since the mouse cursor will be automatiall put at the right location, just start typing.... www.amazcon.com
    this_step, step_words = genStepTextInput("var", False, "www.gmail.com", "direct", 0.05, "enter", 1, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # click on gmail tab
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "gmail", "anchor icon", "", 0, "center", [0, 0], "box", 2, 2, [7, 2], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "gmail", "home", theme, this_step, None)
    psk_words = psk_words + step_words


    this_step, step_words = genStepSearchAnchorInfo("screen_info", "Compose", "direct", "anchor text", "any", "useless", "logged_in", "ads", False, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCheckCondition("not logged_in", "", "", this_step)
    psk_words = psk_words + step_words

    # confirm we're on sign in screen.
    this_step, step_words = genStepSearchAnchorInfo("screen_info", "choose_account", "direct", "anchor text", "any", "useless", "on_login_page", "ads", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("on_login_page", "", "", this_step)
    psk_words = psk_words + step_words

    # should be a loop to wait, the site could take a long time to open.

    # once the page is loaded, check if log in button is there, if not, click to translate to english, then click on english

    # then wait for log in button to appear again, if so,
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "@gmail", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [7, 2], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "your_password", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [7, 2], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepTextInput("var", False, "gmail_pw", "expr", 0.05, "enter", 1, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "next", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [7, 2], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # now that we're in, click on inbox to show all emails list, and fetch # of new email received, # to the right of inbox,
    # then read them one by one by clicking on the titles below "Primary".
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "inbox", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [7, 2], this_step)
    psk_words = psk_words + step_words


    #read screen for the confirmation pop up.
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "ads_power", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    # click on the confirmation popup.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "sent", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "inbox", "anchor text", "", 0, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    # refresh the current tab to keep logged in.
    this_step, step_words = genStepKeyInput("", True, "ctrl,r", "", 3, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    return this_step, psk_words


def genStepsIdentifySideBarBoxes():
    print('')
    # inbox = driver.find_element(By.XPATH, "//a[@href='https://mail.google.com/mail/u/0/#inbox']")
    # inbox_element = driver.find_element(By.XPATH, "//div[@data-tooltip='收件箱' or contains(@aria-label, '收件箱')]")
    #
    # # Extract the number of unread emails from the child element (the count is often within a span or div tag)
    # unread_count_element = inbox_element.find_element(By.XPATH, ".//div[@class='bsU']")
    # unread_count = unread_count_element.text
    #
    # # Click on 已加星标 (Starred)
    # starred = driver.find_element(By.XPATH, "//a[@href='https://mail.google.com/mail/u/0/#starred']")
    # starred.click()
    # time.sleep(2)
    #
    # # Click on 已延后 (Snoozed)
    # snoozed = driver.find_element(By.XPATH, "//a[@href='https://mail.google.com/mail/u/0/#snoozed']")
    # snoozed.click()
    # time.sleep(2)
    #
    # # Click on 已发邮件 (Sent)
    # sent = driver.find_element(By.XPATH, "//a[@href='https://mail.google.com/mail/u/0/#sent']")
    # sent.click()
    # time.sleep(2)
    #
    # # Click on 草稿 (Drafts)
    # drafts = driver.find_element(By.XPATH, "//a[@href='https://mail.google.com/mail/u/0/#drafts']")
    # drafts.click()
    # time.sleep(2)
    #
    # # Optionally click on 显示更多标签 (Show more labels)
    # show_more = driver.find_element(By.XPATH, "//span[contains(text(), '显示更多标签')]")
    # show_more.click()


def genStepsFetchUnreadInbox():
    print('')

    # # Define a function to extract information from email rows
    # def extract_email_info(row):
    #     try:
    #         # Extract the sender's name or email
    #         sender = row.find_element(By.XPATH, ".//span[@class='zF' or @class='yW']").text
    #
    #         # Extract the subject line
    #         subject = row.find_element(By.XPATH, ".//span[@class='bqe']").text
    #
    #         # Extract the date
    #         date = row.find_element(By.XPATH, ".//span[@class='bq3']").text
    #
    #         # Determine read/unread status based on class
    #         status = "Unread" if "zE" in row.get_attribute("class") else "Read"
    #
    #         return {
    #             "sender": sender,
    #             "subject": subject,
    #             "date": date,
    #             "status": status
    #         }
    #     except Exception as e:
    #         print("Error extracting data:", e)
    #         return None
    #
    # try:
    #     # Wait for inbox to load and locate all email rows (either read or unread)
    #     email_rows = driver.find_elements(By.XPATH, "//tr[contains(@class, 'zA')]")
    #
    #     # Loop through each email row and extract the details
    #     for row in email_rows:
    #         email_info = extract_email_info(row)
    #         if email_info:
    #             print(email_info)
    #
    # except Exception as e:
    #     print("An error occurred:", e)
    # finally:
    #     driver.quit()

def genStepsWinChromeGmailBrowserSignIn(stepN):
    try:
        psk_words = ""


        this_step, step_words = genStepWait(5, 0, 0, stepN)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "action_result", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("boolean", "action_flag", "NA", True, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("boolean", "extract_flag", "NA", True, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global info_type\ninfo_type= 'web element'", "", "in_line", "",
                                                  this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "signed_out_text", "NA", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "signed_out", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("string", "run_stat", "NA", "Completed:0", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "enter_key", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("from selenium.webdriver.common.keys import Keys\nglobal enter_key\nenter_key=Keys.RETURN", "", "in_line", "",
                                                  this_step)
        psk_words = psk_words + step_words

        # search first...check whether we have been signed out
        # # Wait for the element with the "Signed out" text to be present
        #     signed_out_element = WebDriverWait(driver, 10).until(
        #         EC.presence_of_element_located((By.CLASS_NAME, "lrLKwc"))
        #     )
        #
        #     # Check if the text is "Signed out"
        #     if signed_out_element.text.strip().lower() == "signed out":
        #         print("User is signed out. Clicking on it...")
        #         signed_out_element.click()
        #     else:
        #         print("User is signed in.")

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CLASS_NAME,
                                                            "lrLKwc", False, "var", "signed_out",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("signed_out != None", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global signed_out, signed_out_text\nsigned_out_text=signed_out.text.strip().lower()\nprint('signed_out_text:',signed_out_text)", "", "in_line", "",
                                                  this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("signed_out_text == 'signed out'", "", "", this_step)
        psk_words = psk_words + step_words

        # try to sign back in.

        # click on signed out. which will bring us to sign in again to input password.
        this_step, step_words = genStepWebdriverClick("web_driver", "signed_out", "action_result", "action_flag",
                                                      this_step)
        psk_words = psk_words + step_words


        # hopefully no need to input user name which should have been memorized by browser already:
        # # Wait for the password field to appear
        #     password_field = WebDriverWait(driver, 10).until(
        #         EC.presence_of_element_located((By.NAME, "Passwd"))
        #     )
        #
        #     # Enter the password
        #     password_field.send_keys("your_password_here")
        #
        #     # Press Enter to submit
        #     password_field.send_keys(Keys.RETURN)
        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 10, "info_type", By.NAME,
                                                            "Passwd", False, "var", "pw_input_box",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverClick("web_driver", "pw_input_box", "action_result", "action_flag", this_step)
        psk_words = psk_words + step_words

        # wait - sort of equivalent to screen read time
        this_step, step_words = genStepWait(0, 3, 5, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern(
            "global dyn_options\ndyn_options = {'attention_area':[0.15, 0.15, 1, 1], 'attention_targets':['@all']}",
            "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "gmail", "top", "light",
                                                   this_step, None, "dyn_options")
        psk_words = psk_words + step_words


        this_step, step_words = genStepSearchAnchorInfo("screen_info", "protect_passwords", "direct", "anchor text", "any",
                                                        "win_popup", "win_popped", "gmail", False, this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepCheckCondition("win_popped", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "no_thanks", "anchor text",
                                                  "", 0,
                                                  "center", [0, 0], "box", 2, 2, [0, 0], this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words

        # after closing the windows pop up in case there is one, then click and key in password

        this_step, step_words = genStepCallExtern(
            "global dyn_options\ndyn_options = {'attention_area':[0.15, 0.15, 1, 1], 'attention_targets':['@all']}",
            "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "gmail", "top", "light",
                                                   this_step, None, "dyn_options")
        psk_words = psk_words + step_words


        this_step, step_words = genStepSearchAnchorInfo("screen_info", "your_passwords", "direct", "anchor text", "any",
                                                        "input_pw_box", "input_ready", "gmail", False, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("input_ready", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "your_passwords", "anchor text",
                                                  "", 0,
                                                  "bottom", [0, 2], "box", 2, 2, [0, 0], this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepTextInput("var", False, "gmail_pw", "direct", 0.05, "enter", 1, this_step)
        psk_words = psk_words + step_words

        # this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "next", "anchor text",
        #                                           "", 0, "center", [0, 0], "box", 2, 2, [0, 0], this_step)
        # psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words

        # this_step, step_words = genStepWebdriverKeyIn("web_driver", "pw_input_box", "gmail_pw", "action_result",
        #                                               "action_flag", this_step)
        # psk_words = psk_words + step_words
        #
        # # hit enter, which should initiate sign in process.
        # this_step, step_words = genStepWebdriverKeyIn("web_driver", "pw_input_box", "enter_key", "action_result",
        #                                               "action_flag", this_step)
        # psk_words = psk_words + step_words

        # double check for the sign of gmail home page:
        #
        # # Extract email elements
        # emails = driver.find_elements(By.CSS_SELECTOR, "tr.zA")  # Rows of emails
        #
        # print("\nExtracted Emails:\n")
        # for email in emails:
        #     try:
        #         sender = email.find_element(By.CSS_SELECTOR, "span.yP").text  # Sender
        #         subject = email.find_element(By.CSS_SELECTOR, "span.bqe").text  # Subject
        #         date = email.find_element(By.CSS_SELECTOR, "td.xW span").text  # Date
        #         print(f"Sender: {sender}\nSubject: {subject}\nDate: {date}\n")
        #     except Exception as e:
        #         print(f"Error extracting email: {e}")

        this_step, step_words = genStepWait(1, 0, 0, this_step)
        psk_words = psk_words + step_words

        # now there is a chance the chrome's auto save password popup could appear, if so, close it.

        this_step, step_words = genStepCallExtern(
            "global dyn_options\ndyn_options = {'attention_area':[0.15, 0.15, 1, 1], 'attention_targets':['@all']}",
            "", "in_line", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "gmail", "top", "light",
                                                   this_step, None, "dyn_options")
        psk_words = psk_words + step_words


        this_step, step_words = genStepSearchAnchorInfo("screen_info", "save_password", "direct", "anchor text", "any",
                                                        "save_password_pop", "save_ready", "gmail", False, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("save_ready", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "save_password", "anchor text",
                                                  "", 0,
                                                  "center", [0, 0], "box", 2, 2, [0, 0], this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words


        # now we should have entered gmail, but we might be prompted to do some house keeping stuff if long time no log in
        # passkeys_message = WebDriverWait(driver, 5).until(
        #         EC.presence_of_element_located((By.XPATH, "//div[contains(text(), 'With passkeys')]"))
        #     )
        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.XPATH,
                                                            "//div[contains(text(), 'With passkeys')]", True, "var",
                                                            "simplify_signin", "prompted_simplify_signin",
                                                            this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("prompted_simplify_signin", "", "", this_step)
        psk_words = psk_words + step_words

        # cancel_button = WebDriverWait(driver, 5).until(
        #         EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='Cancel']"))
        #     )
        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 10, "info_type", By.XPATH,
                                                            "//button[.//span[text()='Not now']]", False, "var",
                                                            "not_now_button",
                                                            "prompted_to_add_backup", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverClick("web_driver", "not_now_button", "action_result", "action_flag",
                                                      this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWait(1, 0, 0, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words


        # the 1st screen could be a prompt to complete backup contact info.
        # message_element = WebDriverWait(driver, 5).until(
        # # **Method 1: Locate by Class Name (Main Recovery Section)**
        #     recovery_section = WebDriverWait(driver, 5).until(
        #         EC.presence_of_element_located((By.CLASS_NAME, "PcQtJe"))
        #     )
        #  # **Method 2: Locate the 'Recovery information' text**
        #     recovery_text = driver.find_element(By.CLASS_NAME, "RY3zi")
        #     print(f"✅ Recovery text found: {recovery_text.text}")
        #
        #     # **Method 3: Locate 'Verify your phone number and email' div**
        #     verify_info = driver.find_element(By.CLASS_NAME, "Tg8Zdf")
        #     print(f"✅ Verify info text: {verify_info.text}")
        #
        #     # **Method 4: Locate "Learn more" button**
        #     learn_more_button = driver.find_element(By.XPATH, "//button[@aria-label='Learn more']")
        #     print("✅ 'Learn More' button detected!")
        #     learn_more_button.click()  # Click on the button
        #
        #     # **Method 5: Locate Email Address**
        #     email_address = driver.find_element(By.CLASS_NAME, "Fws9i")
        #     print(f"✅ Email detected: {email_address.text}")

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CLASS_NAME,
                                                            "Tg8Zdf", True, "var",
                                                            "verify_info", "prompted_to_add_backup", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CLASS_NAME,
                                                            "RY3zi", True, "var",
                                                            "prompted_to_add_backup", "prompted_to_add_backup", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("prompted_to_add_backup", "", "", this_step)
        psk_words = psk_words + step_words


        # cancel_button = WebDriverWait(driver, 5).until(
        #         EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='Cancel']"))
        #     )
        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 10, "info_type", By.XPATH,
                                                            "//button[.//span[text()='Not now']]", False, "var", "cancel_button",
                                                            "prompted_to_add_backup", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverClick("web_driver", "cancel_button", "action_result", "action_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWait(1, 0, 0, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words

        # the 2nd screen could be a prompt to complete account profile info, such as address etc.
        # message_element = WebDriverWait(driver, 5).until(
        #         EC.presence_of_element_located((By.CLASS_NAME, "NJXiZc"))
        #     )
        # home_address_section = WebDriverWait(driver, 5).until(
        #         EC.presence_of_element_located((By.XPATH, "//div[contains(text(), 'Add a home address')]"))
        #     )

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CLASS_NAME,
                                                            "NJXiZc", True, "var",
                                                            "message_element", "prompted_to_complete_acct_info", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.XPATH,
                                                            "//div[contains(text(), 'Add a home address')]", True, "var",
                                                            "home_address_section", "prompted_to_complete_acct_info", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("prompted_to_complete_acct_info", "", "", this_step)
        psk_words = psk_words + step_words



        # not_now_button = WebDriverWait(driver, 5).until(
        #         EC.element_to_be_clickable((By.XPATH, "//button[.//span[text()='Not now']]"))
        #     )
        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 10, "info_type", By.XPATH,
                                                            "//button[.//span[text()='Not now']]", False, "var", "not_now_button",
                                                            "prompted_to_complete_acct_info", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverClick("web_driver", "not_now_button", "action_result", "action_flag", this_step)
        psk_words = psk_words + step_words


        this_step, step_words = genStepWait(12, 0, 0, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words


        # now there is possibility of being asked to complete backup info, try to detect and skip it.
        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.CSS_SELECTOR,
                                                            "tr.zA", True, "var",
                                                            "emails", "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCheckCondition("not emails", "", "", this_step)
        psk_words = psk_words + step_words

        # set error flag somehow.
        this_step, step_words = genStepCallExtern("global run_stat\nrun_stat = 'Error: Unable to Sign into Gmail.'", "", "in_line", "",
                                                  this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsWinChromeGmailBrowserSignIn: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsWinChromeGmailBrowserSignIn: {ex_stat}")

    return this_step, psk_words


# once signed in, simply click on "Sent" box and click back on "Inbox",
# that's simplest refresh activity.
def genStepsWinChromeGmailBrowserRefresh(stepN):
    try:
        psk_words = ""
        this_step = stepN

        this_step, step_words = genStepCheckCondition("not emails", "", "", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWait(1, 0, 0, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("obj", "action_result", "NA", None, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("boolean", "action_flag", "NA", True, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCreateData("boolean", "extract_flag", "NA", True, this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepCallExtern("global info_type\ninfo_type= 'web element'", "", "in_line", "",
                                                  this_step)
        psk_words = psk_words + step_words

        # Find the "Sent" link
        # sent_element = driver.find_element(By.XPATH, "//span[@class='nU ']/a")
        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.XPATH,
                                                            "//span[@class='nU ']/a", False, "var", "sent_box",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWebdriverClick("web_driver", "sent_box", "action_result", "action_flag",
                                                      this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWait(6, 0, 0, this_step)
        psk_words = psk_words + step_words


        # now find inbox again and click on inbox.
        # inbox_element = WebDriverWait(driver, 10).until(
        #     EC.presence_of_element_located((By.XPATH, "//a[contains(@href, '#inbox')]"))
        # )
        # or alternatively, we can use this:
        # inbox_element = WebDriverWait(driver, 10).until(
        #     EC.presence_of_element_located((By.CLASS_NAME, "bsU"))  # Unread email count
        # )

        this_step, step_words = genStepWebdriverExtractInfo("web_driver", "var", "PAGE", 0, "info_type", By.XPATH,
                                                            "//a[contains(@href, '#inbox')]", False, "var", "in_box",
                                                            "extract_flag", this_step)
        psk_words = psk_words + step_words


        # this_step, step_words = genStepWebdriverKeyIn("web_driver", "in_box", "search_phrase", "action_result",
        #                                               "action_flag", this_step)
        # psk_words = psk_words + step_words
        #
        # this_step, step_words = genStepWait(3, 0, 0, this_step)
        # psk_words = psk_words + step_words



        # can fetch all emails if we like:
        # emails = driver.find_elements(By.CSS_SELECTOR, "tr.zA")  # Rows of emails
        #
        # print("\nExtracted Emails:\n")
        # for email in emails:
        #     try:
        #         sender = email.find_element(By.CSS_SELECTOR, "span.yP").text  # Sender
        #         subject = email.find_element(By.CSS_SELECTOR, "span.bqe").text  # Subject
        #         date = email.find_element(By.CSS_SELECTOR, "td.xW span").text  # Date
        #         print(f"Sender: {sender}\nSubject: {subject}\nDate: {date}\n")
        #     except Exception as e:
        #         print(f"Error extracting email: {e}")

        # button = driver.find_element(By.XPATH, "//div[contains(@class, 'T-I') and contains(@aria-label, 'Back to Inbox')]")

        this_step, step_words = genStepStub("end condition", "", "", this_step)
        psk_words = psk_words + step_words

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in genStepsWinChromeGmailBrowserRefresh: {traceback.format_exc()} {str(e)}"
        print(f"Error while generating genStepsWinChromeGmailBrowserRefresh: {ex_stat}")

    return this_step, psk_words
