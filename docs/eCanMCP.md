<p align="center">
  <img src="gui_v2/src/assets/logoDark1.png" alt="" style="width:128px;"/>
</p>

# eCanMCP (eCan Model-Context-Protocol)
eCan.ai has a set of MCP tools that can be integrated with LLM to automate complicated tasks.

###### Streamable HTTP MCP Tools Integration

eCan.ai makes a set of streamable HTTP accessible MCP tools available to LLM.
Here are tools grouped in categories:
- Selenium based browser automation tools
- Vision (OCR) automation tools.
- OS level file and directory handling tools
- Custom utilities for data processing
- Generic API request tools

Here is the list of these MCP tools:


| Name                                     | Description                                             | Syntax                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
|------------------------------------------|---------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Mouse <br>Click                          | Execute a mouse click action                            | <pre>{<br>&nbsp;"type" : "Mouse Click",<br>&nbsp;&nbsp;"action": "string",<br>&nbsp;&nbsp;"action args": "string",<br>&nbsp;&nbsp;"save_rb": True/False,<br>&nbsp;&nbsp;"screen": "string",<br>&nbsp;&nbsp;"target_name": "string",<br>&nbsp;&nbsp;"target_type": "string",<br>&nbsp;&nbsp;"text": "string",<br>&nbsp;&nbsp;"nth": [x-int, y-int],<br>&nbsp;&nbsp;"offset from": "string",<br>&nbsp;&nbsp;"offset unit": "string",<br>&nbsp;&nbsp;"offset": [x-int, y-int]<br>}</pre> | 
| Mouse <br>Move                           | Execute a mouse move action                             | <pre>{<br>&nbsp;"type" : "Mouse Scroll",<br>&nbsp;&nbsp;"action": "string",<br>&nbsp;&nbsp;"screen": "string",<br>&nbsp;&nbsp;"amount": integer,<br>&nbsp;&nbsp;"resolution": "string",<br>&nbsp;&nbsp;"random_min": integer,<br>&nbsp;&nbsp;"random_max": integer,<br>&nbsp;&nbsp;"unit": "string"<br>}</pre>                                                                                                                                                                        |
| Mouse <br>Scroll                         | Execute a mouse scroll action                           | <pre>{<br>&nbsp;"type" : "Mouse Scroll",<br>&nbsp;&nbsp;"action": "string",<br>&nbsp;&nbsp;"screen": "string",<br>&nbsp;&nbsp;"amount": integer,<br>&nbsp;&nbsp;"resolution": "string",<br>&nbsp;&nbsp;"random_min": integer,<br>&nbsp;&nbsp;"random_max": integer,<br>&nbsp;&nbsp;"unit": "string"<br>}</pre>                                                                                                                                                                        | 
| Keyboard <br>Text <br>Typing             | Execute a keyboard text input action                    | <pre>{<br>&nbsp;"type" : "Text Input",<br>&nbsp;&nbsp;"action": "string",<br>&nbsp;&nbsp;"save_rb": True/False,<br>&nbsp;&nbsp;"text": "string",<br>&nbsp;&nbsp;"speed": float,<br>&nbsp;&nbsp;"key_after": "string",<br>&nbsp;&nbsp;"wait_after": "string"<br>}</pre>                                                                                                                                                                                                                | 
| Keyboard <br>Key <br>Press               | Execute a keyboard key stroke action                    | <pre>{<br>&nbsp;"type" : "Key Input",<br>&nbsp;&nbsp;"action": "string",<br>&nbsp;&nbsp;"action value": "string",<br>&nbsp;&nbsp;"save_rb": True/False,<br>&nbsp;&nbsp;"location": "string",<br>&nbsp;&nbsp;"wait_after": "string"<br>}</pre>                                                                                                                                                                                                                                         | 
| Screen <br>Content <br>Extraction        | Extract text and image info from a screen capture image | <pre>{<br>&nbsp;"type" : "Extract Info",<br>&nbsp;&nbsp;"root": obj,<br>&nbsp;&nbsp;"template": "string",<br>&nbsp;&nbsp;"option": "string",<br>&nbsp;&nbsp;"option": "string",<br>&nbsp;&nbsp;"data_sink": "string",<br>&nbsp;&nbsp;"page": "string",<br>&nbsp;&nbsp;"page_data_info": "string",<br>&nbsp;&nbsp;"theme": "string",<br>&nbsp;&nbsp;"section": "string"<br>}</pre>                                                                                                     | 
| Screen <br>Content <br>Search            | Search the result of a screen image extraction          | <pre>{<br>&nbsp;"type" : "Search",<br>&nbsp;&nbsp;"screen": "string",<br>&nbsp;&nbsp;"names": ["string"...],<br>&nbsp;&nbsp;"target_types": ["string"...],<br>&nbsp;&nbsp;"logic": "string",<br>&nbsp;&nbsp;"result": "string",<br>&nbsp;&nbsp;"site": "string",<br>&nbsp;&nbsp;"status": "string"<br>}</pre> |
| In-Browser Move (Playwright)             | In-Browser Move                                         | <pre>{<br>&nbsp;"type" : "Wait",<br>&nbsp;&nbsp;"random_min": integer,<br>&nbsp;&nbsp;"random_max": integer,<br>&nbsp;&nbsp;"time": integer<br>}</pre>                                                                                                                                                                                                                                                                                                                                | 
| In-Browser Move (Playwright)             | In-Browser Move                                         | <pre>{<br>&nbsp;"type" : "Wait",<br>&nbsp;&nbsp;"random_min": integer,<br>&nbsp;&nbsp;"random_max": integer,<br>&nbsp;&nbsp;"time": integer<br>}</pre>                                                                                                                                                                                                                                                                                                                                | 
| In-Browser Execute Script (Playwright)   | In-Browser Execute JS Script (Playwright)               | <pre>{<br>&nbsp;"type" : "Wait",<br>&nbsp;&nbsp;"random_min": integer,<br>&nbsp;&nbsp;"random_max": integer,<br>&nbsp;&nbsp;"time": integer<br>}</pre>                                                                                                                                                                                                                                                                                                                                | 
| In-Browser Wait For Element (Playwright) | In-Browser Wait For Web Element (Playwright)            | <pre>{<br>&nbsp;"type" : "Wait",<br>&nbsp;&nbsp;"random_min": integer,<br>&nbsp;&nbsp;"random_max": integer,<br>&nbsp;&nbsp;"time": integer<br>}</pre>                                                                                                                                                                                                                                                                                                                                | 
| In-Browser Keyboard Action (Playwright)  | In-Browser Keyboard Action (Playwright)                 | <pre>{<br>&nbsp;"type" : "Wait",<br>&nbsp;&nbsp;"random_min": integer,<br>&nbsp;&nbsp;"random_max": integer,<br>&nbsp;&nbsp;"time": integer<br>}</pre>                                                                                                                                                                                                                                                                                                                                | 
| In-Browser Text Input (Playwright)       | In-Browser Text Input (Playwright)                      | <pre>{<br>&nbsp;"type" : "Wait",<br>&nbsp;&nbsp;"random_min": integer,<br>&nbsp;&nbsp;"random_max": integer,<br>&nbsp;&nbsp;"time": integer<br>}</pre>                                                                                                                                                                                                                                                                                                                                | 
| In-Browser Move (Playwright)             | In-Browser Move                                         | <pre>{<br>&nbsp;"type" : "Wait",<br>&nbsp;&nbsp;"random_min": integer,<br>&nbsp;&nbsp;"random_max": integer,<br>&nbsp;&nbsp;"time": integer<br>}</pre>                                                                                                                                                                                                                                                                                                                                | 
| In-Browser Move (Playwright)             | In-Browser Move/Hover  (Playwright)                     | <pre>{<br>&nbsp;"type" : "Wait",<br>&nbsp;&nbsp;"random_min": integer,<br>&nbsp;&nbsp;"random_max": integer,<br>&nbsp;&nbsp;"time": integer<br>}</pre>                                                                                                                                                                                                                                                                                                                                |
| In-Browser Click (Playwright)            | In-Browser Mouse Click (Playwright)                     | <pre>{<br>&nbsp;"type" : "Create Data",<br>&nbsp;&nbsp;"data_type": "string",<br>&nbsp;&nbsp;"data_name": "string",<br>&nbsp;&nbsp;"key_name": "string",<br>&nbsp;&nbsp;"key_value": any<br>}</pre>                                                                                                                                                                                                                                                                                   |
| In-Browser Scroll (Playwright)           | In-Browser Mouse Click (Playwright)                     | <pre>{<br>&nbsp;"type" : "Fill Data",<br>&nbsp;&nbsp;"from": "string",<br>&nbsp;&nbsp;"to": "string",<br>&nbsp;&nbsp;"result": True/False<br>}</pre>                                                                                                                                                                                                                                                                                                                                  | 
| Selenium Execute Script                  | In-Browser Execute JS Script (Selenium)                 | <pre>{<br>&nbsp;"type" : "Check Condition",<br>&nbsp;&nbsp;"condition": "string",<br>&nbsp;&nbsp;"if_else": "string",<br>&nbsp;&nbsp;"if_end": "string"<br>}</pre>                                                                                                                                                                                                                                                                                                                    | 
| Selenium Wait For Element                | In-Browser Wait For Web Element (Selenium)              | <pre>{<br>&nbsp;"type" : "Repeat",<br>&nbsp;&nbsp;"lc_name": "string",<br>&nbsp;&nbsp;"until": "string",<br>&nbsp;&nbsp;"count": integer,<br>&nbsp;&nbsp;"end": "string"<br>}</pre>                                                                                                                                                                                                                                                                                                   | 
| Selenium Keyboard Action                 | In-Browser Keyboard Action (combo key) (Selenium)       | <pre>{<br>&nbsp;"type" : "Goto",<br>&nbsp;&nbsp;"goto": "string"<br>}</pre>                                                                                                                                                                                                                                                                                                                                                                                                           | 
| Selenium Text Input                      | In-Browser Text Input (Selenium)                        | <pre>{<br>&nbsp;"type" : "Exception Handler",<br>&nbsp;&nbsp;"cause": "string",<br>&nbsp;&nbsp;"cdata": any<br>}</pre>                                                                                                                                                                                                                                                                                                                                                                | 
| Selenium Move                            | In-Browser Mouse Move/Hover (Selenium)                  | <pre>{<br>&nbsp;"type" : "End Exception",<br>&nbsp;&nbsp;"cause": "string",<br>&nbsp;&nbsp;"cdata": any<br>}</pre>                                                                                                                                                                                                                                                                                                                                                                    | 
| Selenium Mouse Click                     | In-Browser Mouse Click (Selenium)                       | <pre>{<br>&nbsp;"type" : "Stub",<br>&nbsp;&nbsp;"stub name": "string",<br>&nbsp;&nbsp;"func name": "string"<br>}</pre>                                                                                                                                                                                                                                                                                                                                                                | 
| Selenium Scroll                          | In-Browser Mouse Scroll up/down (Selenium)              | <pre>{<br>&nbsp;"type" : "Call Function",<br>&nbsp;&nbsp;"fname": "string",<br>&nbsp;&nbsp;"args": "string",<br>&nbsp;&nbsp;"return_to": "string",<br>&nbsp;&nbsp;"output": "string"<br>}</pre>                                                                                                                                                                                                                                                                                       | 
| generic API request                      | HTTP request with specified method, header, and data    | <pre>{<br>&nbsp;"type" : "Call Extern",<br>&nbsp;&nbsp;"file": "string",<br>&nbsp;&nbsp;"args": "string",<br>&nbsp;&nbsp;"entity": "string",<br>&nbsp;&nbsp;"output": "string"<br>}</pre>                                                                                                                                                                                                                                                                                             | 

