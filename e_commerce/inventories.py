import json
from utils.logger_helper import logger_helper as logger
# from utils.logger_helper import get_traceback


class INV_PRODUCT:
    def __init__(self):
        self.short_name = ""
        self.title = ""
        self.asin = ""
        self.weight_in_lbs = 0
        self.dimension_in_inches = [0, 0, 0]
        self.variation = ""
        self.state = "new"
        self.availability = []

    def getTitle(self):
        return self.title

    def getWeight(self):
        return self.weight_in_lbs

    def getDimensions(self):
        return self.dimension_in_inches

    def getAsin(self):
        return self.asin

    def setJsonData(self, dj):
        self.short_name = dj["name"]
        self.title = dj["title"]
        self.asin = dj["asin"]
        self.variation = dj["variation"]
        self.weight_in_lbs = dj["weight"]
        self.dimension_in_inches = dj["dimension"]
        self.state = dj["state"]
        self.availability = dj["inventory"]

    def genJson(self):
        jd = {
            "name": self.short_name,
            "title": self.title,
            "asin": self.asin,
            "variation": self.variation,
            "weight": self.weight_in_lbs,
            "dimension": self.dimension_in_inches,
            "state": self.state,
            "inventory": self.availability
        }
        return jd


class INVENTORY:
    def __init__(self):
        self.seller = ""
        self.allowed_bids = []
        self.products = []

    def addProduct(self, prod):
        self.products.append(prod)

    def getAllowedBids(self):
        logger.debug("geting allowed BID:"+json.dumps(self.allowed_bids))
        return self.allowed_bids

    def getSeller(self):
        return self.seller

    def getProducts(self):
        return self.products

    def setJsonData(self, dj):
        self.seller = dj.get("seller", "")
        self.allowed_bids = dj.get("allowed_bots", [])
        for p in dj.get("products", []):
            new_prod = INV_PRODUCT()
            new_prod.setJsonData(p)
            self.products.append(new_prod)

    def genJson(self):
        jd = {
                "seller": self.pseudo_nick_name,
                "allowed_bots": self.location,
                "products": []
            }

        for p in self.products:
            jd["products"].append(p.genJson())

        return jd

