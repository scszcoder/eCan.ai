class FileResource:
    def __init__(self, homepath):
        self.bot_icon_path = homepath + '/resource/images/icons/c_robot64_1.png'
        self.sell_icon_path = homepath + '/resource/images/icons/c_robot64_0.png'
        self.buy_bot_icon_path = homepath + '/resource/images/icons/c_robot64_1.png'
        self.mission_icon_path = homepath + '/resource/images/icons/c_mission96_1.png'
        self.mission_success_icon_path = homepath + '/resource/images/icons/successful_launch0_48.png'
        self.mission_failed_icon_path = homepath + '/resource/images/icons/failed_launch0_48.png'
        self.skill_icon_path = homepath + '/resource/images/icons/skills_78.png'
        self.product_icon_path = homepath + '/resource/images/icons/product80_0.png'
        self.online_vehicle_icon_path = homepath + '/resource/images/icons/vehicle_192.png'
        self.offline_vehicle_icon_path = homepath + '/resource/images/icons/gray_vehicle_192.png'
        self.warn_vehicle_icon_path = homepath + '/resource/images/icons/warn_vehicle_192.png'
        self.commander_icon_path = homepath + '/resource/images/icons/general1_4.png'
        self.BOTS_FILE = homepath + "/resource/bots.json"
        self.MISSIONS_FILE = homepath + "/resource/missions.json"


class StaticResource:
    def __init__(self):
        self.PLATFORMS = ['windows', 'mac', 'linux']
        self.APPS = ['chrome', 'edge', 'firefox', 'ads', 'multilogin', 'safari', 'Custom']
        self.SITES = ['Amazon', 'Etsy', 'Ebay', 'Temu', 'Shein', 'Walmart', 'Wayfair', 'Tiktok', 'Facebook', 'Google',
                      'AliExpress', 'Custom']
        self.SITES_SH_DICT = {'Amazon': "amz", 'Etsy': "etsy", 'Ebay': "ebay", 'Temu': "temu", 'Shein': "shein",
                              'Walmart': "walmart", 'Wayfair': "wf", 'Tiktok': "tiktok", 'Facebook': "fb",
                              'Google': "google", 'AliExpress': 'ali'}
        self.SH_SITES_DICT = {'amz': "Amazon", 'etsy': "Etsy", 'ebay': "Ebay", 'temu': "Temu", 'shein': "Shein",
                              'walmart': "Walmart", 'wf': "Wayfair", 'tiktok': "Tiktok", 'fb': "Facebook",
                              'google': "Google", 'ali': 'AliExpress'}
        self.PLATFORMS_SH_DICT = {'windows': "win", 'mac': "mac", 'linux': "linux"}
        self.SH_PLATFORMS_DICT = {'win': "windows", 'mac': "mac", 'linux': "linux"}

        self.SM_PLATFORMS = ['WhatsApp', 'Messenger', 'Facebook', 'Instagram', 'Snap', 'Telegraph', 'Google', 'Line',
                             'Wechat', 'Tiktok', 'QQ', 'Custom']
        self.BUY_TYPES = ['buy', 'goodFB', 'badFB', 'goodRating', 'badRating', 'storeFB', 'storeRating', 'directFB']
        self.SUB_BUY_TYPES = ['addCart', 'pay', 'addCartPay', "checkShipping", 'rate', 'feedback', "checkFB"]
        self.SELL_TYPES = ['sellFullfill', 'sellRespond', 'sellPromote']
        self.SUB_SELL_TYPES = []
        self.OP_TYPES = ['opProcure', 'opPromote', 'opAccount', 'opCustom']
        self.SUB_OP_TYPES = []
        self.STATUS_TYPES = ['Unassigned', 'Assigned', 'Incomplete', 'Completed']
        self.BUY_STATUS_TYPES = ['Searched', 'InCart', 'Paid', 'Arrived', 'RatingDone', 'FBDone', 'RatingConfirmed',
                                 'FBConfirmed']
        self.PRODUCT_SEL_TYPES = ["ac", "op", "bs", "mr", "mhr", "cp", "cus"]

