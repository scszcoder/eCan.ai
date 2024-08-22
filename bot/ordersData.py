class OrderPerson:
    def __init__(self, buyer_id, role, full_name, street1, city, state, zip, street2="", phone="", email=""):
        self.fn = ""
        self.mn = ""
        self.ln = ""
        self.suffix = ""
        self.full_name = full_name
        self.id = buyer_id
        self.street1 = street1
        self.street2 = street2
        self.street3 = ""
        self.city = city
        self.state = state
        self.zip = zip
        self.country = "USA"
        self.phone = phone
        self.email = email
        self.role = role

    def setStreet1(self, str1):
        self.street1 = str1

    def setStreet2(self, str2):
        self.street2 = str2

    def setStreet3(self, str3):
        self.street3 = str3

    def setCity(self, city):
        self.city = city

    def setState(self, state):
        self.state = state

    def setZip(self, zipcode):
        self.zip = zipcode

    def setCountry(self, country):
        self.country = country

    def setId(self, bid):
        self.id = bid

    def setFullName(self, fullname):
        self.full_name = fullname

    def setPhone(self, phone):
        self.phone = phone

    def setRole(self, role):
        self.role = role

    def toJson(self):
        return {
            "full_name": self.full_name,
            "id": self.id,
            "street1": self.street1,
            "street2": self.street2,
            "city": self.city,
            "state": self.state,
            "zip": self.zip,
            "phone": self.phone
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
        self.label_file = ""

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

    def setLabelFileName(self, label):
        self.label_file = label

    def getLabelFileName(self):
        return self.label_file

    def setLabelNote(self, note):
        self.label_note = note

    def getLabelNote(self):
        return self.label_note

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

class OrderedProduct:
    def __init__(self, pid, ptitle, price, quantity):
        self.pid = pid
        self.ptitle = ptitle
        self.price = price
        self.quantity = quantity
        self.variations = {}

    def setPid(self, pid):
        self.pid = pid

    def getPid(self):
        return self.pid

    def getPTitle(self):
        return(self.ptitle)

    def setPTitle(self, ptitle):
        self.ptitle = ptitle

    def setPrice(self, price):
        self.price = price

    def getPrice(self):
        return self.price

    def setQuantity(self, q):
        self.quantity = q

    def getQuantity(self):
        return self.quantity

    def addVariation(self, var):
        self.variations[var[0]] = var[1]

    def getVariations(self):
        return self.variations

    def toJson(self):
        return {
            "pid": self.pid,
            "ptitle": self.ptitle,
            "price": self.price,
            "quantity": self.quantity,
            "variations": self.variations
        }



class ORDER:
    def __init__(self, oid, products, buyer, recipient, shipping, status, createdOn):
        self.oid = oid
        self.products = products    #[{"pid":***, "pname":****, "quantity":***, "price":***}...]
        self.total_price = 0.0
        self.total_quantity = 0
        self.paid_date = ""
        self.buyer = buyer
        self.recipient = recipient
        self.shipping = shipping
        self.status = status
        self.createdOn = createdOn
        self.total_weight = 0           # in ozs
        self.total_length = 0           # in inches
        self.total_width = 0
        self.total_height = 0
        self.ui_checked = False
        self.combined_oids=[]


    def setOid(self, oid):
        self.oid = oid

    def getOid(self):
        return self.oid

    def combineOid(self, oid):
        self.combined_oids.append(oid)

    def getCombinedOids(self):
        return self.combined_oids

    def setBuyer(self, buyer):
        self.buyer = buyer

    def setRecipient(self, recipient):
        self.recipient = recipient

    def getProducts(self):
        return self.products

    def getProductTitles(self):
        return [p.getPTitle() for p in self.products]

    def setProducts(self, pds):
        self.products = pds
        if pds[0].getPrice() != "":
            self.total_price = sum(float(pd.getPrice()) * int(pd.getQuantity()) for pd in pds)

    def setShipping(self, shipping):
        self.shipping = shipping

    def getRecipientName(self):
        return self.recipient.full_name

    def setRecipientName(self, fn):
        self.recipient.full_name = fn

    def getRecipientAddrState(self):
        return self.recipient.state

    def setRecipientAddrState(self, state):
        self.recipient.state = state

    def getRecipientAddrZip(self):
        return self.recipient.zip

    def setRecipientAddrZip(self, zip):
        self.recipient.zip = zip

    def getRecipientAddrCity(self):
        return self.recipient.city

    def setRecipientAddrCity(self, city):
        self.recipient.city = city

    def getRecipientAddrStreet1(self):
        return self.recipient.street1

    def setRecipientAddrStreet1(self, st1):
        self.recipient.street1 = st1

    def getRecipientAddrStreet2(self):
        return self.recipient.street2

    def setRecipientAddrStreet2(self, st2):
        self.recipient.street2 = st2

    def getRecipientPhone(self):
        return self.recipient.phone

    def getOrderWeightInOzs(self, product_book):
        self.total_weight = 0
        for p in self.products:
            found = next((x for x in product_book if x["title"] == p.getPTitle()), None)
            if found:
                self.total_weight = self.total_weight + found["weight"]*16*int(p.getQuantity())

        self.total_weight = self.total_weight + 3               #3oz as the container weight
        return self.total_weight

    def getOrderWeightInLbs(self, product_book):
        self.total_weight = 0
        for p in self.products:
            found = next((x for x in product_book if x["title"] == p.getPTitle()), None)
            if found:
                self.total_weight = self.total_weight + found["weight"]*int(p.getQuantity())

        self.total_weight = self.total_weight + 3           # 3oz as the container weight
        # if self.total_weight >= 16:
        #     self.total_weight = self.total_weight * 1.2     # for heavy item, add 20% extra weight as container weight.

        # return int(self.total_weight/16)
        return self.total_weight

    def getOrderLengthInInches(self, product_book):
        all_len = []
        for p in self.products:
            found = next((x for x in product_book if x["title"] == p.getPTitle()), None)
            if found:
                all_len.append(found["dimension"][0]*int(p.getQuantity()))

        self.total_length = max(all_len) + 5
        return self.total_length

    def getOrderWidthInInches(self, product_book):
        all_wid = []
        for p in self.products:
            found = next((x for x in product_book if x["title"] == p.getPTitle()), None)
            if found:
                all_wid.append(found["dimension"][1])

        self.total_width = max(all_wid) + 5
        return self.total_width

    def getOrderHeightInInches(self, product_book):
        all_hei = []
        for p in self.products:
            found = next((x for x in product_book if x["title"] == p.getPTitle()), None)
            if found:
                all_hei.append(found["dimension"][2])

        self.total_height = max(all_hei) + 5
        return self.total_height


    def setTotalPrice(self, tp):
        self.total_price = tp

    def setTotalQuantity(self, tq):
        self.total_quantity = tq

    def setCreationDate(self, odate):
        self.createdOn = odate

    def setPaidDate(self, pd):
        self.paid_date = pd
    def setStatus(self, status):
        self.status = status

    def getStatus(self):
        return self.status

    def getChecked(self):
        return self.ui_checked

    def setChecked(self, status):
        self.ui_checked = status

    def getShipping(self):
        return self.shipping

    def getShippingService(self):
        return self.shipping.service

    def setShippingService(self, serv):
        self.shipping.service = serv

    def getShippingTracking(self):
        return self.shipping.tracking

    def setShippingTracking(self, tc):
        self.shipping.tracking = tc


    def toJson(self):
        return {
            "oid": self.oid,
            "buyer": "",
            "recipient": self.recipient.toJson(),
            "products": [p.toJson() for p in self.products],
            "shipping": self.shipping.toJson(),
            "total_price": self.total_price,
            "createOn": self.createdOn,
            "status": self.status
        }