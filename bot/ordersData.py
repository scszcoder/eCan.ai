class Buyer:
    def __init__(self, full_name, street1, city, state, zip, street2="", street3=""):
        self.fn = ""
        self.mn = ""
        self.ln = ""
        self.suffix = ""
        self.full_name = full_name
        self.street1 = street1
        self.street2 = street2
        self.street3 = street3
        self.city = city
        self.state = state
        self.zip = zip


    def toJson(self):
        return {
            "short_name": self.short_name,
            "summery": self.summery.toJson(),
            "reviews": self.reviewsToJson(),
            "qas": self.qasToJson(),
            "point_summery": self.point_summery,
            "description": self.description,
            "start_date": self.start_date,
            "department": self.department,
            "ranks": self.ranks,
            "dimensions": self.dimensions,
            "weight": self.weight
        }

class Shipping:
    def __init__(self, vendor, service, tracking, price=0, disti="", disti_site=""):
        self.vendor = vendor
        self.service = service
        self.tracking = tracking
        self.price = price
        self.disti = disti
        self.disti_site = disti_site
        self.status = ""


    def toJson(self):
        return {
            "short_name": self.short_name,
            "summery": self.summery.toJson(),
            "reviews": self.reviewsToJson(),
            "qas": self.qasToJson(),
            "point_summery": self.point_summery,
            "description": self.description,
            "start_date": self.start_date,
            "department": self.department,
            "ranks": self.ranks,
            "dimensions": self.dimensions,
            "weight": self.weight
        }

class OrderedProducts:
    def __init__(self, pid, pname, price, quantity):
        self.pid = pid
        self.pname = pname
        self.price = price
        self.quantity = quantity

    def setPid(self, pid):
        self.pid = pid

    def getPid(self):
        return self.pid

    def setPname(self, pname):
        self.pname = pname

    def getPname(self):
        return self.pname

    def setPrice(self, price):
        self.price = price

    def getPrice(self):
        return self.price

    def setQuantity(self, q):
        self.quantity = q

    def getQuantity(self):
        return self.quantity

    def toJson(self):
        return {
            "pid": self.pid,
            "pname": self.pname,
            "price": self.price,
            "quantity": self.quantity
        }

class ORDER:
    def __init__(self, oid, products, buyer, shipping, status, createdOn):
        self.oid = oid
        self.products = products    #[{"pid":***, "pname":****, "quantity":***, "price":***}...]
        self.price = 0.0
        self.buyer = buyer
        self.shipping = shipping
        self.status = status
        self.createdOn = createdOn

    def setPid(self, pid):
        self.pid = pid

    def setReviews(self, rvs):
        self.reviews = rvs

    def setQAs(self, qas):
        self.qas = qas

    def set7pts(self, pt7):
        self.point_summery = pt7

    def setRanks(self, ranks):
        self.ranks = ranks

    def setSizeWeight(self, size, weight):
        self.dimensions = size
        self.weight = weight

    def setDescription(self, des):
        self.description = des

    def setStartDate(self, sdt):
        self.start_date = sdt

    def setDepartment(self, dept):
        self.department = dept

    def qasToJson(self):
        qas = []
        for qa in self.qas:
            qas.append(qa.toJson())
        return qas

    def reviewsToJson(self):
        rvs = []
        for rv in self.reviews:
            rvs.append(rv.toJson())
        return rvs

    def toJson(self):
        return {
            "short_name": self.short_name,
            "summery": self.summery.toJson(),
            "reviews": self.reviewsToJson(),
            "qas": self.qasToJson(),
            "point_summery": self.point_summery,
            "description": self.description,
            "start_date": self.start_date,
            "department": self.department,
            "ranks": self.ranks,
            "dimensions": self.dimensions,
            "weight": self.weight
        }