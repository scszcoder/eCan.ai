class Buyer:
    def __init__(self, buyer_id, full_name, street1, city, state, zip, street2=""):
        self.fn = ""
        self.mn = ""
        self.ln = ""
        self.suffix = ""
        self.full_name = full_name
        self.id = buyer_id
        self.street1 = street1
        self.street2 = street2
        self.city = city
        self.state = state
        self.zip = zip

    def setStreet1(self, str1):
        self.street1 = str1

    def setStreet2(self, str2):
        self.street2 = str2

    def setCity(self, city):
        self.city = city

    def setState(self, state):
        self.state = state

    def setZip(self, zipcode):
        self.zip = zipcode

    def setId(self, bid):
        self.id = bid

    def setFullName(self, fullname):
        self.full_name = fullname

    def toJson(self):
        return {
            "full_name": self.full_name,
            "id": self.id,
            "street1": self.street1,
            "street2": self.street2,
            "city": self.city,
            "state": self.state,
            "zip": self.zip
        }

class Shipping:
    def __init__(self, vendor, service, tracking, price=0, disti="", disti_site="", dimension = [9, 6, 3], weight = 1.0):
        self.vendor = vendor
        self.service = service
        self.tracking = tracking
        self.price = price
        self.disti = disti
        self.disti_site = disti_site
        self.dimension_inches = dimension                  # inches
        self.weight_lbs = weight                        # lbs
        self.status = ""

    def setVendor(self, vendor):
        self.vendor = vendor

    def setService(self, service):
        self.service = service

    def setTracking(self, tracking):
        self.tracking = tracking

    def setPrice(self, price):
        self.price = price

    def setDisti(self, disti):
        self.disti = disti

    def setDistiSite(self, disti_site):
        self.disti_site = disti_site

    def setDimension(self, dimension):
        self.dimension_inches = dimension

    def setWeight(self, weight):
        self.weight_lbs = weight

    def setStatus(self, status):
        self.status = status

    def toJson(self):
        return {
            "vendor": self.vendor,
            "service": self.service,
            "tracking": self.tracking,
            "price": self.price,
            "disti": self.disti,
            "disti_site": self.disti_site,
            "dimension_inches": self.dimension_inches,
            "weight_lbs": self.weight_lbs,
            "status": self.status
        }

class OrderedProducts:
    def __init__(self, pid, ptitle, price, quantity):
        self.pid = pid
        self.ptitle = ptitle
        self.price = price
        self.quantity = quantity

    def setPid(self, pid):
        self.pid = pid

    def getPid(self):
        return self.pid

    def setPtitle(self, ptitle):
        self.ptitle = ptitle

    def getPtitle(self):
        return self.ptitle

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
            "ptitle": self.ptitle,
            "price": self.price,
            "quantity": self.quantity
        }

class ORDER:
    def __init__(self, oid, products, buyer, shipping, status, createdOn):
        self.oid = oid
        self.products = products    #[{"pid":***, "pname":****, "quantity":***, "price":***}...]
        self.total_price = 0.0
        self.buyer = buyer
        self.shipping = shipping
        self.status = status
        self.createdOn = createdOn

    def setOid(self, oid):
        self.oid = oid

    def setBuyer(self, buyer):
        self.buyer = buyer

    def setProducts(self, pds):
        self.products = pds
        self.total_price = sum(float(pd.getPrice()) * int(pd.getQuantity()) for pd in pds)

    def setShipping(self, shipping):
        self.shipping = shipping

    def setTotalPrice(self, tp):
        self.total_price = tp

    def setCreationDate(self, odate):
        self.createdOn = odate

    def setStatus(self, status):
        self.status = status

    def toJson(self):
        return {
            "oid": self.oid,
            "buyer": self.buyer.toJson(),
            "products": [p.toJson() for p in self.products],
            "shipping": self.shipping.toJson(),
            "total_price": self.total_price,
            "createOn": self.createdOn,
            "status": self.status
        }