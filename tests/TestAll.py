# tests will all be json file based, there will be a list file listing all tests case [{ case id:, case name:, description:, file location: } ...]
# each tests file will also be a json file.
# the field shall include: stub network responses.
# tests be mainly geared towards testing:
# 1) directly tests list/add/del/update bot,
#      A) add 300  bots.
#               manual add and check local saved files and local DB information.
#               add from json file.
#               tests bot with multi-platform/multi-role (each has a maturity level associated)
#      B) disable 20 bots.
#      C) delete  10 bots.
#      D) update  10 bots.
# 2) directly tests list/add/del/update mission
#      manual add 10 mission and check scheduling algorithm output.
#       manual assign missions to bot and assign mission run date-time?
#       tests mission-skill mapping relationship (a mission could require -multiple skills, work segments(each segment require a psk and csk)
#       add mission from json files
#       suspend mission.
#       delete mission.
#       modify mission - config only, (result/status will tested after the run)
# 3) tests fetch schedule.
# 4) tests work scheduler, tesk distribution to network, collect daily run results and send dail results back to cloud.
#        1 mission - on local machine
#        2 mission - on local machine (2 success/ 1 success, 1 failure/2failure)
#        3 mission - on local machine
#        1 mission - on remote machine
#        2 mission - on remote machine (2 success/ 1 success, 1 failure/2failure)
#        3 mission - on remote machine
#        1 mission - on local machine, 1 on remote machines , the one on local finishes first.
#        1 mission - on local machine, 1 on remote machines , the one on remote finishes first.
#       50 missions over machine capacity -  needs to see warning.
#        1 mission on local machine over 12am of local machine's timezone.
#        1 mission on local machine over 12am of remote machine's timezone.
#       manual buy mission prompt tests.
#       manual buy mission done and result update. (should all other results pend on this? could be part of setting to pend or not pend)
#
#
#
# 5) tests psk processing.....
#       ads_ebay_discord
#       chrome_etsy_discord
#       ads_amazon_buy
#
# 6) tests display.
#
#
#  7) account setting - payment situation/history, usage statistics, (work saving benefit statiscs).


# 6) tests skill editing GUI.





import unittest



class Tester():
    def __init__(self):
        super(Tester, self).__init__()
        self.type = "NA"

    def runAllTests(self):
        # load tests list file.
        print("hello")
        #run thru the list.

        #

