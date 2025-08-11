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
import os
import sys



class Tester():
    def __init__(self):
        super(Tester, self).__init__()
        self.type = "NA"

    def runAllTests(self):
        """Discover and run all tests under the tests/ directory matching test_*.py"""
        start_dir = os.path.dirname(__file__)
        # Ensure project root is on sys.path so 'ota' and other top-level modules can be imported
        project_root = os.path.dirname(start_dir)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        print(f"Discovering tests in: {start_dir} (project_root={project_root})")
        suite = unittest.defaultTestLoader.discover(start_dir=start_dir, pattern='test_*.py')
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    tester = Tester()
    code = tester.runAllTests()
    sys.exit(code)

