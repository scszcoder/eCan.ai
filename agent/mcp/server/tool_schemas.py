import mcp.types as types
from agent.mcp.server.scrapers.amazon_seller.amazon_orders_scrape import add_get_amazon_summary_tool_schema, add_amazon_fullfill_next_order_tool_schema
from agent.mcp.server.scrapers.amazon_seller.amazon_messages_scrape import add_amazon_handle_next_message_tool_schema

from agent.mcp.server.scrapers.ebay_seller.ebay_orders_scrape import add_get_ebay_summary_tool_schema, add_ebay_fullfill_next_order_tool_schema, add_ebay_cancel_orders_tool_schema
from agent.mcp.server.scrapers.ebay_seller.ebay_messages_scrape import add_ebay_read_next_message_tool_schema, add_ebay_respond_to_message_tool_schema
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

from agent.mcp.server.scrapers.etsy_seller.etsy_orders_scrape import add_get_etsy_summary_tool_schema, add_etsy_fullfill_next_order_tool_schema
from agent.mcp.server.scrapers.etsy_seller.etsy_messages_scrape import add_etsy_handle_next_message_tool_schema

from agent.mcp.server.scrapers.shopify_seller.shopify_orders_scrape import add_get_shopify_summary_tool_schema, add_shopify_fullfill_next_order_tool_schema
from agent.mcp.server.scrapers.shopify_seller.shopify_messages_scrape import add_shopify_handle_next_message_tool_schema

