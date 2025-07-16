import time
from selenium import webdriver
from bot.seleniumSkill import *
from agent.ec_skills.dom.dom_utils import *

def load_build_dom_tree_script():
    script = ""
    try:
        build_dom_tree_script_path = "c:/users/songc/pycharmprojects/ecbot/agent/ec_skills/dom/buildDomTree.js"
        print("Loading build dom tree script...", build_dom_tree_script_path)
        with open(build_dom_tree_script_path, 'r', encoding='utf-8') as file:
            script = file.read()
        return script
    except FileNotFoundError:
        print(f"Error: The file {build_dom_tree_script_path} was not found.")
        return ""
    except IOError as e:
        print(f"Error reading {build_dom_tree_script_path}: {e}")
        return ""

def scrape_tests(url=""):
    if not url:
        # url = "https://www.digikey.com/en/products/filter/tantalum-polymer-capacitors/70"
        # url = "https://www.mouser.com/c/connectors/ic-component-sockets/"
        # url = "https://www.avnet.com/americas/products/c/power-management/"
        # # url = "https://eshop.wpgam.com/"   # no parametric filters
        url = "https://www.arrow.com/en/categories/connectors/io-connectors/connector-circular"
        # url = "https://www.futureelectronics.com/c/semiconductors/analog--regulators-reference--linear-regulators/products"
        # url = "https://www.sager.com/category/sensors-and-transducers-magnetic-sensors/0000000526"
        # url = "https://www.tti.com/content/ttiinc/en/apps/part-search.html?c=circuit-protection/esd-protection-diodes-tvs-diodes"
        #
        # url = "https://us.rs-online.com/motors-motor-controls/dc-motor-controllers/?page=1"
        # url = "https://www.fusionww.com/shop/catalog/1072/laser-products"
        # url = "https://newpowerww.com/products/"
        # url = "https://www.newark.com/c/switches-relays/relays/power-relays"
        #
        # url = "https://www.microchip.com/en-us/parametric-search.html/980?filters=JTdCJTIyY2F0ZWdvcnlkcm9wZG93biUyMiUzQSU1QiUyMk1pY3JvY29udHJvbGxlcnMlMjBBbmQlMjBQcm9jZXNzb3JzJTIyJTJDJTIyQWxsJTIwTWljcm9jb250cm9sbGVycyUyMGFuZCUyME1pY3JvcHJvY2Vzc29ycyUyMiUyQyUyMiUyMiU1RCU3RA=="
        # url = "https://www.ti.com/power-management/acdc-dcdc-converters/products.html"
        # url = "https://www.analog.com/en/parametricsearch/12823#/"
        # url = "https://www.monolithicpower.com/en/products/power-management/switching-converters-controllers/step-down-buck/converters/vin-max-19v-to-29v.html"

        # # cn ones.
        # url = "https://ceaci.cecport.com/products"
        # url = "http://www.techtronics.com.hk/index.php/Home/Product/index.html"
        # url = "https://www.ufct.com/list_12.aspx?cid=5"
        # url = "https://comtech.cn/product/product_fenlei"


    # scrape the dom tree
    driver_path = "c:/users/songc/pycharmprojects/ecbot/chromedriver-win64/v138.0.7204.157/chromedriver.exe"
    port = 9228  # this is the port number used when start chrome from win power shell command line. with debug mode on
    web_driver = webDriverStartExistingChrome(driver_path, port)


    web_driver.get(url)  # Replace with the new URL
    print("opened URL: " + url)
    time.sleep(3)
    script = load_build_dom_tree_script()
    # print("dom tree build script to be executed", script)
    target = None
    domTree = execute_js_script(web_driver, script, target)
    with open("domtree.json", 'w', encoding="utf-8") as dtjf:
        json.dump(domTree, dtjf, ensure_ascii=False, indent=4)
        # self.rebuildHTML()
        dtjf.close()

    print("dom tree:", type(domTree), domTree.keys())
    top_level_nodes = find_top_level_nodes(domTree)
    print("top level nodes:", type(top_level_nodes), top_level_nodes)
    top_level_texts = get_shallowest_texts(top_level_nodes, domTree)
    tls = collect_text_nodes_by_level(domTree)
    print("level texts:", tls)
    print("level N texts:", [len(tls[i]) for i in range(len(tls))])
    for l in tls:
        if l:
            print("level texts:", [domTree["map"][nid]["text"] for nid in l])

    sects = sectionize_dt_with_subsections(domTree)
    print("sections:", sects)
    test_result = "success"
    return test_result