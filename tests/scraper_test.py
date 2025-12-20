
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


dtfs = [
    "c:/users/songc/pycharmprojects/ecbot/domtree_adi.json",
    "c:/users/songc/pycharmprojects/ecbot/domtree_arrow.json",
    "c:/users/songc/pycharmprojects/ecbot/domtree_avnet.json",
    "c:/users/songc/pycharmprojects/ecbot/domtree_cirruslogic.json",
    "c:/users/songc/pycharmprojects/ecbot/domtree_infineon1.json",
    "c:/users/songc/pycharmprojects/ecbot/domtree_infineon2.json",
    "c:/users/songc/pycharmprojects/ecbot/domtree_microchip.json",
    "c:/users/songc/pycharmprojects/ecbot/domtree_mouser.json",
    "c:/users/songc/pycharmprojects/ecbot/domtree_mps.json",
    "c:/users/songc/pycharmprojects/ecbot/domtree_murata.json",
    "c:/users/songc/pycharmprojects/ecbot/domtree_nxp.json",
    "c:/users/songc/pycharmprojects/ecbot/domtree_renesas.json",
    "c:/users/songc/pycharmprojects/ecbot/domtree_rohm.json",
    "c:/users/songc/pycharmprojects/ecbot/domtree_silabs.json",
    "c:/users/songc/pycharmprojects/ecbot/domtree_st.json",
    "c:/users/songc/pycharmprojects/ecbot/domtree_ti.json",
    "c:/users/songc/pycharmprojects/ecbot/domtree_toshiba.json"
]
def py_grep(search_string, file_paths):
    for file_path in file_paths:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                lc = 0
                for i, line in enumerate(f, 1):
                    if search_string in line:
                        if len(file_paths) > 1:
                            if lc < 32:
                                print(f"{file_path}:{i}:{line.rstrip()}")
                            lc = lc + 1
                        else:
                            print(f"{i}:{line.rstrip()}")
        except Exception as e:
            print(f"Error opening {file_path}: {e}")


def read_dom_tree_file(file_path=""):
    try:
        if not file_path:
            file_path = "c:/users/songc/pycharmprojects/ecbot/domtree_adi.json"
            # file_path = "c:/users/songc/pycharmprojects/ecbot/domtree_arrow.json"
            # file_path = "c:/users/songc/pycharmprojects/ecbot/domtree_avnet.json"
            # file_path = "c:/users/songc/pycharmprojects/ecbot/domtree_cirruslogic.json"
            # file_path = "c:/users/songc/pycharmprojects/ecbot/domtree_infineon1.json"
            # file_path = "c:/users/songc/pycharmprojects/ecbot/domtree_infineon2.json"
            # file_path = "c:/users/songc/pycharmprojects/ecbot/domtree_microchip.json"
            # file_path = "c:/users/songc/pycharmprojects/ecbot/domtree_mouser.json"
            # file_path = "c:/users/songc/pycharmprojects/ecbot/domtree_mps.json"
            # file_path = "c:/users/songc/pycharmprojects/ecbot/domtree_murata.json"
            # file_path = "c:/users/songc/pycharmprojects/ecbot/domtree_nxp.json"
            # file_path = "c:/users/songc/pycharmprojects/ecbot/domtree_renesas.json"
            # file_path = "c:/users/songc/pycharmprojects/ecbot/domtree_rohm.json"
            # file_path = "c:/users/songc/pycharmprojects/ecbot/domtree_silabs.json"
            # file_path = "c:/users/songc/pycharmprojects/ecbot/domtree_st.json"
            # file_path = "c:/users/songc/pycharmprojects/ecbot/domtree_ti.json"
            # file_path = "c:/users/songc/pycharmprojects/ecbot/domtree_toshiba.json"
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: The file {file_path} was not found.")
        return ""
    except IOError as e:
        print(f"Error reading {file_path}: {e}")
        return ""