###### Mouse Click Instruction
- *action* - can be "single click/double click/right click/drag drop"
- *action args* - "" this is related to action parameter, for example one can specify 
- *save_rb* - whether to save this instruction to be a roll-back point. (mostly it should be True)
- *screen* - the variable name that holds the screen extraction results.
- *target_name* - the name of the anchor or info or other element in "screen" variable, the location of this target item will be clicked on. this is specified in the contents related JOBS instructions on the cloud side.
- *target_type* - the type of  the anchor or info or other element in "screen" variable, the location of this target item will be clicked on.this is specified in the contents related JOBS instructions on the cloud side.
- *target_type* - the piece of text in "screen" variable, the location of this text will be clicked on.
- *nth* - the nth occurrence of the target in case multiple targets are on the screen, [x, y] means it's the xth occurrence in horizontal direction (left to right), and yth occurrence in vertial direction (top to bottom).
- *offset from* - could be "left/top/right/bottom/center", meaning that the click location is at an offset location from the target item, for example "left" means click to the left of the left edge of the target item.
- *offset unit* - could be "pixel/box/screen", the offset unit.
- *offset* - could be integer or fractional, this is the offset amount. For example, we could specify to click 120 pixels offset to the right of the right edge of an text anchor named "Search". 
- *move_pause* - pause number of seconds after move the mouse pointer to target
- *post_wait* - wait number of seconds after mouse click action

