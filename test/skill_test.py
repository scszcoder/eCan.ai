import unittest

from basicSkill import *
from genSkills import genWinTestSkill1, genWinTestSkill2
from config.app_settings import app_settings
from config.app_info import app_info
from readSkill import prepRunSkill


# 编写测试用例
class TestSkillFunction(unittest.TestCase):
    def test_processSearchWordline(self):
        # test_page0 = [{'name': 'paragraph', 'text': '5 6 7 8 9 10 \n', 'loc': (1870, 2938, 1892, 3254), 'type': 'info 1'}]
        test_page0 = [{'name': 'paragraph', 'text': '12345‘ \n', 'loc': (1869, 3426, 1914, 3747), 'type': 'info 1'}]
        symTab["test_page"] = test_page0
        symTab["tbs"] = "5"
        step = {
            "type": "Search Word Line",
            "screen": "test_page",
            "template_var": "tbs",
            "target_name": "paragraph",
            "target_type": "info 1",
            "site": "www.etsy.com",
            "result": "searchResult",
            "breakpoint": False,
            "status": "scrapeStat"
        }

        next_step = processSearchWordLine(step, 10)

    def test_process7z(self):
        symTab["exe_link"] = '7z'
        symTab["in_file"] = os.path.join(os.path.dirname(__file__), 'test_zip.zip')
        symTab["opath"] = app_info.app_home_path + '/runlogs/skills/test_zip'
        symTab["ovar"] = 'nothing'
        step = {
            "type": "Seven Zip",
            "action": "unzip",
            "var_type": "expr",
            "exe_var": "exe_link",
            "in_var": "in_file",
            "out_path": "opath",
            "out_var": "ovar",
            "result": "scrapeStat"
        }

        next_step = process7z(step, 10)
        print("done unzipping test....")

    def test_multi_skills(self):
        psk1 = app_info.app_resources_path + "/testdata/ut1sk1.psk"
        psk2 = app_info.app_resources_path + "/testdata/ut1sk2.psk"
        test_settings = {"skfname": psk1}
        # a test skill will be writen
        genWinTestSkill1(test_settings, 0)

        test_settings = {"skfname": psk2}
        # a test skill will be writen
        genWinTestSkill2(test_settings, 0)

        print("done generating skill============================>")
        skodes = [{"ns": "UT1SK1", "skfile": psk1}, {"ns": "UT1SK2", "skfile": psk2}]
        rpa_script = prepRunSkill(skodes)

        print("done all address gen.................")

        # set mission to be None, skill to be None, since we won't be testing extractInfo step.

        # test_m = EBMISSION()
        runAllSteps(rpa_script, None, None)

        print("done testing.................")


# 运行测试
if __name__ == '__main__':
    unittest.main()