def scrape_tests(url=""):
    if not url:
        url = "https://www.digikey.com/en/products/filter/tantalum-polymer-capacitors/70"
        url = "file:///C:/temp/junkk.html"

        # url = "file:///C:/Users/songc/Downloads/vendorpages/Tantalum%20-%20Polymer%20Capacitors%20_%20Electronic%20Components%20Distributor%20DigiKey.html"
        # url = "https://www.mouser.com/c/connectors/ic-component-sockets/"
        # url = "https://www.avnet.com/americas/products/c/power-management/"
        # url = "file:///C:/Users/songc/Downloads/vendorpages/Operational%20Amplifiers%20_%20Avnet%20Americas.html"
        # # url = "https://eshop.wpgam.com/"   # no parametric filters
        # url = "https://www.arrow.com/en/categories/connectors/io-connectors/connector-circular"
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
        # url = "https://www.silabs.com/wireless/bluetooth"
        # url = "https://www.cirrus.com/#psearch_T120"
        # url = "https://www.nxp.com/products/product-selector:PRODUCT-SELECTOR?category=c731_c382_c85&page=1"
        # url = "https://www.st.com/en/microcontrollers-microprocessors/stm32f101/products.html"
        # url = "https://www.st.com/en/microcontrollers-microprocessors/stm32f105-107.html"
        # url = "https://www.st.com/en/microcontrollers-microprocessors/stm32-32-bit-arm-cortex-mcus.html"
        # url = "https://www.st.com/en/motor-drivers/brushed-dc-motor-drivers/products.html"
        # url = "https://www.infineon.com/products/esd-surge-protection/multi-purpose-esd-devices"
        # url = "https://www.infineon.com/products/power/igbt/automotive-qualified-igbts/coolsic-mosfet-modules"
        # url = "https://www.infineon.com/products/power/igbt/automotive-qualified-igbts/coolsic-mosfet-modules/hybridpack-drive-dc6"
        # url = "https://www.infineon.com/application/automotive-traction-inverter-commercial-vehicles"
        # url = "https://toshiba.semicon-storage.com/us/search/parametric.html"
        # url = "https://toshiba.semicon-storage.com/parametric?region=ncsa&lang=en_us&code=param_210&p=50&i=1&sort=4,asc&cc=0d,1d,28d,3h,18h,29h,20h,30h,4d,5d,6d,7d,8d,19d,9d,10d,11d,12d,13d,14d,21h,22h,23h,24h,25h,26h,27h"
        # url = "https://toshiba.semicon-storage.com/parametric?region=ncsa&lang=en_us&code=param_814&p=50&i=1&sort=3,asc&cc=0d,1d,20d,19h,3d,4d,5d,6d,7d,8d,9d,10d,11d,12d,13d,14d,15h,16h,17h,18h"
        # url = "https://www.renesas.com/en/products/microcontrollers-microprocessors/rh850-automotive-mcus"
        # url = "https://www.renesas.com/en/products/microcontrollers-microprocessors/rh850-automotive-mcus/product-selector?field-series-name=RH850%2FF1x"
        # url = "https://www.renesas.com/en/products/automotive-products/automotive-sensors/automotive-position-sensors/product-selector"
        # url = "https://www.sony-semicon.com/en/products/is/industry/selector.html"
        # url = "https://semiconductor.samsung.com/processor/wearable-processor/"
        # url = "https://semiconductor.samsung.com/power-ic/memory-power-ic/"
        # url = "https://product.skhynix.com/products/cxl/cxl.go"
        # url = "https://www.rohm.com/products/motor-actuator-drivers/stepping-motor#getDriverEPF"
        # url = "https://www.rohm.com/quick-search/motor-driver/fan"
        # url = "https://www.rohm.com/products/wireless-lsi/industrial-wireless-communication/mcu-Included-specified-low-power-radio#parametricSearch"
        # url = "https://www.murata.com/en-us/products/power/power-semiconductor/overview/lineup/flexibk"
        # url = "https://www.murata.com/en-us/search/productsearch?cate=cgsubResonators&stype=2&realtime=1"
        # url = "https://global.kyocera.com/prdct/fc/industries/semiconductor/index.html"
        # url = "https://product.torexsemi.com/en/category/dcdc-converters#col9=3"
        # url = "https://product.torexsemi.com/en"

        # # cn ones.
        # url = "https://ceaci.cecport.com/products"
        # url = "http://www.techtronics.com.hk/index.php/Home/Product/index.html"
        # url = "https://www.ufct.com/list_12.aspx?cid=5"
        # url = "https://comtech.cn/product/product_fenlei"


    # scrape the dom tree
    driver_path = "c:/users/songc/pycharmprojects/ecbot/chromedriver-win64/v138.0.7204.157/chromedriver.exe"
    port = 9228  # this is the port number used when start chrome from win power shell command line. with debug mode on
    # web_driver = webDriverStartExistingChrome(driver_path, port)

    py_grep("td", dtfs)

    # web_driver.get(url)  # Replace with the new URL
    # time.sleep(15)
    # print("waited for 15 seconds.................")
    # handle_popups(web_driver)
    # print("done with popups.................")
    # # scroll to bottom and back up to get the full page
    # page_scroll(web_driver, None)
    # time.sleep(1)
    # # wait for all dynamic content to settle
    # if wait_for_dynamic_content(web_driver):
    #     print("opened URL: " + url)
    #     time.sleep(3)
    #     script = load_build_dom_tree_script()
    #     # print("dom tree build script to be executed", script)
    #     target = None
    #     response = execute_js_script(web_driver, script, target)
    #     domTree = response.get("result", {})
    #
    #     # print out some logs.
    #     logs = response.get("logs", [])
    #     MAX_LOGS = 128
    #     if len(logs) > MAX_LOGS:
    #         llogs = MAX_LOGS
    #     else:
    #         llogs = len(logs)
    #     for i in range(llogs):
    #         print(logs[i])
    #
    #     with open("domtree.json", 'w', encoding="utf-8") as dtjf:
    #         json.dump(domTree, dtjf, ensure_ascii=False, indent=4)
    #         # self.rebuildHTML()
    #         dtjf.close()
    #
    #     print("dom tree:", type(domTree), domTree.keys())
    #     top_level_nodes = find_top_level_nodes(domTree)
    #     print("top level nodes:", type(top_level_nodes), top_level_nodes)
    #     top_level_texts = get_shallowest_texts(top_level_nodes, domTree)
    #     tls = collect_text_nodes_by_level(domTree)
    #     print("level texts:", tls)
    #     print("level N texts:", [len(tls[i]) for i in range(len(tls))])
    #     for l in tls:
    #         if l:
    #             print("level texts:", [domTree["map"][nid]["text"] for nid in l])
    #
    #     domExtractor = DomExtractor(domTree["map"])
    #     param_filter = domExtractor.find_parametric_filters()
    #     print("param filter:", param_filter)
    #
    #     tables = domExtractor.find_and_extract_tables()
    #     print("found tables:", tables)
    #
    #     sects = sectionize_dt_with_subsections(domTree)
    #     print("sections:", sects)


    domTree =read_dom_tree_file()
    top_level_nodes = find_top_level_nodes(domTree)
    print("top level nodes:", type(top_level_nodes), top_level_nodes)
    top_level_texts = get_shallowest_texts(top_level_nodes, domTree)
    tls = collect_text_nodes_by_level(domTree)
    print("level texts:", tls)
    print("level N texts:", [len(tls[i]) for i in range(len(tls))])

    # print out longest string for each levels
    for tl in tls:
        if tl:
            nts = [(nid, domTree["map"][nid]["text"]) for nid in tl]
            #sort strings in tl by length
            nts_sorted = sorted(nts, key=lambda t: len(t[1]), reverse=True)  # longest first
            print("level longesttexts:", nts_sorted[0])

    test_result = "success"
    return test_result