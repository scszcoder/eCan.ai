/**
 * Cloud MCP Tools Schema for Chatter Lambda
 * 
 * JavaScript port of agent/mcp/server/tool_schemas.py
 * Defines cloud-side MCP tool schemas that agents can reference.
 * 
 * Each tool schema follows the MCP Tool format:
 *   { name, description, inputSchema, outputSchema?, meta? }
 */

const toolSchemas = [];

function addToolSchema(schema) {
  toolSchemas.push(schema);
}

/**
 * Build all cloud MCP tool schemas.
 * Returns an array of tool schema objects.
 */
export function build_cloud_mcp_tools_schema() {
  // Clear any previously built schemas
  toolSchemas.length = 0;

  // ============================================================
  // RPA Tools
  // ============================================================

  addToolSchema({
    name: "rpa_supervisor_scheduling_work",
    description: "<category>RPA</category><sub-category>Supervisor</sub-category>As a RPA supervisor, fetches daily work schedule and run team prep and get ready to dispatch the work to the operator agents on the remote hosts to work on.",
    inputSchema: {
      type: "object",
      required: [],
      properties: {},
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "rpa_operator_dispatch_works",
    description: "<category>RPA</category><sub-category>Supervisor</sub-category>As a RPA operator, it dispatches the RPA works to be performed by a platoon of bots on this host computer.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["works"],
          properties: {
            works: {
              type: "object",
              description: "work to be dones",
            },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "rpa_supervisor_process_work_results",
    description: "<category>RPA</category><sub-category>Operator</sub-category>As an RPA supervisor, update overall result with received operator work report.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["url"],
          properties: {
            url: { type: "string", description: "URL to fetch" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "rpa_supervisor_run_daily_housekeeping",
    description: "<category>RPA</category><sub-category>Operator</sub-category>As an RPA supervisor, after all work reports collected, do necessary housekeeping work such as accounting, book keeping etc.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["url"],
          properties: {
            url: { type: "string", description: "URL to fetch" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "rpa_operator_report_work_results",
    description: "<category>RPA</category><sub-category>Operator</sub-category>As an RPA operator, report work results to supervisor",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["url"],
          properties: {
            url: { type: "string", description: "URL to fetch" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  // ============================================================
  // OS Tools
  // ============================================================

  addToolSchema({
    name: "os_screen_capture",
    description: "<category>OS</category><sub-category>Screen Capture</sub-category>Do a screen shot, save to a png file and stores into a cv2 image data structure",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["win_title_kw", "sub_area", "file"],
          properties: {
            win_title_kw: { type: "string", description: 'the window title keyword for the window to be screen captured, (default is "" which means top window)' },
            sub_area: { type: "array", items: { type: "integer" }, description: "sub area of screen shot with relative offset [left, top, right, bottom]" },
            file: { type: "string", description: "full path of screen shot file name" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "os_screen_analyze",
    description: "<category>OS</category><sub-category>OCR</sub-category>do OCR and icon match on an image and result in structured text in the image",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["win_title_kw", "sub_area", "site", "engine"],
          properties: {
            win_title_kw: { type: "string", description: 'the window title keyword for the window to be screen captured, (default is "" which means top window)' },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "os_wait",
    description: "<category>OS</category><sub-category>Timer</sub-category>wait a few seconds.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["seconds"],
          properties: {
            seconds: { type: "integer", description: "number of seconds to wait" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "say_hello",
    description: "<category>OS</category><sub-category>General</sub-category>just a test.",
    inputSchema: { type: "object", required: [], properties: {} },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "get_current_time",
    description: "<category>OS</category><sub-category>Timer</sub-category>Get the current date and time in yyyy-mm-dd hh:mm:ss format.",
    inputSchema: { type: "object", required: [], properties: {} },
    meta: { run_in_cloud: false },
  });

  // ============================================================
  // PyAutoGUI Tools
  // ============================================================

  addToolSchema({
    name: "mouse_click",
    description: "<category>PyAutoGUI</category><sub-category>Mouse Action</sub-category>a mouse click function using pyautogui.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["loc", "post_move_delay", "post_click_delay"],
          properties: {
            loc: { type: "array", items: { type: "integer" }, description: "coordinates of [x, y]" },
            post_move_delay: { type: "integer", description: "wait some seconds after mouse move to the location" },
            post_click_delay: { type: "integer", description: "wait some seconds after mouse click" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "mouse_move",
    description: "<category>PyAutoGUI</category><sub-category>Mouse Action</sub-category>a mouse move/hover function using pyautogui.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["location", "post_wait"],
          properties: {
            location: { type: "array", items: { type: "integer" }, description: "coordinates of [x, y]" },
            post_wait: { type: "integer", description: "wait number of seconds after movement" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "mouse_drag_drop",
    description: "<category>PyAutoGUI</category><sub-category>Mouse Action</sub-category>a mouse drag and drop function using pyautogui.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["pick_loc", "drop_loc", "duration", "post_wait"],
          properties: {
            pick_loc: { type: "array", items: { type: "integer" }, description: "coordinates mouse pick up location of [x, y]" },
            drop_loc: { type: "array", items: { type: "integer" }, description: "coordinates mouse drop location of [x, y]" },
            duration: { type: "number", description: "time interval in seconds (could be fractional) between pick up and drop off" },
            post_wait: { type: "integer", description: "wait number of seconds after post movement" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "mouse_scroll",
    description: "<category>PyAutoGUI</category><sub-category>Mouse Action</sub-category>a mouse scroll function using pyautogui.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["direction", "amount", "post_wait"],
          properties: {
            direction: { type: "string", description: "either up or down" },
            amount: { type: "integer", description: "amount of mouse wheel scroll units" },
            post_wait: { type: "integer", description: "wait number of seconds after post movement" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "keyboard_text_input",
    description: "<category>PyAutoGUI</category><sub-category>Keyboard Action</sub-category>direct drive keyboard type in text string.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["text", "interval", "post_wait"],
          properties: {
            text: { type: "string", description: "text string to be typed in" },
            interval: { type: "number", description: "amount of time interval in seconds(can be fractional number) between key strokes" },
            post_wait: { type: "integer", description: "wait number of seconds after post movement" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "keyboard_keys_input",
    description: "<category>PyAutoGUI</category><sub-category>Keyboard Action</sub-category>direct drive keyboard type combo hot keys.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["keys", "post_wait"],
          properties: {
            keys: { type: "array", items: { type: "string" }, description: "list of keys to be keyed in, for example ['ctrl', 'x']" },
            post_wait: { type: "integer", description: "wait number of seconds after post movement" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "solve_px_captcha",
    description: "<category>PyAutoGUI</category><sub-category>Mouse Action</sub-category>solve px captcha, PerimeterX Captcha, by read screen, and emulate pressing and holding button for certain amount of time.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["keyword", "duration"],
          properties: {
            keyword: { type: "array", items: { type: "string" }, description: "the text on the button to where the mouse will be pressed and held down" },
            duration: { type: "integer", description: "press and hold for this number of seconds before releasing" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  // ============================================================
  // Browser Automation Tools
  // ============================================================

  const browserDriverProps = {
    driver_type: { type: "string", enum: ["webdriver", "cdp"], default: "webdriver", description: "Driver mode: 'webdriver' for Selenium WebDriver, 'cdp' for Chrome DevTools Protocol via BrowserSession" },
    browser_type: { type: "string", enum: ["adspower", "existing chrome", "chromium"], default: "existing chrome", description: "Browser type to use (only applicable when driver_type is 'cdp')" },
  };

  addToolSchema({
    name: "in_browser_wait_for_element",
    description: "<category>Browser Automation</category><sub-category>In Browser Search Action</sub-category>use webdriver or cdp to wait for web elements.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["driver_type", "browser_type", "element_type", "element_name", "timeout"],
          properties: {
            ...browserDriverProps,
            element_type: { type: "string", description: "web element type: ID, Name, ClassName, LinkText, PartialLinkText, TagName, CSS Selector, or XPath" },
            element_name: { type: "string", description: "name of the element" },
            timeout: { type: "integer", description: "max wait time(seconds) to find element on the page" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "in_browser_click_element_by_index",
    description: "<category>Browser Automation</category><sub-category>In Browser Mouse Action</sub-category>use webdriver or cdp to click on a web element based on index in the selector map.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["driver_type", "browser_type", "dom_index", "timeout"],
          properties: {
            ...browserDriverProps,
            dom_index: { type: "integer", description: "dom index of the element in the dom tree" },
            timeout: { type: "integer", description: "max wait time(seconds) to find element on the page" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "in_browser_click_element_by_selector",
    description: "<category>Browser Automation</category><sub-category>In Browser Mouse Action</sub-category>use webdriver or cdp to click on an web element based on css selector.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["driver_type", "browser_type", "element_type", "element_name", "timeout"],
          properties: {
            ...browserDriverProps,
            element_type: { type: "string", description: "web element type: ID, Name, ClassName, LinkText, PartialLinkText, TagName, CSS Selector, or XPath" },
            element_name: { type: "string", description: "name of the element" },
            timeout: { type: "integer", description: "max wait time(seconds) to find element on the page" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "in_browser_click_element_by_xpath",
    description: "<category>Browser Automation</category><sub-category>In Browser Mouse Action</sub-category>use webdriver or cdp to click on an web element based on xpath.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["driver_type", "browser_type", "element_type", "element_name", "timeout"],
          properties: {
            ...browserDriverProps,
            element_type: { type: "string", description: "web element type: ID, Name, ClassName, LinkText, PartialLinkText, TagName, CSS Selector, or XPath" },
            element_name: { type: "string", description: "name of the element" },
            timeout: { type: "integer", description: "max wait time(seconds) to find element on the page" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "in_browser_click_element_by_text",
    description: "<category>Browser Automation</category><sub-category>Selenium Mouse Action</sub-category>use webdriver or cdp to click on an web element based on text",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["driver_type", "browser_type", "element_type", "element_name", "timeout"],
          properties: {
            ...browserDriverProps,
            element_type: { type: "string", description: "web element type: ID, Name, ClassName, LinkText, PartialLinkText, TagName, CSS Selector, or XPath" },
            element_name: { type: "string", description: "name of the element" },
            timeout: { type: "integer", description: "max wait time(seconds) to find element on the page" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "in_browser_input_text",
    description: "<category>Browser Automation</category><sub-category>In Browser Keyboard Action</sub-category>use webdriver or cdp to key in text on a web page's input field.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["driver_type", "browser_type", "element_type", "element_name", "element_text", "nth", "timeout"],
          properties: {
            ...browserDriverProps,
            element_type: { type: "string", description: "web element type: ID, Name, ClassName, LinkText, PartialLinkText, TagName, CSS Selector, or XPath" },
            element_name: { type: "string", description: "name of the element" },
            element_text: { type: "string", description: "text of the web element" },
            nth: { type: "integer", description: "nth element of the list of elements of same type and same name" },
            timeout: { type: "integer", description: "max wait time(seconds) to find element on the page" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "in_browser_scroll",
    description: "<category>Browser Automation</category><sub-category>In Browser Mouse Action</sub-category>use webdriver or cdp to scroll within the browser.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["driver_type", "browser_type", "direction", "amount", "post_wait"],
          properties: {
            ...browserDriverProps,
            direction: { type: "string", description: "scroll direction of either up or down" },
            amount: { type: "integer", description: "number of scroll units" },
            post_wait: { type: "integer", description: "max wait time(seconds) to find element on the page" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "in_browser_send_keys",
    description: "<category>Browser Automation</category><sub-category>In Browser Keyboard Action</sub-category>use webdriver or cdp to send hot keys to the web page.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["driver_type", "browser_type", "keys"],
          properties: {
            ...browserDriverProps,
            keys: {
              type: "array",
              items: { type: "string" },
              description: "list of combo keys to send. Special keys: <ctrl> <alt> <shift> <meta> <enter> <esc> <backspace> <tab> <space> <up> <down> <left> <right> <home> <end> <pageup> <pagedown> <insert> <delete> <f1>-<f12>",
            },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "in_browser_scroll_to_text",
    description: "<category>Browser Automation</category><sub-category>In Browser Mouse Action</sub-category>use webdriver or cdp to scroll to the specified text location.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["driver_type", "browser_type", "text"],
          properties: {
            ...browserDriverProps,
            text: { type: "string", description: "text to scroll to on the page" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "in_browser_get_dropdown_options",
    description: "<category>Browser Automation</category><sub-category>In Browser Mouse Action</sub-category>use webdriver or cdp to obtains the list of selection options on the drop down list.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["driver_type", "browser_type", "pulldown_menu_name"],
          properties: {
            ...browserDriverProps,
            pulldown_menu_name: { type: "string", description: "pull down menu name" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "in_browser_select_dropdown_option",
    description: "<category>Browser Automation</category><sub-category>In Browser Mouse Action</sub-category>use webdriver or cdp to select an item on the drop down selection list.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["driver_type", "browser_type", "pulldown_item"],
          properties: {
            ...browserDriverProps,
            pulldown_item: { type: "string", description: "to be selected item text on the drop down list" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "in_browser_drag_drop",
    description: "<category>Browser Automation</category><sub-category>In Browser Mouse Action</sub-category>use webdriver or cdp to drag and drop an item. Supports both element-based (CSS selectors) and coordinate-based drag and drop.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["driver_type", "browser_type"],
          properties: {
            ...browserDriverProps,
            source_selector: { type: "string", description: "CSS selector of the source element to drag (use this OR source_x/source_y)" },
            target_selector: { type: "string", description: "CSS selector of the target element to drop onto (use this OR target_x/target_y)" },
            source_x: { type: "integer", description: "X coordinate of source position" },
            source_y: { type: "integer", description: "Y coordinate of source position" },
            target_x: { type: "integer", description: "X coordinate of target position" },
            target_y: { type: "integer", description: "Y coordinate of target position" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "in_browser_extract_content",
    description: "<category>Browser Automation</category><sub-category>In Browser Extract Content</sub-category>use cdp to extract dom tree from the web page.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["driver_type", "browser_type", "url"],
          properties: {
            ...browserDriverProps,
            url: { type: "string", format: "uri", description: "URL of the web page to open, if empty, currently opened page will be extracted." },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "in_browser_switch_tab",
    description: "<category>Browser Automation</category><sub-category>In Browser Tab Action</sub-category>use webdriver or cdp to switch to a tab in a browser.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["driver_type", "browser_type", "tab_title"],
          properties: {
            ...browserDriverProps,
            tab_title: { type: "string", description: "the title of the tab to switch to. Its dom tree will be automatically extracted after the page loads." },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "in_browser_open_tab",
    description: "<category>Browser Automation</category><sub-category>In Browser Tab Action</sub-category>use webdriver or cdp to open a new tab in a browser and open a specified URL.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["driver_type", "browser_type", "url"],
          properties: {
            ...browserDriverProps,
            url: { type: "string", format: "uri", description: "URL of the web page to be opened" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "in_browser_close_tab",
    description: "<category>Browser Automation</category><sub-category>In Browser Tab Action</sub-category>use webdriver or cdp to close a tab in a browser.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["driver_type", "browser_type", "tab_title"],
          properties: {
            ...browserDriverProps,
            tab_title: { type: "string", description: "title of the browser tab to be closed" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "in_browser_execute_javascript",
    description: "<category>Browser Automation</category><sub-category>In Browser Run Code Action</sub-category>use webdriver or cdp to execute a javascript on a web page.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["driver_type", "browser_type", "script_code"],
          properties: {
            ...browserDriverProps,
            script_code: { type: "string", description: "js script code to be executed in browser" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "in_browser_save_href_to_file",
    description: "<category>Browser Automation</category><sub-category>In Browser Download Action</sub-category>use webdriver or cdp to download a href pointed file on a web page.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["driver_type", "browser_type", "href", "saved_file_path"],
          properties: {
            ...browserDriverProps,
            href: { type: "string", format: "uri", description: "URL of the file to be downloaded" },
            saved_file_path: { type: "string", description: "Full path to save the downloaded file" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "in_browser_upload_file",
    description: "<category>Browser Automation</category><sub-category>In Browser Upload Action</sub-category>use webdriver or cdp to upload a file.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["driver_type", "browser_type", "href", "upload_file_path"],
          properties: {
            ...browserDriverProps,
            href: { type: "string", format: "uri", description: "URL of the file upload element" },
            upload_file_path: { type: "string", description: "Full path to the file to be uploaded" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "in_browser_go_to_url",
    description: "<category>Browser Automation</category><sub-category>In Browser Tab Action</sub-category>use webdriver or cdp to open a new url site.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["driver_type", "browser_type", "url"],
          properties: {
            url: { type: "string", format: "uri", description: "URL of the web page to open" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  // ============================================================
  // Browser Connection Tools
  // ============================================================

  addToolSchema({
    name: "os_connect_to_adspower",
    description: "<category>Browser Automation</category><sub-category>ADSPower Action</sub-category>connect to an already opened and logged in ADS Power and open a new tab in URL.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["url"],
          properties: {
            url: { type: "string", format: "uri", description: "URL of the web page to open" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "os_connect_to_chrome",
    description: "<category>Browser Automation</category><sub-category>Chrome Connection</sub-category>connect to an already opened chrome and open a new tab in URL.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["driver_path", "url"],
          properties: {
            driver_path: { type: "string", description: "full path to web driver to use" },
            url: { type: "string", format: "uri", description: "URL of the web page to open" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "ecan_ai_new_chromiunm",
    description: "<category>Browser Automation</category><sub-category>Launch New Chromium</sub-category>launch a new instance of chromium and open a new tab in URL.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["driver_path", "url", "profile"],
          properties: {
            driver_path: { type: "string", description: "full path to web driver to use" },
            url: { type: "string", format: "uri", description: "URL of the web page to open" },
            profile: { type: "string", description: "json string of the browser profile to be used." },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  // ============================================================
  // System Tools
  // ============================================================

  addToolSchema({
    name: "os_reconnect_wifi",
    description: "<category>System</category><sub-category>Network</sub-category>use shell command to reconnect wifi (assume wifi access point profiles exist).",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["network_name", "post_wait"],
          properties: {
            network_name: { type: "string", description: "name of the wifi access point." },
            post_wait: { type: "integer", description: "wait number of seconds after attempting to open the url site" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "os_open_app",
    description: "<category>System</category><sub-category>General Applications</sub-category>in OS, open an app.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["app_name"],
          properties: {
            app_name: { type: "string", description: "the name of the app to open." },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "os_close_app",
    description: "<category>System</category><sub-category>General Applications</sub-category>in OS, close an app.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["app_name"],
          properties: {
            app_name: { type: "string", description: "the name of the app to close." },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "os_switch_to_app",
    description: "<category>System</category><sub-category>General Applications</sub-category>in OS, switch an app to foreground.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["win_title"],
          properties: {
            win_title: { type: "string", description: "the title of the app window." },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "python_run_extern",
    description: "<category>System</category><sub-category>Run Code</sub-category>run a python script",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["code"],
          properties: {
            code: { type: "string", description: "syntax free python script's source code in string format, ready to be called by exec()" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  // ============================================================
  // File System Tools
  // ============================================================

  addToolSchema({
    name: "os_list_dir",
    description: "<category>System</category><sub-category>File System</sub-category>in OS, list files and directories in a given path.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["dir_path"],
          properties: {
            dir_path: { type: "string", description: "the directory path to list contents of" },
            pattern: { type: "string", description: "optional glob pattern to filter files (e.g., '*.txt', '*.py'). Default is '*' for all files." },
            recursive: { type: "boolean", description: "if true, list files recursively in subdirectories. Default is false." },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "os_make_dir",
    description: "<category>System</category><sub-category>File System</sub-category>in OS, make a directory",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["dir_path"],
          properties: {
            dir_path: { type: "string", description: "the dir path to be created" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "os_delete_dir",
    description: "<category>System</category><sub-category>File System</sub-category>in OS, delete a directory recursively",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["dir_path"],
          properties: {
            dir_path: { type: "string", description: "the dir path to be deleted" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "os_delete_file",
    description: "<category>System</category><sub-category>File System</sub-category>in OS, delete a file",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["file"],
          properties: {
            file: { type: "string", description: "the full path of the file to be deleted" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "os_move_file",
    description: "<category>System</category><sub-category>File System</sub-category>in OS, move a file from one location to another",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["src", "dest"],
          properties: {
            src: { type: "string", description: "the full path of the file to be moved" },
            dest: { type: "string", description: "the full path of the dir the file will be moved to" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "os_copy_file_dir",
    description: "<category>System</category><sub-category>File System</sub-category>in OS, copy a file or directory from one location to another",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["src", "dest"],
          properties: {
            src: { type: "string", description: "the full path of the file or dir to be copied" },
            dest: { type: "string", description: "the full path of the file or dir will be copied to" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "os_seven_zip",
    description: "<category>System</category><sub-category>File System</sub-category>Compress or extract files using 7-Zip. Operation is determined by dest extension.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["src", "dest"],
          properties: {
            src: {
              oneOf: [
                { type: "string" },
                { type: "array", items: { type: "string" } },
              ],
              description: "For compression: a file path, directory, wildcard pattern, or array of paths. For extraction: the archive file path.",
            },
            dest: { type: "string", description: "For compression: the output archive path (.7z, .zip, .tar, .gz, .bz2, or .xz). For extraction: the output directory path." },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "os_kill_processes",
    description: "<category>System</category><sub-category>Process Management</sub-category>OS kill processes",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["apps"],
          properties: {
            apps: { type: "array", items: { type: "string" }, description: "the processes to be killed, all digits meaning process ID, otherwise, process name" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  // ============================================================
  // API Tools
  // ============================================================

  addToolSchema({
    name: "api_ecan_ai_query_components",
    description: "<category>API</category><sub-category>ECAN Search</sub-category>send ecan_ai API to query components and get their parametric filter values.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["components"],
          properties: {
            components: { type: "array", items: { type: "object" }, description: "list of components with basic attributes." },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "api_ecan_ai_query_fom",
    description: "<category>API</category><sub-category>ECAN Search</sub-category>send ecan_ai API to query figure of merit for a component.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["component_name", "product_app", "params"],
          properties: {
            component_name: { type: "string", description: "name of the component." },
            product_app: { type: "array", items: { type: "string" }, description: "list of products or applications." },
            params: { type: "array", items: { type: "object" }, description: "list of parameters in dict." },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "api_ecan_ai_img2text_icons",
    description: "<category>API</category><sub-category>ECAN OCR</sub-category>run API to convert image to text and icons matching including generate the text and icons' location coordinates.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["win_title_keyword"],
          properties: {
            win_title_keyword: { type: "string", description: "do OCR on the window whose window title with the keyword" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "api_ecan_ai_cloud_search",
    description: "<category>API</category><sub-category>ECAN Search</sub-category>run cloud API to do search using cloud hosted search specialist agent.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["setup"],
          properties: {
            setup: { type: "object", description: "setup contains component preliminary info, parametric filter values, and result figure of merit schemes." },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "api_ecan_ai_rerank_results",
    description: "<category>API</category><sub-category>ECAN Search</sub-category>run cloud API to re-rank search results based on human boss specified figure of merit.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["agent_id", "setup"],
          properties: {
            agent_id: { type: "string", description: "calling agent id" },
            setup: { type: "object", description: "setup contains component preliminary info, parametric filter values, and result figure of merit schemes." },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "ecan_local_search_components",
    description: "<category>Local Search</category><sub-category>ECAN Search</sub-category>Locally search components on designated site with parametric filters.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["components", "urls", "parametric_filters", "fom_form", "max_n_results"],
          properties: {
            components: { type: "array", items: { type: "object" }, description: "optional: list of components with basic attributes." },
            urls: { type: "object", description: "categories dict with site names as the keys" },
            parametric_filters: { type: "array", description: "parametric filters to be used in search." },
            fom_form: { type: "object", description: "figure of merit data to be used in ranking search results." },
            max_n_results: { type: "integer", description: "max number of results to return." },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "ecan_local_sort_search_results",
    description: "<category>Local Search</category><sub-category>ECAN Search</sub-category>locally sort search results based on certain column header text either in ascending order or descending order.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["sites"],
          properties: {
            sites: {
              type: "array",
              items: {
                type: "object",
                required: ["url", "header_text", "ascending", "max_n"],
                properties: {
                  url: { type: "string" },
                  header_text: { type: "string" },
                  ascending: { type: "boolean" },
                  max_n: { type: "integer" },
                },
              },
              description: "list of json objects with basic attributes of url, header_text, ascending, and max_n.",
            },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  // ============================================================
  // E-Commerce Platform Tools (commented out in Python, included as stubs)
  // These are registered dynamically from external schema modules
  // ============================================================

  // ============================================================
  // Label / Shipping Tools
  // ============================================================

  addToolSchema({
    name: "print_labels",
    description: "<category>Shipping</category><sub-category>Labels</sub-category>Print shipping labels to a printer.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["labels"],
          properties: {
            labels: { type: "array", items: { type: "object" }, description: "list of label objects to print" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "reformat_labels",
    description: "<category>Shipping</category><sub-category>Labels</sub-category>Reformat shipping labels to a different format.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["labels", "format"],
          properties: {
            labels: { type: "array", items: { type: "object" }, description: "list of label objects to reformat" },
            format: { type: "string", description: "target format for the labels" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  // ============================================================
  // Agent Communication Tools
  // ============================================================

  addToolSchema({
    name: "ecan_ai_api_get_agent_status",
    description: "<category>API</category><sub-category>Agent Management</sub-category>Get the status of an agent via eCan.ai API.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["agent_id"],
          properties: {
            agent_id: { type: "string", description: "ID of the agent to get status for" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "ecan_ai_api_req_create_scene",
    description: "<category>API</category><sub-category>Agent Management</sub-category>Request creation of a new scene via eCan.ai API.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["scene_config"],
          properties: {
            scene_config: { type: "object", description: "configuration object for the new scene" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  // ============================================================
  // Gmail Tools
  // ============================================================

  addToolSchema({
    name: "gmail_read_titles",
    description: "<category>Gmail</category><sub-category>Read</sub-category>Read email titles from Gmail inbox.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["folder"],
          properties: {
            folder: { type: "string", description: "Gmail folder to read from (e.g., INBOX, SENT)" },
            max_results: { type: "integer", description: "maximum number of email titles to return" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "gmail_read_full_email",
    description: "<category>Gmail</category><sub-category>Read</sub-category>Read the full content of a specific email from Gmail.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["email_id"],
          properties: {
            email_id: { type: "string", description: "ID of the email to read" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "gmail_respond",
    description: "<category>Gmail</category><sub-category>Write</sub-category>Respond to an email in Gmail.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["email_id", "body"],
          properties: {
            email_id: { type: "string", description: "ID of the email to respond to" },
            body: { type: "string", description: "response email body content" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "gmail_write_new",
    description: "<category>Gmail</category><sub-category>Write</sub-category>Compose and send a new email via Gmail.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["to", "subject", "body"],
          properties: {
            to: { type: "string", description: "recipient email address" },
            subject: { type: "string", description: "email subject" },
            body: { type: "string", description: "email body content" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "gmail_move_email",
    description: "<category>Gmail</category><sub-category>Organize</sub-category>Move an email to a different folder/label in Gmail.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["email_id", "target_folder"],
          properties: {
            email_id: { type: "string", description: "ID of the email to move" },
            target_folder: { type: "string", description: "target folder/label name" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "gmail_mark_status",
    description: "<category>Gmail</category><sub-category>Organize</sub-category>Mark email read/unread/starred/important in Gmail.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["email_id", "status"],
          properties: {
            email_id: { type: "string", description: "ID of the email" },
            status: { type: "string", description: "status to set (read, unread, starred, important)" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "gmail_delete_email",
    description: "<category>Gmail</category><sub-category>Organize</sub-category>Delete an email in Gmail.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["email_id"],
          properties: {
            email_id: { type: "string", description: "ID of the email to delete" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  // ============================================================
  // Privacy Tools
  // ============================================================

  addToolSchema({
    name: "privacy_reserve",
    description: "<category>Privacy</category><sub-category>Data Protection</sub-category>Reserve privacy-sensitive data for secure processing.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["data_type"],
          properties: {
            data_type: { type: "string", description: "type of data to reserve for privacy protection" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  // ============================================================
  // RAG Tools
  // ============================================================

  addToolSchema({
    name: "ragify",
    description: "<category>RAG</category><sub-category>Indexing</sub-category>Index documents into RAG knowledge base.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["source"],
          properties: {
            source: { type: "string", description: "source path or URL to index" },
            chunk_size: { type: "integer", description: "optional chunk size for splitting documents" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "rag_query",
    description: "<category>RAG</category><sub-category>Query</sub-category>Query the RAG knowledge base.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["query"],
          properties: {
            query: { type: "string", description: "search query for the knowledge base" },
            top_k: { type: "integer", description: "number of top results to return" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "wait_for_rag_completion",
    description: "<category>RAG</category><sub-category>Indexing</sub-category>Wait for an async RAG indexing job to complete.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["job_id"],
          properties: {
            job_id: { type: "string", description: "ID of the RAG indexing job to wait for" },
            timeout: { type: "integer", description: "max seconds to wait" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "ragify_async",
    description: "<category>RAG</category><sub-category>Indexing</sub-category>Asynchronously index documents into RAG knowledge base.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["source"],
          properties: {
            source: { type: "string", description: "source path or URL to index" },
            chunk_size: { type: "integer", description: "optional chunk size for splitting documents" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  // ============================================================
  // Self-Introspection Tools
  // ============================================================

  addToolSchema({
    name: "describe_self",
    description: "<category>Agent</category><sub-category>Self</sub-category>Describe the agent's own capabilities and configuration.",
    inputSchema: { type: "object", required: [], properties: {} },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "start_task_using_skill",
    description: "<category>Agent</category><sub-category>Task</sub-category>Start a task using a specific skill.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["skill_name"],
          properties: {
            skill_name: { type: "string", description: "name of the skill to use" },
            parameters: { type: "object", description: "parameters to pass to the skill" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "stop_task_using_skill",
    description: "<category>Agent</category><sub-category>Task</sub-category>Stop a running task.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["task_id"],
          properties: {
            task_id: { type: "string", description: "ID of the task to stop" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "schedule_task",
    description: "<category>Agent</category><sub-category>Task</sub-category>Schedule a task to run at a specific time or interval.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["skill_name", "schedule"],
          properties: {
            skill_name: { type: "string", description: "name of the skill to schedule" },
            schedule: { type: "string", description: "cron expression or ISO datetime for scheduling" },
            parameters: { type: "object", description: "parameters to pass to the skill" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  // ============================================================
  // Code Execution Tools
  // ============================================================

  addToolSchema({
    name: "run_code",
    description: "<category>System</category><sub-category>Run Code</sub-category>Execute code in a sandboxed environment.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["language", "code"],
          properties: {
            language: { type: "string", description: "programming language (python, javascript, bash)" },
            code: { type: "string", description: "source code to execute" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "run_shell_script",
    description: "<category>System</category><sub-category>Run Code</sub-category>Execute a shell script.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["script"],
          properties: {
            script: { type: "string", description: "shell script content to execute" },
            shell: { type: "string", description: "shell to use (bash, sh, zsh). Default is bash." },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "grep_search",
    description: "<category>System</category><sub-category>Search</sub-category>Search for text patterns in files using grep.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["pattern", "path"],
          properties: {
            pattern: { type: "string", description: "search pattern (regex supported)" },
            path: { type: "string", description: "directory or file path to search in" },
            recursive: { type: "boolean", description: "search recursively in subdirectories" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  addToolSchema({
    name: "find_files",
    description: "<category>System</category><sub-category>Search</sub-category>Find files matching a pattern.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["path"],
          properties: {
            path: { type: "string", description: "directory to search in" },
            name: { type: "string", description: "file name pattern to match" },
            type: { type: "string", description: "file type filter (f=file, d=directory)" },
          },
        },
      },
    },
    meta: { run_in_cloud: false },
  });

  // ============================================================
  // Chat / Communication Tools
  // ============================================================

  addToolSchema({
    name: "send_chat",
    description: "<category>Communication</category><sub-category>Chat</sub-category>Send a chat message to another agent.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["recipient_id", "message"],
          properties: {
            recipient_id: { type: "string", description: "ID of the agent to send the message to" },
            message: { type: "string", description: "message content" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "list_chat_agents",
    description: "<category>Communication</category><sub-category>Chat</sub-category>List available agents for chat communication.",
    inputSchema: { type: "object", required: [], properties: {} },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "get_chat_history",
    description: "<category>Communication</category><sub-category>Chat</sub-category>Get chat history with a specific agent.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["agent_id"],
          properties: {
            agent_id: { type: "string", description: "ID of the agent to get chat history with" },
            limit: { type: "integer", description: "max number of messages to return" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  // ============================================================
  // Cloud Cost Monitoring Tools
  // ============================================================

  addToolSchema({
    name: "aws_read_billing",
    description: "<category>Cloud</category><sub-category>AWS</sub-category>Read AWS billing and cost data.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["period"],
          properties: {
            period: { type: "string", description: "billing period (e.g., 'current_month', 'last_month', or ISO date range)" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "aws_shutdown",
    description: "<category>Cloud</category><sub-category>AWS</sub-category>Emergency shutdown of AWS resources to control costs.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["resource_type"],
          properties: {
            resource_type: { type: "string", description: "type of AWS resource to shut down (ec2, rds, ecs, etc.)" },
            resource_id: { type: "string", description: "specific resource ID to shut down (optional - shuts down all of type if omitted)" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "azure_read_billing",
    description: "<category>Cloud</category><sub-category>Azure</sub-category>Read Azure billing and cost data.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["period"],
          properties: {
            period: { type: "string", description: "billing period" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "azure_shutdown",
    description: "<category>Cloud</category><sub-category>Azure</sub-category>Emergency shutdown of Azure resources to control costs.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["resource_type"],
          properties: {
            resource_type: { type: "string", description: "type of Azure resource to shut down" },
            resource_id: { type: "string", description: "specific resource ID to shut down" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "gcloud_read_billing",
    description: "<category>Cloud</category><sub-category>GCP</sub-category>Read Google Cloud billing and cost data.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["period"],
          properties: {
            period: { type: "string", description: "billing period" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "gcloud_shutdown",
    description: "<category>Cloud</category><sub-category>GCP</sub-category>Emergency shutdown of Google Cloud resources to control costs.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["resource_type"],
          properties: {
            resource_type: { type: "string", description: "type of GCP resource to shut down" },
            resource_id: { type: "string", description: "specific resource ID to shut down" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  console.log(`[tools_schema] Built ${toolSchemas.length} cloud MCP tool schemas`);
  return [...toolSchemas];
}

/**
 * Get all tool schemas (builds them if not yet built).
 */
export function get_cloud_mcp_tools_schema() {
  if (toolSchemas.length === 0) {
    build_cloud_mcp_tools_schema();
  }
  return [...toolSchemas];
}
