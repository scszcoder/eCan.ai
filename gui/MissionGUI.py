import json
import traceback
import time

from bot.missions import TIME_SLOT_MINS, EBMISSION
from utils.logger_helper import logger_helper as logger


class MissionManager:
    """
    Mission Manager class that handles mission data and business logic
    without GUI components
    """

    def __init__(self, main_win):
        """
        Initialize MissionManager

        Args:
            main_win: Reference to main window
        """
        self.main_win = main_win
        self.homepath = main_win.homepath

        # Mission data
        self.newMission = EBMISSION(main_win)
        self.owner = None
        self.mode = "new"

        # Default values (previously from GUI components)
        self.selected_mission_platform = "Windows"
        self.selected_mission_app = "Chrome"
        self.selected_mission_app_link = ""
        self.selected_mission_site = "Amazon"
        self.selected_mission_site_link = ""
        self.selected_skill_action = "Browse"

        # Data storage (previously stored in GUI components)
        self.ticket_number = 0
        self.mission_id = 0
        self.bid = 0
        self.estimated_start_time = "00:00:00"
        self.estimated_run_time = 1
        self.retry_count = 3
        self.assignment_type = "manual"

        # Repeat configuration
        self.repeat_type = "none"
        self.repeat_number = 1
        self.repeat_unit = "second"
        self.repeat_on = "now"
        self.repeat_until = "2050-01-01"

        # Mission type configuration
        self.mission_type = "manage"
        self.buy_type = ""
        self.sell_type = ""

        # Private attributes (customer/product data)
        self.customer_id = ""
        self.customer_sm_id = ""
        self.customer_sm_platform = ""
        self.variations = ""
        self.follow_seller = ""
        self.follow_price = ""
        self.fingerprint_profile = ""
        self.asin = ""
        self.store = ""
        self.title = ""
        self.image_path = ""
        self.rating = 0.0
        self.feedbacks = 0
        self.price = 0.0

        # Search configuration
        self.search_kw = ""
        self.search_cat = ""

        # Pseudo data
        self.pseudo_store = ""
        self.pseudo_brand = ""
        self.pseudo_asin = ""

        # Skills management
        self.selected_skills = []  # List of skill IDs

        # Server configuration
        self.as_server = False

    def setMode(self, mode):
        """Set the mode of the mission manager"""
        self.mode = mode
        if self.mode == "new":
            current_time_nanoseconds = time.time_ns()
            current_time_milliseconds = current_time_nanoseconds // 1_000_000
            self.newMission.setTicket(current_time_milliseconds)
            self.ticket_number = current_time_milliseconds
            self.estimated_start_time = "01:00:00"
            self.estimated_run_time = 1
            # Clear skills for new mission
            self.selected_skills = []
        elif self.mode == "update":
            pass

    def setOwner(self, owner):
        """Set the owner of the mission"""
        self.owner = owner
        self.newMission.setOwner(owner)

    def getMonthNumber(self, mo):
        """Convert month name to number"""
        moTable = {
            "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
            "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"
        }
        return moTable.get(mo, "01")

    def getMonthString(self, mo):
        """Convert month number to name"""
        moTable = {
            "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr", "05": "May", "06": "Jun",
            "07": "Jul", "08": "Aug", "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec"
        }
        return moTable.get(mo, "Jan")

    def saveMission(self):
        """Save mission with all configured data"""
        self.main_win.showMsg("saving mission....")

        # Assignment type configuration
        if self.assignment_type == "manual":
            slots = 0
            runtime = 1
            if self.bid != self.newMission.getBid():
                self.newMission.setBid(self.bid)
                if self.estimated_start_time:
                    hours, minutes, seconds = map(int, self.estimated_start_time.split(':'))
                    total_minutes = hours * 60 + minutes
                    slots = int(total_minutes / TIME_SLOT_MINS) + 1
                    runtime = int(int(self.estimated_run_time) / (60 * TIME_SLOT_MINS)) + 1

                    self.newMission.setEstimatedStartTime(slots)
                    self.newMission.setEstimatedRunTime(runtime)

            self.newMission.setConfig(
                json.dumps({"bid": self.bid, "start_time": slots, "estRunTime": runtime}))
            self.newMission.setAssignmentType("manual")
        else:
            self.newMission.setAssignmentType("auto")
            self.newMission.setConfig("{}")

        # Retry configuration
        if self.retry_count:
            self.newMission.setRetry(self.retry_count)

        # Repeat configuration
        self.newMission.setRepeatType(self.repeat_type)
        self.newMission.setRepeatNumber(self.repeat_number)

        if self.repeat_type == "none":
            self.newMission.setRepeatUnit("second")
            self.repeat_on = "now"
        elif self.repeat_type == "by seconds":
            self.newMission.setRepeatUnit("second")
            self.repeat_on = "now"
            self.repeat_until = "2050-01-01"
        elif self.repeat_type == "by minutes":
            self.newMission.setRepeatUnit("minute")
        elif self.repeat_type == "by hours":
            self.newMission.setRepeatUnit("hour")
        elif self.repeat_type == "by days":
            self.newMission.setRepeatUnit("day")
        elif self.repeat_type == "by weeks":
            self.newMission.setRepeatUnit("week")
        elif self.repeat_type == "by months":
            self.newMission.setRepeatUnit("month")
        elif self.repeat_type == "by years":
            self.newMission.setRepeatUnit("year")

        if self.repeat_until:
            self.newMission.setRepeatUntil(self.repeat_until)

        self.newMission.addRepeatToConfig()

        # Mission type configuration
        if "buy" in self.mission_type or "browse" in self.mission_type:
            if self.buy_type == "browse":
                self.newMission.setMtype(self.buy_type)
            else:
                self.newMission.setMtype(self.buy_type)
        elif "sell" in self.mission_type:
            self.newMission.setMtype(self.sell_type)
        elif "manage" in self.mission_type:
            self.newMission.setMtype("manage")
        elif "hr" in self.mission_type:
            self.newMission.setMtype("hr")
        elif "finance" in self.mission_type:
            self.newMission.setMtype("finance")
        elif "legal" in self.mission_type:
            self.newMission.setMtype("legal")

        self.newMission.setBuyType(self.buy_type)
        self.newMission.setSellType(self.sell_type)

        # Private attributes
        self.newMission.privateAttributes.setItem(
            self.asin, self.store, self.title, self.image_path,
            self.rating, self.feedbacks, self.price
        )

        self.newMission.setCustomerID(self.customer_id)
        self.newMission.setFollowPrice(self.follow_price)
        self.newMission.setFollowSeller(self.follow_seller)
        self.newMission.setVariations(self.variations)
        self.newMission.setFingerPrintProfile(self.fingerprint_profile)
        self.newMission.setCustomerSMID(self.customer_sm_id)
        self.newMission.setCustomerSMPlatform(self.customer_sm_platform)

        # Search configuration
        self.newMission.pubAttributes.setSearch(self.search_kw, self.search_cat)

        # Platform/App/Site configuration
        platform_sh = self.main_win.translatePlatform(self.selected_mission_platform)
        app_sh = self.selected_mission_app
        site_sh = self.main_win.translateSiteName(self.selected_mission_site)

        self.newMission.setPlatform(self.selected_mission_platform)
        self.newMission.setApp(self.selected_mission_app)
        self.newMission.setSite(self.selected_mission_site)

        self.main_win.showMsg("Setting PAS:" + platform_sh + "," + app_sh + "," + site_sh)
        self.newMission.setCusPAS(platform_sh + "," + app_sh + "," + site_sh)

        # Skills
        self.fillSkills()

        self.newMission.updateDisplay()

        # Server configuration
        self.newMission.setAsServer(self.as_server)

        # Save to database
        if self.mode == "new":
            self.main_win.showMsg("adding new mission....")
            self.main_win.addNewMissions([self.newMission])
        elif self.mode == "update":
            self.main_win.showMsg("updating mission....")
            self.main_win.updateMissions([self.newMission])

        return self.newMission

    def fillSkills(self):
        """Convert selected skills to string format for storage"""
        sk_word = ""
        if self.selected_skills:
            for i, skid in enumerate(self.selected_skills):
                sk_word += str(skid)
                if i < len(self.selected_skills) - 1:
                    sk_word += ","

        self.main_win.showMsg("skills>>>>>" + sk_word)
        self.newMission.setSkills(sk_word)

    def loadSkills(self, mission):
        """Load skills from mission data"""
        print("all mission skills string:", mission.getMid(), mission.getSkills(), len(self.main_win.skills))

        if mission.getSkills().strip():
            all_skids = mission.getSkills().split(",")
            self.selected_skills = [int(skid.strip()) for skid in all_skids]
        else:
            self.selected_skills = []

    def setMission(self, mission):
        """Load mission data into manager"""
        try:
            print("filling mission data...")
            self.newMission = mission
            self.mission_id = mission.getMid()
            self.ticket_number = mission.getTicket()
            self.bid = mission.getBid()
            self.estimated_start_time = str(mission.getEstimatedStartTime())
            self.estimated_run_time = str(mission.getEstimatedRunTime())
            self.retry_count = mission.getRetry()

            # Load repeat configuration
            self.repeat_type = mission.getRepeatType()
            self.repeat_number = mission.getRepeatNumber()
            self.repeat_until = mission.getRepeatUntil()

            # Load mission type
            if "browse" in mission.getMtype() or "buy" in mission.getMtype():
                self.mission_type = "buy"
                self.buy_type = mission.getMtype().split("_")[0]
            elif "sell" in mission.getMtype():
                self.mission_type = "sell"
                self.sell_type = mission.getMtype().split("_")[0]
            elif "manage" in mission.getMtype():
                self.mission_type = "manage"
            elif "hr" in mission.getMtype():
                self.mission_type = "hr"
            elif "finance" in mission.getMtype():
                self.mission_type = "finance"
            elif "legal" in mission.getMtype():
                self.mission_type = "legal"

            # Load assignment type
            if mission.getAssignmentType() == "auto":
                self.assignment_type = "auto"

            # Load private attributes
            self.asin = mission.getASIN()
            self.store = mission.getStore()
            self.title = mission.getTitle()
            self.image_path = mission.getImagePath()
            self.rating = mission.getRating()
            self.feedbacks = mission.getFeedbacks()
            self.price = mission.getPrice()
            self.customer_id = mission.getCustomerID()
            self.customer_sm_id = mission.getCustomerSMID()
            self.variations = mission.getVariations()
            self.follow_seller = mission.getFollowSeller()
            self.follow_price = str(mission.getFollowPrice())
            self.fingerprint_profile = mission.getFingerPrintProfile()

            if mission.getCustomerSMPlatform():
                self.customer_sm_platform = mission.getCustomerSMPlatform()

            # Load search configuration
            self.search_kw = mission.getSearchKW()
            self.search_cat = mission.getSearchCat()

            # Load platform/app/site
            self.selected_mission_platform = mission.getPlatform()
            self.selected_mission_app = mission.getApp()
            self.selected_mission_site = mission.getSite()

            # Load server configuration
            self.as_server = mission.getAsServer()

            # Load skills
            self.loadSkills(mission)

        except Exception as e:
            logger.debug(f"Error setting mission: {e}")
            traceback.print_exc()

    # Data management methods
    def setPlatform(self, platform):
        """Set mission platform"""
        self.selected_mission_platform = platform

    def setApp(self, app):
        """Set mission app"""
        self.selected_mission_app = app

    def setSite(self, site):
        """Set mission site"""
        self.selected_mission_site = site

    def setMissionType(self, mission_type):
        """Set mission type"""
        self.mission_type = mission_type

    def setAssignmentType(self, assignment_type):
        """Set assignment type"""
        self.assignment_type = assignment_type

    def setBid(self, bid):
        """Set bot ID"""
        self.bid = bid

    def setEstimatedStartTime(self, start_time):
        """Set estimated start time"""
        self.estimated_start_time = start_time

    def setEstimatedRunTime(self, run_time):
        """Set estimated run time"""
        self.estimated_run_time = run_time

    def setRetryCount(self, retry_count):
        """Set retry count"""
        self.retry_count = retry_count

    def setRepeatConfig(self, repeat_type, repeat_number, repeat_until):
        """Set repeat configuration"""
        self.repeat_type = repeat_type
        self.repeat_number = repeat_number
        self.repeat_until = repeat_until

    def setSearchConfig(self, search_kw, search_cat):
        """Set search configuration"""
        self.search_kw = search_kw
        self.search_cat = search_cat

    def setPrivateAttributes(self, customer_id, customer_sm_id, customer_sm_platform,
                           variations, follow_seller, follow_price, fingerprint_profile,
                           asin, store, title, image_path, rating, feedbacks, price):
        """Set private attributes"""
        self.customer_id = customer_id
        self.customer_sm_id = customer_sm_id
        self.customer_sm_platform = customer_sm_platform
        self.variations = variations
        self.follow_seller = follow_seller
        self.follow_price = follow_price
        self.fingerprint_profile = fingerprint_profile
        self.asin = asin
        self.store = store
        self.title = title
        self.image_path = image_path
        self.rating = rating
        self.feedbacks = feedbacks
        self.price = price

    def setSkills(self, skills):
        """Set selected skills"""
        self.selected_skills = skills

    def addSkill(self, skill_id):
        """Add a skill to selected skills"""
        if skill_id not in self.selected_skills:
            self.selected_skills.append(skill_id)

    def removeSkill(self, skill_id):
        """Remove a skill from selected skills"""
        if skill_id in self.selected_skills:
            self.selected_skills.remove(skill_id)

    def setAsServer(self, as_server):
        """Set server mode"""
        self.as_server = as_server

    # Getter methods
    def getMission(self):
        """Get current mission object"""
        return self.newMission

    def getSelectedSkills(self):
        """Get selected skills"""
        return self.selected_skills.copy()

    def getMissionData(self):
        """Get all mission data as dictionary"""
        return {
            'platform': self.selected_mission_platform,
            'app': self.selected_mission_app,
            'site': self.selected_mission_site,
            'mission_type': self.mission_type,
            'assignment_type': self.assignment_type,
            'bid': self.bid,
            'estimated_start_time': self.estimated_start_time,
            'estimated_run_time': self.estimated_run_time,
            'retry_count': self.retry_count,
            'repeat_type': self.repeat_type,
            'repeat_number': self.repeat_number,
            'repeat_until': self.repeat_until,
            'search_kw': self.search_kw,
            'search_cat': self.search_cat,
            'customer_id': self.customer_id,
            'customer_sm_id': self.customer_sm_id,
            'customer_sm_platform': self.customer_sm_platform,
            'variations': self.variations,
            'follow_seller': self.follow_seller,
            'follow_price': self.follow_price,
            'fingerprint_profile': self.fingerprint_profile,
            'asin': self.asin,
            'store': self.store,
            'title': self.title,
            'image_path': self.image_path,
            'rating': self.rating,
            'feedbacks': self.feedbacks,
            'price': self.price,
            'selected_skills': self.selected_skills,
            'as_server': self.as_server
        }