from agent.mcp.server.scrapers.pirate_shipping.purchase_label import add_pirate_shipping_purchase_labels_tool_schema
from agent.mcp.server.utils.print_utils import add_reformat_and_print_labels_tool_schema
from agent.mcp.server.api.ecan_ai.ecan_ai_api import add_ecan_ai_api_get_agent_status_tool_schema
from agent.ec_skills.rag.local_rag_mcp import add_ragify_tool_schema, add_rag_query_tool_schema

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
            description="As a RPA supervisor, fetches daily work schedule and run team prep and get ready to dispatch the work to the operator agents on the remote hosts to work on.",
            inputSchema={
                "type": "object",
                "required": [],
                "properties": {},
            },
        )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="rpa_operator_dispatch_works",
        description="As a RPA operator, it dispatches the RPA works to be performed by a platoon of bots on this host computer.",
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
        description="As an RPA supervisor, update overall result with received operator work report.",
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
        description="As an RPA supervisor, after all work reports collected, do necessary housekeeping work such as accounting, book keeping etc.",
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
        description="As an RPA operator, report work results to supervisor",
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
        description="Do a screen shot, save to a png file and stores into a cv2 image data structure",
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
        description="do OCR and icon match on an image and result in structured text in the image",
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
        description="a mouse click function using pyautogui.",
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
        description="a mouse move/hover function using pyautogui.",
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
        description="a mouse drag and drop function using pyautogui.",
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
        description="a mouse scroll function using pyautogui.",
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
        description="keyboard type in text string.",
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
        description="keyboard type combo hot keys.",
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
        description="solve px captcha, PerimeterX Captcha, by read screen, and emulate pressing and holding button for certin amount of time.",
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
        description="wait a few seconds.",
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
        description="just a test.",
        inputSchema={
            "type": "object",
            "required": [],
            "properties": {},
        },
    )

    add_tool_schema(tool_schema)


    tool_schema = types.Tool(
        name="in_browser_wait_for_element",
        description="use python web tool to wait for web elements.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["element_type", "element_name", "timeout"],  # url is required *inside* input
                    "properties": {
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
        description="use selenium to click on a web element based on index in the selector map.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["element_type", "element_name", "timeout"],  # url is required *inside* input
                    "properties": {
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
        name="in_browser_click_element_by_selector",
        description="use selenium to click on an web element based on selector.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["element_type", "element_name", "timeout"],  # url is required *inside* input
                    "properties": {
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
        description="use selenium to click on an web element based on xpath.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["element_type", "element_name", "timeout"],  # url is required *inside* input
                    "properties": {
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
        description="use selenium to click on an web element based on text",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["element_type", "element_name", "timeout"],  # url is required *inside* input
                    "properties": {
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
        description="key in text on a web page's input field.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["element_type", "element_name", "element_text", "nth", "timeout"],  # url is required *inside* input
                    "properties": {
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
        description="use browser driver like selenium or playwright to scroll within the browser.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["direction", "amount", "post_wait"],  # url is required *inside* input
                    "properties": {
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
        description="use browser driver like selenium or playwright to send hot keys to the web page.",
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
        name="in_browser_scroll_to_text",
        description="use browser driver like selenium or playwright to scroll to the specified text location.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["text"],  # url is required *inside* input
                    "properties": {
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
        description="use browser driver like selenium or playwright to obtains the list of selection options on the drop down list.",
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
        name="in_browser_select_dropdown_option",
        description="use browser driver like selenium or playwright to select an item on the drop down selection list.",
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
        name="in_browser_drag_drop",
        description="use browser driver like selenium or playwright to drag and drop an item.",
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
        name="in_browser_multi_actions",
        description="use browser driver to execute a series of actions specified by the input json data.",
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
        name="in_browser_extract_content",
        description="use browser driver like selenium or playwright to drag and drop an item.",
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
        name="in_browser_switch_tab",
        description="use browser driver like selenium or playwright to drag and drop an item.",
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
        name="in_browser_open_tab",
        description="use browser driver like selenium or playwright to drag and drop an item.",
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
        name="in_browser_close_tab",
        description="use browser driver like selenium or playwright to drag and drop an item.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["tab_title"],  # url is required *inside* input
                    "properties": {
                        "tab_title": {
                            "type": "string",
                            "description": "title of the web page to open",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="in_browser_scrape_content",
        description="use browser driver like selenium or playwright to drag and drop an item.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["tab_title"],  # url is required *inside* input
                    "properties": {
                        "tab_title": {
                            "type": "string",
                            "description": "title of the web page to open",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="in_browser_execute_javascript",
        description="use browser driver to execute a javascript on a web page.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["tab_title"],  # url is required *inside* input
                    "properties": {
                        "tab_title": {
                            "type": "string",
                            "description": "title of the web page to open",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="in_browser_build_dom_tree",
        description="build DOM tree of a web page.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["tab_title"],  # url is required *inside* input
                    "properties": {
                        "tab_title": {
                            "type": "string",
                            "description": "title of the web page to open",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="in_browser_save_href_to_file",
        description="download a href pointed file on a web page.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["tab_title"],  # url is required *inside* input
                    "properties": {
                        "tab_title": {
                            "type": "string",
                            "description": "title of the web page to open",
                        }
                    },
                }
            },
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="in_browser_download_file",
        description="use browser driver like selenium or playwright to drag and drop an item.",
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
        name="in_browser_go_to_url",
        description="use browser driver like selenium or playwright to open a new url site.",
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
        name="in_browser_run_js",
        description="use browser driver like selenium or playwright to inject js script into the page.",
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
        name="os_connect_to_adspower",
        description="connect to an already opened and logged in ADS Power and open a new tab in URL.",
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
        description="connect to an already opened chrome and open a new tab in URL.",
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
        name="os_reconnect_wifi",
        description="use shell command to reconnect wifi (assume wifi access point porfiles exist).",
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
        description="in OS, open an app.",
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
        description="in OS, close an app.",
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
        description="in OS, switch an app to foreground.",
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
        description="run a python script",
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
        name="os_make_dir",
        description="in OS, make a directory",
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
        description="in OS, delete a directory recursively",
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
        description="in OS, delete a file",
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
        description="in OS, move a file from one location to anther",
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
        description="in OS, copy a file or directory from one location to anther",
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
        description="zip or unzip using 7z app",
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
                            "description": "the full path of the sourcefile or dir to be ziped or unziped",
                        },
                        "dest": {
                            "type": "string",
                            "description": "the full path of the resulting file or dir to be ziped or unziped",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="os_kill_processes",
        description="OS kill processes",
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
        description="send ecan_ai API to query components and get their parametric filter values.",
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
        description="send ecan_ai API to query figure of merit for an component.",
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
        description="run API to convert image to text and icons matching including generate the text and icons' location cooridnates.",
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
        name="api_ecan_ai_get_nodes_prompts",
        description="run API to obtain the prompts for the langggraph nodes.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["nodes", "end_point"],
                    "properties": {
                        "nodes": {
                            "type": "array",
                            "description": "list of nodes json data each with keys 'askid' and 'name'.",
                            "items": {
                                "type": "object"
                            }
                        },
                        "end_point": {
                            "type": "string",
                            "description": "either local/lan/wan, local means the algorithm runs on this host, lan means the algorithm runs on a remote computer within the LAN, wan means the algorithm runs on a remote computer on the internet, outside of the LAN",
                        },
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)


    tool_schema = types.Tool(
        name="api_ecan_ai_cloud_search",
        description="run API to search components.",
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
        description="run cloud API to re-rank search results based on human boss specified figure of merit.",
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
        description="run cloud API to do search using cloud hosted search specialist agent.",
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
        description="Locally search components on designated site with parametric filters.",
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
        description="locally sort search results based on certain column header text either in ascending order or descending order, then extract top max_n rows of results.",
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
    add_ebay_respond_to_message_tool_schema(tool_schemas)
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

    add_get_amazon_summary_tool_schema(tool_schemas)
    add_amazon_fullfill_next_order_tool_schema(tool_schemas)
    add_amazon_handle_next_message_tool_schema(tool_schemas)

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

    add_reformat_and_print_labels_tool_schema(tool_schemas)

    add_ecan_ai_api_get_agent_status_tool_schema(tool_schemas)

    add_ragify_tool_schema(tool_schemas)

    add_rag_query_tool_schema(tool_schemas)

    return tool_schemas