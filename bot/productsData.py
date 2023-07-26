
class PRODUCT_REVIEW:
    def __init__(self):
        self.reviewer = ''
        self.title = ''
        self.score = ''
        self.body = ''
        self.date = ''
        self.num_helpful = 0


    def setTitle(self, rt):
        self.title = rt

    def setReviewer(self, rver):
        self.reviewer = rver

    def setBody(self, body):
        self.body = body

    def setHelpful(self, nh):
        self.num_helpful = nh

    def setScore(self, score):
        self.score = score

    def setDate(self, dt):
        self.date = dt

    def toJson(self):
        return {
            "title": self.title,
            "reviewer": self.reviewer,
            "body": self.body,
            "num_helpful": self.num_helpful,
            "score": self.score,
            "date": self.date
        }

class PRODUCT_ANSWER:
    def __init__(self):
        self.answerer = ''
        self.date = ''
        self.answer = ''

    def setAuthor(self, author):
        self.answerer = author

    def setADate(self, dt):
        self.date = dt

    def setAnswer(self, ans):
        self.answer = ans

    def toJson(self):
        return {
            "answerer": self.answerer,
            "date": self.date,
            "answer": self.answer
        }


class PRODUCT_QA:
    def __init__(self):
        self.question = ''
        self.answers = []
        self.num_votes = 0

    def setQ(self, qes):
        self.question = qes

    def setVotes(self, nv):
        self.num_votes = nv

    def setA(self, ans):
        self.answers = ans

    def answersToJson(self):
        answs = []
        for answ in self.answers:
            answs.append(answ.toJson())
        return answs

    def toJson(self):
        return {
            "question": self.question,
            "num_votes": self.num_votes,
            "answers": self.answersToJson()
        }


class PRODUCT_SUMMERY:
    def __init__(self):
        self.title = ''
        self.brand = ''
        self.store = ''
        self.asin = ''
        self.image = ''
        self.bs = False
        self.ac = False
        self.score = 0
        self.feedbacks = 0
        self.price = 0
        self.weekly_sales = 0
        self.free_delivery = False
        self.badges = []

    def setTitle(self, tt):
        self.title = tt

    def setBrand(self, brand):
        self.brand = brand

    def setWeekSales(self, ws):
        self.weekly_sales = ws

    def setStore(self, st):
        self.store = st

    def setASIN(self, asin):
        self.asin = asin

    def setImage(self, img):
        self.image = img

    def setScore(self, score):
        self.score = score

    def setFeedbacks(self, nfbs):
        self.feedbacks = nfbs

    def setPrice(self, price):
        self.price = price

    def addBadge(self, badge):
        self.badges.append(badge)
        if badge == "Best Seller":
            self.bs = True
        elif badge == "Amazon's Choice":
            self.ac = True

    def getBadges(self):
        return self.badges

    def getBSStat(self):
        return self.bs

    def getACStat(self):
        return self.ac

    def setFreeDelivery(self, fd):
        self.free_delivery = fd

    def toJson(self):
        return {
            "title": self.title,
            "brand": self.brand,
            "store": self.store,
            "asin": self.asin,
            "image": self.image,
            "ac": self.ac,
            "bs": self.bs,
            "score": self.score,
            "feedbacks": self.feedbacks,
            "price": self.price,
            "badges": self.badges,
            "weekly_sales": self.weekly_sales,
            "free_delivery": self.free_delivery
        }


class PRODUCT:
    def __init__(self, name=''):
        self.short_name = name
        self.summery = None
        self.reviews = []
        self.qas = []
        self.point_summery = []     #amazon's 7 bullet points description.
        self.description = ""
        self.start_date = ""
        self.department = ""
        self.ranks = []
        self.dimensions = ""
        self.weight = ""

    def setSummery(self, summery):
        self.summery = summery

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