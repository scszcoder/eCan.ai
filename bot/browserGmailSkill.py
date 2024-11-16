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

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    # assume profile file is ready.
    this_step, step_words = genStepCallExtern("global gmail_acct\ngmail_acct = fin[0]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global gmail_pw\ngmail_pw = fin[1]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepsChromeRefreshGMailSkill(worksettings, this_step, theme)
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

    this_step, step_words = genStepCallExtern("global gmail_pw\ngmail_pw = fin[1]", "", "in_line", "", this_step)
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