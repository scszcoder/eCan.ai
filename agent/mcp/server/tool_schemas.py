import mcp.types as types
from agent.mcp.server.scrapers.amazon_seller.amazon_orders_scrape import (
    add_get_amazon_summary_tool_schema,
    add_amazon_fullfill_next_order_tool_schema,
)
from agent.mcp.server.scrapers.amazon_seller.amazon_messages_scrape import (
    add_amazon_handle_next_message_tool_schema,
)
from agent.mcp.server.scrapers.amazon_seller.amazon_search import add_amazon_search_tool_schema
from agent.mcp.server.scrapers.amazon_seller.amazon_listing import (
    add_amazon_add_listings_tool_schema,
    add_amazon_remove_listings_tool_schema,
    add_amazon_update_listings_tool_schema,
    add_amazon_get_listings_tool_schema,
    add_amazon_add_listing_templates_tool_schema,
    add_amazon_remove_listing_templates_tool_schema,
    add_amazon_update_listing_templates_tool_schema,
)
from agent.mcp.server.scrapers.amazon_seller.amazon_cancel_return import (
    add_amazon_handle_return_tool_schema,
    add_amazon_handle_refund_tool_schema,
)
from agent.mcp.server.scrapers.amazon_seller.amazon_campaign import (
    add_amazon_collect_campaigns_stats_tool_schema,
    add_amazon_adjust_campaigns_tool_schema,
)
from agent.mcp.server.scrapers.amazon_seller.amazon_performance import (
    add_amazon_collect_shop_products_stats_tool_schema,
)
from agent.mcp.server.scrapers.amazon_seller.amazon_utils import (
    add_amazon_generate_work_summary_tool_schema,
)

from agent.mcp.server.scrapers.ebay_seller.ebay_orders_scrape import add_get_ebay_summary_tool_schema, add_ebay_fullfill_next_order_tool_schema, add_ebay_cancel_orders_tool_schema
from agent.mcp.server.scrapers.ebay_seller.ebay_messages_scrape import add_ebay_read_all_messages_tool_schema, add_ebay_read_next_message_tool_schema, add_ebay_respond_to_message_tool_schema
from agent.mcp.server.scrapers.ebay_seller.ebay_search import add_ebay_search_tool_schema
from agent.mcp.server.scrapers.ebay_seller.ebay_listing import (
    add_ebay_add_listings_tool_schema,
    add_ebay_remove_listings_tool_schema,
    add_ebay_update_listings_tool_schema,
    add_ebay_get_listings_tool_schema,
    add_ebay_add_listing_templates_tool_schema,
    add_ebay_remove_listing_templates_tool_schema,
    add_ebay_update_listing_templates_tool_schema
)
from agent.mcp.server.scrapers.ebay_seller.ebay_labels import (
    add_ebay_gen_labels_tool_schema,
    add_ebay_cancel_labels_tool_schema
)
from agent.mcp.server.scrapers.ebay_seller.ebay_cancel_return import (
    add_ebay_handle_return_tool_schema,
    add_ebay_handle_refund_tool_schema
)
from agent.mcp.server.scrapers.ebay_seller.ebay_campaign import (
    add_ebay_collect_campaigns_stats_tool_schema,
    add_ebay_adjust_campaigns_tool_schema
)
from agent.mcp.server.scrapers.ebay_seller.ebay_performance import (
    add_ebay_collect_shop_products_stats_tool_schema
)
from agent.mcp.server.scrapers.ebay_seller.ebay_utils import (
    add_ebay_generate_work_summary_tool_schema
)

from agent.mcp.server.scrapers.etsy_seller.etsy_orders_scrape import (
    add_get_etsy_summary_tool_schema,
    add_etsy_fullfill_next_order_tool_schema,
)
from agent.mcp.server.scrapers.etsy_seller.etsy_messages_scrape import (
    add_etsy_handle_next_message_tool_schema,
)
from agent.mcp.server.scrapers.etsy_seller.etsy_search import add_etsy_search_tool_schema
from agent.mcp.server.scrapers.etsy_seller.etsy_listing import (
    add_etsy_add_listings_tool_schema,
    add_etsy_remove_listings_tool_schema,
    add_etsy_update_listings_tool_schema,
    add_etsy_get_listings_tool_schema,
    add_etsy_add_listing_templates_tool_schema,
    add_etsy_remove_listing_templates_tool_schema,
    add_etsy_update_listing_templates_tool_schema,
)
from agent.mcp.server.scrapers.etsy_seller.etsy_cancel_return import (
    add_etsy_handle_return_tool_schema,
    add_etsy_handle_refund_tool_schema,
)
from agent.mcp.server.scrapers.etsy_seller.etsy_campaign import (
    add_etsy_collect_campaigns_stats_tool_schema,
    add_etsy_adjust_campaigns_tool_schema,
)
from agent.mcp.server.scrapers.etsy_seller.etsy_performance import (
    add_etsy_collect_shop_products_stats_tool_schema,
)
from agent.mcp.server.scrapers.etsy_seller.etsy_utils import (
    add_etsy_generate_work_summary_tool_schema,
)

from agent.mcp.server.scrapers.gmail.gmail_read import (
    add_gmail_read_titles_tool_schema,
    add_gmail_read_full_email_tool_schema,
    add_gmail_respond_tool_schema,
    add_gmail_write_new_tool_schema,
    add_gmail_move_email_tool_schema,
    add_gmail_mark_status_tool_schema,
    add_gmail_delete_email_tool_schema
)
from agent.mcp.server.Privacy.privacy_reserve import add_privacy_reserve_tool_schema
from agent.mcp.server.scrapers.shopify_seller.shopify_orders_scrape import add_get_shopify_summary_tool_schema, add_shopify_fullfill_next_order_tool_schema
from agent.mcp.server.scrapers.shopify_seller.shopify_messages_scrape import add_shopify_handle_next_message_tool_schema

from agent.mcp.server.scrapers.pirate_shipping.purchase_label import add_pirate_shipping_purchase_labels_tool_schema
from agent.ec_skills.label_utils.print_label import (
    add_print_labels_tool_schema,
    add_reformat_labels_tool_schema,
)
from agent.mcp.server.api.ecan_ai.ecan_ai_api import add_ecan_ai_api_get_agent_status_tool_schema
from agent.ec_skills.rag.local_rag_mcp import add_ragify_tool_schema, add_rag_query_tool_schema
from agent.mcp.server.extern_tools_schemas import add_extern_tools_schemas

