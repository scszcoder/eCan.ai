from agent.mcp.server.scrapers.digi_key_scrapers.digi_key_selenium_scrapers import *
from utils.logger_helper import get_traceback
from agent.agent_service import get_agent_by_id


def selenium_search_component(webdriver, pf, site_urls):
    try:
        all_results = []
        for site_url in site_urls:
            if "digikey" in site_url:
                logger.debug("searching digikey")
                results = digi_key_selenium_search_component(webdriver, pf, site_url)
                all_results.extend(results)
    except Exception as e:
        err_trace = get_traceback(e, "ErrorSeleniumSearchComponent")
        logger.debug(err_trace)
        all_results = []

    return all_results