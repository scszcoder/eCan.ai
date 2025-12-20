from agent.mcp.server.scrapers.digi_key_scrapers.digi_key_selenium_scrapers import *
from utils.logger_helper import get_traceback
from agent.agent_service import get_agent_by_id
from utils.logger_helper import logger_helper as logger


def selenium_search_component(webdriver, pf, site_cats):
    try:
        logger.debug(f"selenium_search_component started......{site_cats}")
        logger.debug(f"Received pf: {pf}")
        all_results = []

        for cats in site_cats:
            site_url = cats[-1]['url']
            cat_phrase = cats[-1]['name']
            if "digikey" in site_url:
                logger.debug("searching digikey")
                results = digi_key_selenium_search_component(webdriver, pf, cat_phrase, site_url)
                if results["status"] == "success":
                    all_results.extend(results["components"])
    except Exception as e:
        err_trace = get_traceback(e, "ErrorSeleniumSearchComponent")
        logger.debug(err_trace)
        all_results = []

    return all_results


def selenium_sort_search_results(webdriver, header_text, ascending, max_n, site_url):
    try:
        logger.debug(f"selenium_sort_search_results started......{header_text}")
        all_results = []

        if "digi" in site_url and "key" in site_url:
            logger.debug("sorting digikey search results")
            results = digi_key_selenium_sort_and_extract_results(webdriver, header_text, ascending, max_n)

            if results["status"] == "success":
                all_results.extend(results["components"])
    except Exception as e:
        err_trace = get_traceback(e, "ErrorSeleniumSearchComponent")
        logger.debug(err_trace)
        all_results = []

    return all_results