tool_schemas = []

def get_tool_schemas():
    # 确保工具模式已初始化
    if not tool_schemas:
        build_agent_mcp_tools_schemas()
    return tool_schemas

def add_tool_schema(new_schema):
    tool_schemas.append(new_schema)

def build_agent_mcp_tools_schemas():
    tool_schema = types.Tool(
            name="rpa_supervisor_scheduling_work",
            description="<category>RPA</category><sub-category>Supervisor</sub-category>As a RPA supervisor, fetches daily work schedule and run team prep and get ready to dispatch the work to the operator agents on the remote hosts to work on.",
            inputSchema={
                "type": "object",
                "required": [],
                "properties": {},
            },
        )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="rpa_operator_dispatch_works",
        description="<category>RPA</category><sub-category>Supervisor</sub-category>As a RPA operator, it dispatches the RPA works to be performed by a platoon of bots on this host computer.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["works"],
                    "properties": {
                        "works": {
                            "type": "dict",
                            "description": "work to be dones",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="rpa_supervisor_process_work_results",
        description="<category>RPA</category><sub-category>Operator</sub-category>As an RPA supervisor, update overall result with received operator work report.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["url"],
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL to fetch",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="rpa_supervisor_run_daily_housekeeping",
        description="<category>RPA</category><sub-category>Operator</sub-category>As an RPA supervisor, after all work reports collected, do necessary housekeeping work such as accounting, book keeping etc.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["url"],
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL to fetch",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="rpa_operator_report_work_results",
        description="<category>RPA</category><sub-category>Operator</sub-category>As an RPA operator, report work results to supervisor",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["url"],
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL to fetch",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="os_screen_capture",
        description="<category>OS</category><sub-category>Screen Capture</sub-category>Do a screen shot, save to a png file and stores into a cv2 image data structure",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["win_title_kw", "sub_area", "file"],
                    "properties": {
                        "win_title_kw": {
                            "type": "string",
                            "description": "the window title keyword for the window to be screen captured, (default is \"\" which means top window)",
                        },
                        "sub_area": {
                            "type": "[int]",
                            "description": "sub area of screen shot with relative offset [left, top, right, bottom]",
                        },
                        "file": {
                            "type": "string",
                            "description": "full path of screen shot file name",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="os_screen_analyze",
        description="<category>OS</category><sub-category>OCR</sub-category>do OCR and icon match on an image and result in structured text in the image",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["win_title_kw", "sub_area", "site", "engine"],
                    "properties": {
                        "win_title_kw": {
                            "type": "string",
                            "description": "the window title keyword for the window to be screen captured, (default is \"\" which means top window)",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="mouse_click",
        description="<category>PyAutoGUI</category><sub-category>Mouse Action</sub-category>a mouse click function using pyautogui.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["loc", "post_move_delay", "post_click_delay"],
                    "properties": {
                        "loc": {
                            "type": "[int]",
                            "description": "coordinates of [x, y]",
                        },
                        "post_move_delay": {
                            "type": "integer",
                            "description": "wait some seconds after mouse move to the location",
                        },
                        "post_click_delay": {
                            "type": "integer",
                            "description": "wait some seconds after mouse click",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="mouse_move",
        description="<category>PyAutoGUI</category><sub-category>Mouse Action</sub-category>a mouse move/hover function using pyautogui.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["location", "post_wait"],
                    "properties": {
                        "location": {
                            "type": "[int]",
                            "description": "coordinates of [x, y]",
                        },
                        "post_wait": {
                            "type": "integer",
                            "description": "wait number of seconds after movement",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="mouse_drag_drop",
        description="<category>PyAutoGUI</category><sub-category>Mouse Action</sub-category>a mouse drag and drop function using pyautogui.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["pick_loc","drop_loc", "duration", "post_wait"],
                    "properties": {
                        "pick_loc": {
                            "type": "[int]",
                            "description": "coordinates mouse pick up locationof [x, y]",
                        },
                        "drop_loc": {
                            "type": "[int]",
                            "description": "coordinates mouse drop locationof [x, y]",
                        },
                        "duration": {
                            "type": "float",
                            "description": "time interval in seconds (could be fractional) between pick up and drop off",
                        },
                        "post_wait": {
                            "type": "integer",
                            "description": "wait number of seconds after post movement",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="mouse_scroll",
        description="<category>PyAutoGUI</category><sub-category>Mouse Action</sub-category>a mouse scroll function using pyautogui.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["direction", "amount", "post_wait"],
                    "properties": {
                        "direction": {
                            "type": "string",
                            "description": "either up or down",
                        },
                        "duration": {
                            "type": "integer",
                            "description": "amount of mouse wheel scroll units",
                        },
                        "post_wait": {
                            "type": "integer",
                            "description": "wait number of seconds after post movement",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="keyboard_text_input",
        description="<category>PyAutoGUI</category><sub-category>Keyboard Action</sub-category>direct drive keyboard type in text string.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["text", "interval", "post_wait"],
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "text string to be typed in",
                        },
                        "interval": {
                            "type": "float",
                            "description": "amount of time interval in seconds(can be fractional number) between key strokes",
                        },
                        "post_wait": {
                            "type": "integer",
                            "description": "wait number of seconds after post movement",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="keyboard_keys_input",
        description="<category>PyAutoGUI</category><sub-category>Keyboard Action</sub-category>direct drive keyboard type combo hot keys.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["keys", "post_wait"],
                    "properties": {
                        "keys": {
                            "type": "[string]",
                            "description": "list of keys to be keyed in, for example ['ctrl', 'x']",
                        },
                        "post_wait": {
                            "type": "integer",
                            "description": "wait number of seconds after post movement",
                        }
                    }
                }
            },
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="solve_px_captcha",
        description="<category>PyAutoGUI</category><sub-category>Mouse Action</sub-category>solve px captcha, PerimeterX Captcha, by read screen, and emulate pressing and holding button for certin amount of time.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["keyword", "duration"],
                    "properties": {
                        "keyword": {
                            "type": "[string]",
                            "description": "the text on the button to where the mouse will be pressed and held down",
                        },
                        "duration": {
                            "type": "integer",
                            "description": "press and hold for this number of seconds before releasing",
                        }
                    }
                }
            },
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="os_wait",
        description="<category>OS</category><sub-category>Timer</sub-category>wait a few seconds.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["seconds"],  # url is required *inside* input
                    "properties": {
                        "seconds": {
                            "type": "integer",
                            "description": "URL of the web page to open",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)


    tool_schema = types.Tool(
        name="say_hello",
        description="<category>OS</category><sub-category>General</sub-category>just a test.",
        inputSchema={
            "type": "object",
            "required": [],
            "properties": {},
        },
    )

    add_tool_schema(tool_schema)


    tool_schema = types.Tool(
        name="in_browser_wait_for_element",
        description="<category>Browser Automation</category><sub-category>In Browser Search Action</sub-category>use webdriver or cdp to wait for web elements.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["driver_type", "browser_type", "element_type", "element_name", "timeout"],  # url is required *inside* input
                    "properties": {
                        "driver_type": {
                            "type": "string",
                            "enum": ["webdriver", "cdp"],
                            "default": "webdriver",
                            "description": "Driver mode: 'webdriver' for Selenium WebDriver, 'cdp' for Chrome DevTools Protocol via BrowserSession",
                        },
                        "browser_type": {
                            "type": "string",
                            "enum": ["adspower", "existing chrome", "chromium"],
                            "default": "existing chrome",
                            "description": "Browser type to use (only applicable when driver_type is 'cdp')",
                        },
                        "element_type": {
                            "type": "string",
                            "description": "web element type: ID, Name, ClassName, LinkText, PartialLinkText, TagName, CSS Selector, or XPath",
                        },
                        "element_name": {
                            "type": "string",
                            "description": "name of the element",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "max wait time(seconds) to find element on the page",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="in_browser_click_element_by_index",
        description="<category>Browser Automation</category><sub-category>In Browser Mouse Action</sub-category>use webdriver or cdp to click on a web element based on index in the selector map.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["driver_type", "browser_type", "dom_index", "timeout"],  # url is required *inside* input
                    "properties": {
                        "driver_type": {
                            "type": "string",
                            "enum": ["webdriver", "cdp"],
                            "default": "webdriver",
                            "description": "Driver mode: 'webdriver' for Selenium WebDriver, 'cdp' for Chrome DevTools Protocol via BrowserSession",
                        },
                        "browser_type": {
                            "type": "string",
                            "enum": ["adspower", "existing chrome", "chromium"],
                            "default": "existing chrome",
                            "description": "Browser type to use (only applicable when driver_type is 'cdp')",
                        },
                        "dom_index": {
                            "type": "integer",
                            "description": "dom index of the element in the dom tree",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "max wait time(seconds) to find element on the page",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)


    tool_schema = types.Tool(
        name="in_browser_click_element_by_selector",
        description="<category>Browser Automation</category><sub-category>In Browser Mouse Action</sub-category>use webdriver or cdp to click on an web element based on css selector.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["driver_type", "browser_type", "element_type", "element_name", "timeout"],  # url is required *inside* input
                    "properties": {
                        "driver_type": {
                            "type": "string",
                            "enum": ["webdriver", "cdp"],
                            "default": "webdriver",
                            "description": "Driver mode: 'webdriver' for Selenium WebDriver, 'cdp' for Chrome DevTools Protocol via BrowserSession",
                        },
                        "browser_type": {
                            "type": "string",
                            "enum": ["adspower", "existing chrome", "chromium"],
                            "default": "existing chrome",
                            "description": "Browser type to use (only applicable when driver_type is 'cdp')",
                        },
                        "element_type": {
                            "type": "string",
                            "description": "web element type: ID, Name, ClassName, LinkText, PartialLinkText, TagName, CSS Selector, or XPath",
                        },
                        "element_name": {
                            "type": "string",
                            "description": "name of the element",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "max wait time(seconds) to find element on the page",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)


    tool_schema = types.Tool(
        name="in_browser_click_element_by_xpath",
        description="<category>Browser Automation</category><sub-category>In Browser Mouse Action</sub-category>use webdriver or cdp to click on an web element based on xpath.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["driver_type", "browser_type", "element_type", "element_name", "timeout"],  # url is required *inside* input
                    "properties": {
                        "driver_type": {
                            "type": "string",
                            "enum": ["webdriver", "cdp"],
                            "default": "webdriver",
                            "description": "Driver mode: 'webdriver' for Selenium WebDriver, 'cdp' for Chrome DevTools Protocol via BrowserSession",
                        },
                        "browser_type": {
                            "type": "string",
                            "enum": ["adspower", "existing chrome", "chromium"],
                            "default": "existing chrome",
                            "description": "Browser type to use (only applicable when driver_type is 'cdp')",
                        },
                        "element_type": {
                            "type": "string",
                            "description": "web element type: ID, Name, ClassName, LinkText, PartialLinkText, TagName, CSS Selector, or XPath",
                        },
                        "element_name": {
                            "type": "string",
                            "description": "name of the element",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "max wait time(seconds) to find element on the page",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)


    tool_schema = types.Tool(
        name="in_browser_click_element_by_text",
        description="<category>Browser Automation</category><sub-category>Selenium Mouse Action</sub-category>use webdriver or cdp to click on an web element based on text",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["driver_type", "browser_type", "element_type", "element_name", "timeout"],  # url is required *inside* input
                    "properties": {
                        "driver_type": {
                            "type": "string",
                            "enum": ["webdriver", "cdp"],
                            "default": "webdriver",
                            "description": "Driver mode: 'webdriver' for Selenium WebDriver, 'cdp' for Chrome DevTools Protocol via BrowserSession",
                        },
                        "browser_type": {
                            "type": "string",
                            "enum": ["adspower", "existing chrome", "chromium"],
                            "default": "existing chrome",
                            "description": "Browser type to use (only applicable when driver_type is 'cdp')",
                        },
                        "element_type": {
                            "type": "string",
                            "description": "web element type: ID, Name, ClassName, LinkText, PartialLinkText, TagName, CSS Selector, or XPath",
                        },
                        "element_name": {
                            "type": "string",
                            "description": "name of the element",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "max wait time(seconds) to find element on the page",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)


    tool_schema = types.Tool(
        name="in_browser_input_text",
        description="<category>Browser Automation</category><sub-category>In Browser Keyboard Action</sub-category>use webdriver or cdp to key in text on a web page's input field.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["driver_type", "browser_type", "element_type", "element_name", "element_text", "nth", "timeout"],  # url is required *inside* input
                    "properties": {
                        "driver_type": {
                            "type": "string",
                            "enum": ["webdriver", "cdp"],
                            "default": "webdriver",
                            "description": "Driver mode: 'webdriver' for Selenium WebDriver, 'cdp' for Chrome DevTools Protocol via BrowserSession",
                        },
                        "browser_type": {
                            "type": "string",
                            "enum": ["adspower", "existing chrome", "chromium"],
                            "default": "existing chrome",
                            "description": "Browser type to use (only applicable when driver_type is 'cdp')",
                        },
                        "element_type": {
                            "type": "string",
                            "description": "web element type: ID, Name, ClassName, LinkText, PartialLinkText, TagName, CSS Selector, or XPath",
                        },
                        "element_name": {
                            "type": "string",
                            "description": "name of the element",
                        },
                        "element_text": {
                            "type": "string",
                            "description": "text of the web element",
                        },
                        "nth": {
                            "type": "integer",
                            "description": "nth element of the list of elements of same type and same name",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "max wait time(seconds) to find element on the page",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)


    tool_schema = types.Tool(
        name="in_browser_scroll",
        description="<category>Browser Automation</category><sub-category>In Browser Mouse Action</sub-category>use webdriver or cdp to scroll within the browser.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["driver_type", "browser_type", "direction", "amount", "post_wait"],  # url is required *inside* input
                    "properties": {
                        "driver_type": {
                            "type": "string",
                            "enum": ["webdriver", "cdp"],
                            "default": "webdriver",
                            "description": "Driver mode: 'webdriver' for Selenium WebDriver, 'cdp' for Chrome DevTools Protocol via BrowserSession",
                        },
                        "browser_type": {
                            "type": "string",
                            "enum": ["adspower", "existing chrome", "chromium"],
                            "default": "existing chrome",
                            "description": "Browser type to use (only applicable when driver_type is 'cdp')",
                        },
                        "direction": {
                            "type": "string",
                            "description": "scroll direction of either up or down",
                        },
                        "amount": {
                            "type": "integer",
                            "description": "number of scroll units",
                        },
                        "post_wait": {
                            "type": "integer",
                            "description": "max wait time(seconds) to find element on the page",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)


    tool_schema = types.Tool(
        name="in_browser_send_keys",
        description="<category>Browser Automation</category><sub-category>In Browser Keyboard Action</sub-category>use webdriver or cdp to send hot keys to the web page.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["driver_type", "browser_type", "keys"],  # url is required *inside* input
                    "properties": {
                        "driver_type": {
                            "type": "string",
                            "enum": ["webdriver", "cdp"],
                            "default": "webdriver",
                            "description": "Driver mode: 'webdriver' for Selenium WebDriver, 'cdp' for Chrome DevTools Protocol via BrowserSession",
                        },
                        "browser_type": {
                            "type": "string",
                            "enum": ["adspower", "existing chrome", "chromium"],
                            "default": "existing chrome",
                            "description": "Browser type to use (only applicable when driver_type is 'cdp')",
                        },
                        "keys": {
                            "type": "array",
                            "description": "list of combo keys to send. the special keyboard keys are: <ctrl> <alt> <shift> <meta> <enter> <esc> <backspace> <tab> <space> <up> <down> <left> <right> <home> <end> <pageup> <pagedown> <insert> <delete> <f1> <f2> <f3> <f4> <f5> <f6> <f7> <f8> <f9> <f10> <f11> <f12>",
                            "items": {
                                "type": "string"
                            }
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)


    tool_schema = types.Tool(
        name="in_browser_scroll_to_text",
        description="<category>Browser Automation</category><sub-category>In Browser Mouse Action</sub-category>use webdriver or cdp to scroll to the specified text location.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["driver_type", "browser_type", "text"],  # url is required *inside* input
                    "properties": {
                        "driver_type": {
                            "type": "string",
                            "enum": ["webdriver", "cdp"],
                            "default": "webdriver",
                            "description": "Driver mode: 'webdriver' for Selenium WebDriver, 'cdp' for Chrome DevTools Protocol via BrowserSession",
                        },
                        "browser_type": {
                            "type": "string",
                            "enum": ["adspower", "existing chrome", "chromium"],
                            "default": "existing chrome",
                            "description": "Browser type to use (only applicable when driver_type is 'cdp')",
                        },
                        "text": {
                            "type": "string",
                            "description": "URL of the web page to open",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="in_browser_get_dropdown_options",
        description="<category>Browser Automation</category><sub-category>In Browser Mouse Action</sub-category>use webdriver or cdp to obtains the list of selection options on the drop down list.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["driver_type", "browser_type", "pulldown_menu_name"],  # url is required *inside* input
                    "properties": {
                        "driver_type": {
                            "type": "string",
                            "enum": ["webdriver", "cdp"],
                            "default": "webdriver",
                            "description": "Driver mode: 'webdriver' for Selenium WebDriver, 'cdp' for Chrome DevTools Protocol via BrowserSession",
                        },
                        "browser_type": {
                            "type": "string",
                            "enum": ["adspower", "existing chrome", "chromium"],
                            "default": "existing chrome",
                            "description": "Browser type to use (only applicable when driver_type is 'cdp')",
                        },
                        "pulldown_menu_name": {
                            "type": "string",
                            "description": "pull down menu name",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="in_browser_select_dropdown_option",
        description="<category>Browser Automation</category><sub-category>In Browser Mouse Action</sub-category>use webdriver or cdp to select an item on the drop down selection list.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["driver_type", "browser_type", "pulldown_item"],  # url is required *inside* input
                    "properties": {
                        "driver_type": {
                            "type": "string",
                            "enum": ["webdriver", "cdp"],
                            "default": "webdriver",
                            "description": "Driver mode: 'webdriver' for Selenium WebDriver, 'cdp' for Chrome DevTools Protocol via BrowserSession",
                        },
                        "browser_type": {
                            "type": "string",
                            "enum": ["adspower", "existing chrome", "chromium"],
                            "default": "existing chrome",
                            "description": "Browser type to use (only applicable when driver_type is 'cdp')",
                        },
                        "pulldown_item": {
                            "type": "string",
                            "description": "to be selected item text on the drop down list",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="in_browser_drag_drop",
        description="<category>Browser Automation</category><sub-category>In Browser Mouse Action</sub-category>use webdriver or cdp to drag and drop an item. Supports both element-based (CSS selectors) and coordinate-based drag and drop.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["driver_type", "browser_type"],
                    "properties": {
                        "driver_type": {
                            "type": "string",
                            "enum": ["webdriver", "cdp"],
                            "default": "webdriver",
                            "description": "Driver mode: 'webdriver' for Selenium WebDriver, 'cdp' for Chrome DevTools Protocol via BrowserSession",
                        },
                        "browser_type": {
                            "type": "string",
                            "enum": ["adspower", "existing chrome", "chromium"],
                            "default": "existing chrome",
                            "description": "Browser type to use (only applicable when driver_type is 'cdp')",
                        },
                        "source_selector": {
                            "type": "string",
                            "description": "CSS selector of the source element to drag (use this OR source_x/source_y)",
                        },
                        "target_selector": {
                            "type": "string",
                            "description": "CSS selector of the target element to drop onto (use this OR target_x/target_y)",
                        },
                        "source_x": {
                            "type": "integer",
                            "description": "X coordinate of source position (use with source_y instead of source_selector)",
                        },
                        "source_y": {
                            "type": "integer",
                            "description": "Y coordinate of source position (use with source_x instead of source_selector)",
                        },
                        "target_x": {
                            "type": "integer",
                            "description": "X coordinate of target position (use with target_y instead of target_selector)",
                        },
                        "target_y": {
                            "type": "integer",
                            "description": "Y coordinate of target position (use with target_x instead of target_selector)",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)



    tool_schema = types.Tool(
        name="in_browser_extract_content",
        description="<category>Browser Automation</category><sub-category>In Browser Extract Content</sub-category>use cdp to extract dom tree from the web page.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["driver_type", "browser_type", "url"],  # url is required *inside* input
                    "properties": {
                        "driver_type": {
                            "type": "string",
                            "enum": ["webdriver", "cdp"],
                            "default": "webdriver",
                            "description": "Driver mode: 'webdriver' for Selenium WebDriver, 'cdp' for Chrome DevTools Protocol via BrowserSession",
                        },
                        "browser_type": {
                            "type": "string",
                            "enum": ["adspower", "existing chrome", "chromium"],
                            "default": "existing chrome",
                            "description": "Browser type to use (only applicable when driver_type is 'cdp')",
                        },
                        "url": {
                            "type": "string",
                            "format": "uri",  # optional JSON-Schema hint
                            "description": "URL of the web page to open, if this is empty, then whatever currently opened page will be extracted.",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)


    tool_schema = types.Tool(
        name="in_browser_switch_tab",
        description="<category>Browser Automation</category><sub-category>In Browser Tab Action</sub-category>use webdriver or cdp to switch to a tab in a browser.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["driver_type", "browser_type", "tab_title"],  # url is required *inside* input
                    "properties": {
                        "driver_type": {
                            "type": "string",
                            "enum": ["webdriver", "cdp"],
                            "default": "webdriver",
                            "description": "Driver mode: 'webdriver' for Selenium WebDriver, 'cdp' for Chrome DevTools Protocol via BrowserSession",
                        },
                        "browser_type": {
                            "type": "string",
                            "enum": ["adspower", "existing chrome", "chromium"],
                            "default": "existing chrome",
                            "description": "Browser type to use (only applicable when driver_type is 'cdp')",
                        },
                        "tab_title": {
                            "type": "string",
                            "description": "the title of the tab to switch to. and its dom tree will be automatically extracted after the page loads.",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)


    tool_schema = types.Tool(
        name="in_browser_open_tab",
        description="<category>Browser Automation</category><sub-category>In Browser Tab Action</sub-category>use webdriver or cdp to open a new tab in a browser and open an specified URL.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["driver_type", "browser_type", "url"],  # url is required *inside* input
                    "properties": {
                        "driver_type": {
                            "type": "string",
                            "enum": ["webdriver", "cdp"],
                            "default": "webdriver",
                            "description": "Driver mode: 'webdriver' for Selenium WebDriver, 'cdp' for Chrome DevTools Protocol via BrowserSession",
                        },
                        "browser_type": {
                            "type": "string",
                            "enum": ["adspower", "existing chrome", "chromium"],
                            "default": "existing chrome",
                            "description": "Browser type to use (only applicable when driver_type is 'cdp')",
                        },
                        "url": {
                            "type": "string",
                            "format": "uri",  # optional JSON-Schema hint
                            "description": "URL of the web page to be opened",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)


    tool_schema = types.Tool(
        name="in_browser_close_tab",
        description="<category>Browser Automation</category><sub-category>In Browser Tab Action</sub-category>use webdriver or cdp to close a tab in a browser.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["driver_type", "browser_type", "tab_title"],  # url is required *inside* input
                    "properties": {
                        "driver_type": {
                            "type": "string",
                            "enum": ["webdriver", "cdp"],
                            "default": "webdriver",
                            "description": "Driver mode: 'webdriver' for Selenium WebDriver, 'cdp' for Chrome DevTools Protocol via BrowserSession",
                        },
                        "browser_type": {
                            "type": "string",
                            "enum": ["adspower", "existing chrome", "chromium"],
                            "default": "existing chrome",
                            "description": "Browser type to use (only applicable when driver_type is 'cdp')",
                        },
                        "tab_title": {
                            "type": "string",
                            "description": "title of the browser tab to be closed",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)


    tool_schema = types.Tool(
        name="in_browser_execute_javascript",
        description="<category>Browser Automation</category><sub-category>In Browser Run Code Action</sub-category>use webdriver or cdp to execute a javascript on a web page.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["driver_type", "browser_type", "script_code"],  # url is required *inside* input
                    "properties": {
                        "driver_type": {
                            "type": "string",
                            "enum": ["webdriver", "cdp"],
                            "default": "webdriver",
                            "description": "Driver mode: 'webdriver' for Selenium WebDriver, 'cdp' for Chrome DevTools Protocol via BrowserSession",
                        },
                        "browser_type": {
                            "type": "string",
                            "enum": ["adspower", "existing chrome", "chromium"],
                            "default": "existing chrome",
                            "description": "Browser type to use (only applicable when driver_type is 'cdp')",
                        },
                        "script_code": {
                            "type": "string",
                            "description": "js script code to be executed in browser",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)



    tool_schema = types.Tool(
        name="in_browser_save_href_to_file",
        description="<category>Browser Automation</category><sub-category>In Browser Download Action</sub-category>use webdriver or cdp to download a href pointed file on a web page.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["driver_type", "browser_type", "href", "saved_file_path"],  # url is required *inside* input
                    "properties": {
                        "driver_type": {
                            "type": "string",
                            "enum": ["webdriver", "cdp"],
                            "default": "webdriver",
                            "description": "Driver mode: 'webdriver' for Selenium WebDriver, 'cdp' for Chrome DevTools Protocol via BrowserSession",
                        },
                        "browser_type": {
                            "type": "string",
                            "enum": ["adspower", "existing chrome", "chromium"],
                            "default": "existing chrome",
                            "description": "Browser type to use (only applicable when driver_type is 'cdp')",
                        },
                        "href": {
                            "type": "string",
                            "format": "uri",  # optional JSON-Schema hint
                            "description": "URL of the file to be downloaded",
                        },
                        "saved_file_path": {
                            "type": "string",
                            "description": "Full path to save the downloaded file",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="in_browser_upload_file",
        description="<category>Browser Automation</category><sub-category>In Browser Upload Action</sub-category>use webdriver or cdp to upload a file.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["driver_type", "browser_type", "href", "upload_file_path"],  # url is required *inside* input
                    "properties": {
                        "driver_type": {
                            "type": "string",
                            "enum": ["webdriver", "cdp"],
                            "default": "webdriver",
                            "description": "Driver mode: 'webdriver' for Selenium WebDriver, 'cdp' for Chrome DevTools Protocol via BrowserSession",
                        },
                        "browser_type": {
                            "type": "string",
                            "enum": ["adspower", "existing chrome", "chromium"],
                            "default": "existing chrome",
                            "description": "Browser type to use (only applicable when driver_type is 'cdp')",
                        },
                        "href": {
                            "type": "string",
                            "format": "uri",  # optional JSON-Schema hint
                            "description": "URL of the file upload element",
                        },
                        "upload_file_path": {
                            "type": "string",
                            "description": "Full path to the file to be uploaded",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)


    tool_schema = types.Tool(
        name="in_browser_go_to_url",
        description="<category>Browser Automation</category><sub-category>In Browser Tab Action</sub-category>use webdriver or cdp to open a new url site.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["driver_type", "browser_type", "url"],  # url is required *inside* input
                    "properties": {
                        "url": {
                            "type": "string",
                            "format": "uri",  # optional JSON-Schema hint
                            "description": "URL of the web page to open",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)


    tool_schema = types.Tool(
        name="os_connect_to_adspower",
        description="<category>Browser Automation</category><sub-category>ADSPower Action</sub-category>connect to an already opened and logged in ADS Power and open a new tab in URL.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["url"],  # url is required *inside* input
                    "properties": {
                        "url": {
                            "type": "string",
                            "format": "uri",  # optional JSON-Schema hint
                            "description": "URL of the web page to open",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="os_connect_to_chrome",
        description="<category>Browser Automation</category><sub-category>Chrome Connection</sub-category>connect to an already opened chrome and open a new tab in URL.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["driver_path", "url"],  # url is required *inside* input
                    "properties": {
                        "driver_path": {
                            "type": "string",
                            "description": "full path to web driver to use",
                        },
                        "url": {
                            "type": "string",
                            "format": "uri",  # optional JSON-Schema hint
                            "description": "URL of the web page to open",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)


    tool_schema = types.Tool(
        name="ecan_ai_new_chromiunm",
        description="<category>Browser Automation</category><sub-category>Launch New Chromium</sub-category>launch a new instance of chromium and open a new tab in URL.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["driver_path", "url", "profile"],  # url is required *inside* input
                    "properties": {
                        "driver_path": {
                            "type": "string",
                            "description": "full path to web driver to use",
                        },
                        "url": {
                            "type": "string",
                            "format": "uri",  # optional JSON-Schema hint
                            "description": "URL of the web page to open",
                        },
                        "profile": {
                            "type": "string",
                            "description": "json string of the browser profile to be used. ",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)


    tool_schema = types.Tool(
        name="os_reconnect_wifi",
        description="<category>System</category><sub-category>Network</sub-category>use shell command to reconnect wifi (assume wifi access point porfiles exist).",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["network_name", "post_wait"],
                    "properties": {
                        "network_name": {
                            "type": "string",
                            "description": "name of the wifi access point.",
                        },
                        "post_wait": {
                            "type": "integer",
                            "description": "wait number of seconds after attempting to open the url site",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="os_open_app",
        description="<category>System</category><sub-category>General Applications</sub-category>in OS, open an app.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["app_name"],
                    "properties": {
                        "app_name": {
                            "type": "string",
                            "description": "the name of the app to open.",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="os_close_app",
        description="<category>System</category><sub-category>General Applications</sub-category>in OS, close an app.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["app_name"],
                    "properties": {
                        "app_name": {
                            "type": "string",
                            "description": "the name of the app to close.",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="os_switch_to_app",
        description="<category>System</category><sub-category>General Applications</sub-category>in OS, switch an app to foreground.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["win_title"],
                    "properties": {
                        "win_title": {
                            "type": "string",
                            "description": "the title of the app window.",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="python_run_extern",
        description="<category>System</category><sub-category>Run Code</sub-category>run a python script",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["code"],
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "syntax free python script's source code in string format, ready to be called by exec()",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="os_list_dir",
        description="<category>System</category><sub-category>File System</sub-category>in OS, list files and directories in a given path. Returns a list of file/directory names with optional filtering by pattern.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["dir_path"],
                    "properties": {
                        "dir_path": {
                            "type": "string",
                            "description": "the directory path to list contents of",
                        },
                        "pattern": {
                            "type": "string",
                            "description": "optional glob pattern to filter files (e.g., '*.txt', '*.py'). Default is '*' for all files.",
                        },
                        "recursive": {
                            "type": "boolean",
                            "description": "if true, list files recursively in subdirectories. Default is false.",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="os_make_dir",
        description="<category>System</category><sub-category>File System</sub-category>in OS, make a directory",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["dir_path"],
                    "properties": {
                        "dir_path": {
                            "type": "string",
                            "description": "the dir path to be created",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="os_delete_dir",
        description="<category>System</category><sub-category>File System</sub-category>in OS, delete a directory recursively",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["dir_path"],
                    "properties": {
                        "dir_path": {
                            "type": "string",
                            "description": "the dir path to be deleted",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="os_delete_file",
        description="<category>System</category><sub-category>File System</sub-category>in OS, delete a file",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["file"],
                    "properties": {
                        "file": {
                            "type": "string",
                            "description": "the full path of the file to be deleted",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="os_move_file",
        description="<category>System</category><sub-category>File System</sub-category>in OS, move a file from one location to anther",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["src", "dest"],
                    "properties": {
                        "src": {
                            "type": "string",
                            "description": "the full path of the file to be moved",
                        },
                        "dest": {
                            "type": "string",
                            "description": "the full path of the dir the file will be moved to",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="os_copy_file_dir",
        description="<category>System</category><sub-category>File System</sub-category>in OS, copy a file or directory from one location to anther",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["src", "dest"],
                    "properties": {
                        "src": {
                            "type": "string",
                            "description": "the full path of the file or dirto be copied",
                        },
                        "dest": {
                            "type": "string",
                            "description": "the full path of the file or dir will be copied to",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="os_seven_zip",
        description="<category>System</category><sub-category>File System</sub-category>Compress or extract files using 7-Zip. Operation is determined by dest extension: if dest ends with .7z/.zip/.tar/.gz/.bz2/.xz, it compresses src into dest archive; otherwise it extracts src archive to dest directory.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["src", "dest"],
                    "properties": {
                        "src": {
                            "type": "string",
                            "description": "For compression: the file or directory to compress. For extraction: the archive file to extract.",
                        },
                        "dest": {
                            "type": "string",
                            "description": "For compression: the output archive path (must end with .7z, .zip, .tar, .gz, .bz2, or .xz). For extraction: the output directory path.",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="os_kill_processes",
        description="<category>System</category><sub-category>Process Management</sub-category>OS kill processes",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["apps"],
                    "properties": {
                        "apps": {
                            "type": "[string]",
                            "description": "the processes to be killed, all digits meaning process ID, otherwise, process name",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="api_ecan_ai_query_components",
        description="<category>API</category><sub-category>ECAN Search</sub-category>send ecan_ai API to query components and get their parametric filter values.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["components"],
                    "properties": {
                        "components": {
                            "type": "array",
                            "description": "list of components with basic attributes.",
                            "items": {
                                "type": "object"
                            }
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="api_ecan_ai_query_fom",
        description="<category>API</category><sub-category>ECAN Search</sub-category>send ecan_ai API to query figure of merit for an component.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["component_results_info"],  # the root requires *input*
                    "properties": {
                        "input": {  # nested object
                            "type": "object",
                            "required": ["component_name", "product_app", "params"],
                            "properties": {
                                "component_name": {
                                    "type": "string",
                                    "description": "name of the component."
                                },
                                "product_app": {
                                    "type": "array",
                                    "description": "list of products or applications.",
                                    "items": {
                                        "type": "string"
                                    }
                                },
                                "params": {
                                    "type": "array",
                                    "description": "list of parameters in dict.",
                                    "items": {
                                        "type": "object"
                                    }
                                }
                            },
                        }
                    }
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="api_ecan_ai_img2text_icons",
        description="<category>API</category><sub-category>ECAN OCR</sub-category>run API to convert image to text and icons matching including generate the text and icons' location cooridnates.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["win_title_keyword"],
                    "properties": {
                        "win_title_keyword": {
                            "type": "string",
                            "description": "do OCR on the window whose window title with the keyword",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)


    tool_schema = types.Tool(
        name="api_ecan_ai_cloud_search",
        description="<category>API</category><sub-category>ECAN Search</sub-category>run API to search components.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["setup"],
                    "properties": {
                        "setup": {
                            "type": "object",
                            "description": "setup contains component preliminary info, parametric filter values, and result figure of merit schemes.",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)




    tool_schema = types.Tool(
        name="api_ecan_ai_rerank_results",
        description="<category>API</category><sub-category>ECAN Search</sub-category>run cloud API to re-rank search results based on human boss specified figure of merit.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["agent_id", "setup"],
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "calling agent id",
                        },
                        "setup": {
                            "type": "object",
                            "description": "setup contains component preliminary info, parametric filter values, and result figure of merit schemes.",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)



    tool_schema = types.Tool(
        name="api_ecan_ai_cloud_search",
        description="<category>API</category><sub-category>ECAN Search</sub-category>run cloud API to do search using cloud hosted search specialist agent.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["setup"],
                    "properties": {
                        "setup": {
                            "type": "object",
                            "description": "setup contains component preliminary info, parametric filter values, and result figure of merit schemes.",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)


    tool_schema = types.Tool(
        name="ecan_local_search_components",
        description="<category>Local Search</category><sub-category>ECAN Search</sub-category>Locally search components on designated site with parametric filters.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["components", "urls", "parametric_filters", "fom_form", "max_n_results"],
                    "properties": {
                        "components": {
                            "type": "array",
                            "description": "optional: list of components with basic attributes.",
                            "items": {"type": "object"}
                        },
                        "urls": {
                            "type": "object",
                            "description": "categories dict with site names as the keys",
                        },
                        "parametric_filters": {
                            "type": "array",
                            "description": "parametric filters to be used in search.",
                        },
                        "fom_form": {
                            "type": "object",
                            "description": "figure of merit data to be used in ranking search results.",
                        },
                        "max_n_results": {
                            "type": "integer",
                            "description": "max number of results to return.",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="ecan_local_sort_search_results",
        description="<category>Local Search</category><sub-category>ECAN Search</sub-category>locally sort search results based on certain column header text either in ascending order or descending order, then extract top max_n rows of results.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["sites"],
                    "properties": {
                        "sites": {
                            "type": "array",
                            "description": "list of json objects with basic attributes of url, header_text, ascending, and max_n.",
                            "items": {
                                "type": "object",
                                "required": ["url", "header_text", "ascending", "max_n"],
                                "properties": {
                                    "url": {"type": "string"},
                                    "header_text": {"type": "string"},
                                    "ascending": {"type": "boolean"},
                                    "max_n": {"type": "integer"}
                                }
                            }
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)


    add_get_ebay_summary_tool_schema(tool_schemas)
    add_ebay_fullfill_next_order_tool_schema(tool_schemas)
    add_ebay_cancel_orders_tool_schema(tool_schemas)
    add_ebay_read_next_message_tool_schema(tool_schemas)
    add_ebay_read_all_messages_tool_schema(tool_schemas)
    add_ebay_respond_to_message_tool_schema(tool_schemas)
    add_ebay_search_tool_schema(tool_schemas)
    add_ebay_gen_labels_tool_schema(tool_schemas)
    add_ebay_cancel_labels_tool_schema(tool_schemas)
    add_ebay_handle_return_tool_schema(tool_schemas)
    add_ebay_handle_refund_tool_schema(tool_schemas)
    add_ebay_add_listings_tool_schema(tool_schemas)
    add_ebay_remove_listings_tool_schema(tool_schemas)
    add_ebay_update_listings_tool_schema(tool_schemas)
    add_ebay_get_listings_tool_schema(tool_schemas)
    add_ebay_add_listing_templates_tool_schema(tool_schemas)
    add_ebay_remove_listing_templates_tool_schema(tool_schemas)
    add_ebay_update_listing_templates_tool_schema(tool_schemas)
    add_ebay_collect_campaigns_stats_tool_schema(tool_schemas)
    add_ebay_adjust_campaigns_tool_schema(tool_schemas)
    add_ebay_collect_shop_products_stats_tool_schema(tool_schemas)
    add_ebay_generate_work_summary_tool_schema(tool_schemas)


    add_get_etsy_summary_tool_schema(tool_schemas)
    add_etsy_fullfill_next_order_tool_schema(tool_schemas)
    add_etsy_handle_next_message_tool_schema(tool_schemas)
    add_etsy_search_tool_schema(tool_schemas)
    add_etsy_handle_return_tool_schema(tool_schemas)
    add_etsy_handle_refund_tool_schema(tool_schemas)
    add_etsy_add_listings_tool_schema(tool_schemas)
    add_etsy_remove_listings_tool_schema(tool_schemas)
    add_etsy_update_listings_tool_schema(tool_schemas)
    add_etsy_get_listings_tool_schema(tool_schemas)
    add_etsy_add_listing_templates_tool_schema(tool_schemas)
    add_etsy_remove_listing_templates_tool_schema(tool_schemas)
    add_etsy_update_listing_templates_tool_schema(tool_schemas)
    add_etsy_collect_campaigns_stats_tool_schema(tool_schemas)
    add_etsy_adjust_campaigns_tool_schema(tool_schemas)
    add_etsy_collect_shop_products_stats_tool_schema(tool_schemas)
    add_etsy_generate_work_summary_tool_schema(tool_schemas)


    add_get_amazon_summary_tool_schema(tool_schemas)
    add_amazon_fullfill_next_order_tool_schema(tool_schemas)
    add_amazon_handle_next_message_tool_schema(tool_schemas)
    add_amazon_search_tool_schema(tool_schemas)
    add_amazon_handle_return_tool_schema(tool_schemas)
    add_amazon_handle_refund_tool_schema(tool_schemas)
    add_amazon_add_listings_tool_schema(tool_schemas)
    add_amazon_remove_listings_tool_schema(tool_schemas)
    add_amazon_update_listings_tool_schema(tool_schemas)
    add_amazon_get_listings_tool_schema(tool_schemas)
    add_amazon_add_listing_templates_tool_schema(tool_schemas)
    add_amazon_remove_listing_templates_tool_schema(tool_schemas)
    add_amazon_update_listing_templates_tool_schema(tool_schemas)
    add_amazon_collect_campaigns_stats_tool_schema(tool_schemas)
    add_amazon_adjust_campaigns_tool_schema(tool_schemas)
    add_amazon_collect_shop_products_stats_tool_schema(tool_schemas)
    add_amazon_generate_work_summary_tool_schema(tool_schemas)

    # add_get_walmart_summary_tool_schema(tool_schemas)
    # add_walmart_fullfill_next_order_tool_schema(tool_schemas)
    # add_walmart_handle_next_message_tool_schema(tool_schemas)
    #
    # add_get_wayfair_summary_tool_schema(tool_schemas)
    # add_wayfair_fullfill_next_order_tool_schema(tool_schemas)
    # add_wayfair_handle_next_message_tool_schema(tool_schemas)
    #
    # add_get_chewy_summary_tool_schema(tool_schemas)
    # add_chewy_fullfill_next_order_tool_schema(tool_schemas)
    # add_chewy_handle_next_message_tool_schema(tool_schemas)

    add_get_shopify_summary_tool_schema(tool_schemas)
    add_shopify_fullfill_next_order_tool_schema(tool_schemas)
    add_shopify_handle_next_message_tool_schema(tool_schemas)

    # add_amazon_mcf_tool_schema(tool_schemas)
    # add_ebay_buy_shipping_tool_schema(tool_schemas)
    # add_pirate_shipping_buy_tool_schema(tool_schemas)

    add_print_labels_tool_schema(tool_schemas)
    add_reformat_labels_tool_schema(tool_schemas)

    add_ecan_ai_api_get_agent_status_tool_schema(tool_schemas)

    add_gmail_read_titles_tool_schema(tool_schemas)
    add_gmail_read_full_email_tool_schema(tool_schemas)
    add_gmail_respond_tool_schema(tool_schemas)
    add_gmail_write_new_tool_schema(tool_schemas)
    add_gmail_move_email_tool_schema(tool_schemas)
    add_gmail_mark_status_tool_schema(tool_schemas)
    add_gmail_delete_email_tool_schema(tool_schemas)

    add_privacy_reserve_tool_schema(tool_schemas)

    add_ragify_tool_schema(tool_schemas)

    add_rag_query_tool_schema(tool_schemas)

    # Self-introspection tools
    from agent.mcp.server.self_utils.self_tools import (
        add_describe_self_tool_schema,
        add_start_task_using_skill_tool_schema,
        add_stop_task_using_skill_tool_schema,
    )
    add_describe_self_tool_schema(tool_schemas)
    add_start_task_using_skill_tool_schema(tool_schemas)
    add_stop_task_using_skill_tool_schema(tool_schemas)

    # Code execution tools
    from agent.mcp.server.code_utils.code_tools import add_run_code_tool_schema, add_run_shell_script_tool_schema
    add_run_code_tool_schema(tool_schemas)
    add_run_shell_script_tool_schema(tool_schemas)

    # Chat/communication tools for inter-agent messaging
    from agent.mcp.server.chat_utils.chat_tools import (
        add_send_chat_tool_schema,
        add_list_chat_agents_tool_schema,
        add_get_chat_history_tool_schema,
    )
    add_send_chat_tool_schema(tool_schemas)
    add_list_chat_agents_tool_schema(tool_schemas)
    add_get_chat_history_tool_schema(tool_schemas)

    add_extern_tools_schemas(tool_schemas)

    return tool_schemas