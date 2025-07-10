import mcp.types as types

tool_schemas = []

def get_tool_schemas():
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
        name="screen_capture",
        description="Do a screen shot, save to a png file and stores into a cv2 image data structure",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["file_name"],
                    "properties": {
                        "file_name": {
                            "type": "string",
                            "description": "screen shot file name",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    tool_schema = types.Tool(
        name="screen_analyze",
        description="do OCR and icon match on an image and result in structured text in the image",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["image", "icons", "options", "end_point"],
                    "properties": {
                        "image": {
                            "type": "string",
                            "description": "image file name.",
                        },
                        "icons": {
                            "type": "[string]",
                            "description": "a list of icon file names",
                        },
                        "options": {
                            "type": "dict",
                            "description": "various run options",
                        },
                        "end_point": {
                            "type": "string",
                            "description": "a choice of local/lan/wan",
                        },
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
                            "type": "int",
                            "description": "wait some seconds after mouse move to the location",
                        },
                        "post_click_delay": {
                            "type": "int",
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
                            "type": "int",
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
                            "type": "int",
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
                            "type": "int",
                            "description": "amount of mouse wheel scroll units",
                        },
                        "post_wait": {
                            "type": "int",
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
                            "type": "int",
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
                            "type": "int",
                            "description": "wait number of seconds after post movement",
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
                            "type": "int",
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
                            "type": "int",
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
                            "type": "int",
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
                            "type": "int",
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
                            "type": "int",
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
                            "type": "int",
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
                            "type": "int",
                            "description": "nth element of the list of elements of same type and same name",
                        },
                        "timeout": {
                            "type": "int",
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
                            "type": "int",
                            "description": "number of scroll units",
                        },
                        "post_wait": {
                            "type": "int",
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
                            "type": "int",
                            "description": "wait number of seconds after attempting to open the url site",
                        }
                    },
                }
            }
        },
    )

    add_tool_schema(tool_schema)

    return tool_schemas