###### Mouse Scroll Instruction
- *action* - can be "scroll up/scroll down"
- *action args* - "" this is scroll speed
- *screen* - the variable name that holds the screen extraction results.
- *amount* - integer, amount to scroll (equivalent to mouse wheel is minimum step)
- *resolution* - the variable's name that holds the pixel/scroll resolution varaible.
- *random min* - integer, add random amount to the scroll, the random amount's range's lower limit. 
- *random max* - integer, add random amount to the scroll, the random amount's range's upper limit. Setting both min and max to 0 means there is no randomness.
- *unit* - the unit the scroll, could "raw/screen"

###### Keyboard Text Input Instruction
- *action* - can be "scroll up/scroll down"
- *save_rb* - whether to save this instruction to be a roll-back point. (mostly it should be True)
- *text* - the text to type on the keyboard
- *speed* - float, type speed, time between each key stroke
- *key_after* - the non-text key to hit after typing the text, for exammple "enter" means hit the <enter> key after typing.
- *wait_after* - integer, the amount of seconds to wait after the type action. for example, for waiting the web site to load after typing something.

###### Keyboard Key Input Instruction
- *type* - can be "scroll up/scroll down"
- *action* - "" this is scroll speed
- *action* value - the variable name that holds the screen extraction results.
- *save_rb* - whether to save this instruction to be a roll-back point. (mostly it should be True)
- *location* - integer, amount to scroll (equivalent to mouse wheel is minimum step)
- *wait_after* - integer, the amount of seconds to wait after the type action. for example, for waiting the web site to load after typing something.