# Legacy GUI classes - kept for compatibility but deprecated
class SkillListView:
    """Legacy SkillListView class - deprecated, use MissionManager instead"""
    def __init__(self, mission_win):
        self.mission_win = mission_win
        self.homepath = mission_win.homepath
        self.selected_row = None


class MWORKSKILL:
    """Legacy MWORKSKILL class - deprecated, use MissionManager instead"""
    def __init__(self, homepath, platform, app, applink, site, sitelink, action):
        self.platform = platform
        self.app = app
        self.applink = applink
        self.site = site
        self.homepath = homepath
        self.sitelink = sitelink
        self.action = action
        self.name = platform + "_" + app + "_" + site + "_" + action

        self.setText(self.name)

    def getData(self):
        return self.platform, self.app, self.applink, self.site, self.sitelink, self.action

    def setText(self, text):
        self.text = text


class CustomDelegate:
    """Legacy CustomDelegate class - deprecated, use MissionManager instead"""
    def __init__(self, mission_win):
        self.mission_win = mission_win

    def initStyleOption(self, option, index):
        # Check the item's text for customization
        item_text = index.data()
        # if item_text == "5" or item_text == "11":
        if self.mission_win.checkIsMain(item_text):
            option.font.setBold(True)


# MissionNewWin class has been replaced with MissionManager
# The GUI components have been removed and only business logic is retained
# See MissionManager class above for the replacement implementation