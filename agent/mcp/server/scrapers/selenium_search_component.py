
from agent.mcp.server.scrapers.digi_key_scrapers.digi_key_selenium_scrapers import *
from utils.logger_helper import get_traceback
from agent.agent_service import get_agent_by_id
from utils.logger_helper import logger_helper as logger


def selenium_search_component(webdriver, pf, site):
    try:
        logger.debug("selenium_search_component started......")
        all_results = []
        site_url = site['url']
        cats = site['categories']
        for cat in cats:
            cat_phrase = cat[-1]
            if "digikey" in site_url:
                logger.debug("searching digikey")
                results = digi_key_selenium_search_component(webdriver, pf, cat_phrase)
                if results["status"] == "success":
                    all_results.extend(results["components"])
    except Exception as e:
        err_trace = get_traceback(e, "ErrorSeleniumSearchComponent")
        logger.debug(err_trace)
        all_results = []

    return all_results