###### Screen Extraction Instruction
- *root* - can be "scroll up/scroll down"
- *template* - "" this is scroll speed
- *option* - the variable name that holds the screen extraction results.
- *data_sink* - whether to save this instruction to be a roll-back point. (mostly it should be True)
- *page* -  section name of the page (refer to the contents part of the JOBS-DL instruction set)
- *page_data_info* - integer, the amount of seconds to wait after the type action. for example, for waiting the web site to load after typing something.
- *theme* - 
- *section* - section name of the page (refer to the contents part of the JOBS-DL instruction set)


###### Screen Search Instruction
- *screen* - can be "scroll up/scroll down"
- *names* - "" this is scroll speed
- *target_types* - the variable name that holds the screen extraction results.
- *logic* - whether to save this instruction to be a roll-back point. (mostly it should be True)
- *result* - integer, amount to scroll (equivalent to mouse wheel is minimum step)
- *site* - integer, the amount of seconds to wait after the type action. for example, for waiting the web site to load after typing something.
- *status* - integer, the amount of seconds to wait after the type action. for example, for waiting the web site to load after typing something.

###### Time Wait Instruction
- *random_min* - add a random amount of seconds on top of the number of seconds specified in "time" parameter. This sets the lower bound of the random number.
- *random_max* - add a random amount of seconds on top of the number of seconds specified in "time" parameter. This sets the upper bound of the random number.
- *time* - integer number of seconds to wait

###### Variable Creation Instruction
- *data_type* - the type of the variable to be created, could be "int/string/float/obj"
- *data_name* - the name of the variable to be created.
- *key_name* - if data_type is obj, then this holds the name of the key to be created.
- *key_value* - if data_type is obj, then this holds the value of the key to be created.

###### Variable Assign Value Instruction
- *from* - the variable that's the souce of the data value assignment
- *to* - the variable that's the sink of the data value assignment
- *result* - the name of the variable that holds the result of the assignment.


###### Call Function Instruction
- *func_name* - the name of the function to be executed.
- *stub_name* - "function/end function"

###### Call External Instruction
- *file* - the file name or the external python code in string to be executed.
- *args* - "" this is scroll speed
- *entity* - integer, amount to scroll (equivalent to mouse wheel is minimum step)
- *output* - the name of the variable that will hold the output of the external instructions run.


With the above basic instruction set, one can pretty much create a skill for any task flow.