<p align="center">
  <img src="gui_v2/src/assets/logoDark1.png" alt="" style="width:128px;"/>
</p>

# eCan.ai (E-Commerce Agent Network)
eCan.ai is an agent app for e-commerce, aimed at empowering sellers to run their multi-channel e-commerce with minimal human overheads.
This will be achieved by allowing sellers to run every aspects of their e-commerce business with ai agents, from sourcing to selling, 
from marketing research to advertising, from legal counsel to customer service. eCan agents can do it all, the goal is to enable single 
person billion dollar business, run by agents, so the person can be on the beach :)

# Features

### Networked Agents

With eCan.ai, you can run many agents with cross many computers on a LAN or WAN or a combo of both. There will be at least 1 host computer that serves as a commander, and other 
computers serve as vehicles that carries a platoon of agents, a computer or a mobile device such as a smart phone or tablet can also serve as a staff officer, a staff officer 
computer can monitor and command the agents remotely thru the internet.

![](resource/images/icons/org0.png)

### Multi-Agent, Multi-Task

eCan.ai has built-in agents for several e-commerce tasks, but you can easily create your own agents, create tasks for them
and launch those task on any available vehicle (host computer). Each task will run in its own thread.

### A2A Protocol For Inter-Agent Communication

eCan.ai adopts de-facto standard-in-making A2A protocol for messaging between agents. We also supports websocket based real time
chat between human and agents and between human and agents.


![](resource/images/icons/bms_relationship.png)

### [Langgraph](https://github.com/langchain-ai/langgraph) based Agent Skills

eCan.ai builds on top of Langgraph (from Langchain), the state of art agent development framework. Any agent task will require
at least one skill, which is work-flow described by langgraph.


##### Graphic [Flowgram](https://github.com/bytedance/flowgram.ai) based Langgraph IDE
The .PSK file is a file contains description of the prccess to be automated.
It is a JSON Object Based Skill (JOBS) description language, with an abstract instruction set.
each instruction is written as a json object.

###### Streamable HTTP MCP Tools Integration
Here are the procedures related instruction sets of the ecbots RPA virtual machine:


| Name                              | Description                                             | Syntax                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
|-----------------------------------|---------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Mouse <br>Click                   | Execute a mouse click action                            | <pre>{<br>&nbsp;"type" : "Mouse Click",<br>&nbsp;&nbsp;"action": "string",<br>&nbsp;&nbsp;"action args": "string",<br>&nbsp;&nbsp;"save_rb": True/False,<br>&nbsp;&nbsp;"screen": "string",<br>&nbsp;&nbsp;"target_name": "string",<br>&nbsp;&nbsp;"target_type": "string",<br>&nbsp;&nbsp;"text": "string",<br>&nbsp;&nbsp;"nth": [x-int, y-int],<br>&nbsp;&nbsp;"offset from": "string",<br>&nbsp;&nbsp;"offset unit": "string",<br>&nbsp;&nbsp;"offset": [x-int, y-int]<br>}</pre> | 
| Mouse <br>Scroll                  | Execute a mouse scroll action                           | <pre>{<br>&nbsp;"type" : "Mouse Scroll",<br>&nbsp;&nbsp;"action": "string",<br>&nbsp;&nbsp;"screen": "string",<br>&nbsp;&nbsp;"amount": integer,<br>&nbsp;&nbsp;"resolution": "string",<br>&nbsp;&nbsp;"random_min": integer,<br>&nbsp;&nbsp;"random_max": integer,<br>&nbsp;&nbsp;"unit": "string"<br>}</pre>                                                                                                                                                                        | 
| Keyboard <br>Text <br>Typing      | Execute a keyboard text input action                    | <pre>{<br>&nbsp;"type" : "Text Input",<br>&nbsp;&nbsp;"action": "string",<br>&nbsp;&nbsp;"save_rb": True/False,<br>&nbsp;&nbsp;"text": "string",<br>&nbsp;&nbsp;"speed": float,<br>&nbsp;&nbsp;"key_after": "string",<br>&nbsp;&nbsp;"wait_after": "string"<br>}</pre>                                                                                                                                                                                                                | 
| Keyboard <br>Key <br>Press        | Execute a keyboard key stroke action                    | <pre>{<br>&nbsp;"type" : "Key Input",<br>&nbsp;&nbsp;"action": "string",<br>&nbsp;&nbsp;"action value": "string",<br>&nbsp;&nbsp;"save_rb": True/False,<br>&nbsp;&nbsp;"location": "string",<br>&nbsp;&nbsp;"wait_after": "string"<br>}</pre>                                                                                                                                                                                                                                         | 
| Screen <br>Content <br>Extraction | Extract text and image info from a screen capture image | <pre>{<br>&nbsp;"type" : "Extract Info",<br>&nbsp;&nbsp;"root": obj,<br>&nbsp;&nbsp;"template": "string",<br>&nbsp;&nbsp;"option": "string",<br>&nbsp;&nbsp;"option": "string",<br>&nbsp;&nbsp;"data_sink": "string",<br>&nbsp;&nbsp;"page": "string",<br>&nbsp;&nbsp;"page_data_info": "string",<br>&nbsp;&nbsp;"theme": "string",<br>&nbsp;&nbsp;"section": "string"<br>}</pre>                                                                                                     | 
| Screen <br>Content <br>Search     | Search the result of a screen image extraction          | <pre>{<br>&nbsp;"type" : "Search",<br>&nbsp;&nbsp;"screen": "string",<br>&nbsp;&nbsp;"names": ["string"...],<br>&nbsp;&nbsp;"target_types": ["string"...],<br>&nbsp;&nbsp;"logic": "string",<br>&nbsp;&nbsp;"result": "string",<br>&nbsp;&nbsp;"site": "string",<br>&nbsp;&nbsp;"status": "string"<br>}</pre> |
| Time <br>Wait                     | wait N seconds                                          | <pre>{<br>&nbsp;"type" : "Wait",<br>&nbsp;&nbsp;"random_min": integer,<br>&nbsp;&nbsp;"random_max": integer,<br>&nbsp;&nbsp;"time": integer<br>}</pre>                                                                                                                                                                                                                                                                                                                                | 
| Variable <br>Creation             | create a variable                                       | <pre>{<br>&nbsp;"type" : "Create Data",<br>&nbsp;&nbsp;"data_type": "string",<br>&nbsp;&nbsp;"data_name": "string",<br>&nbsp;&nbsp;"key_name": "string",<br>&nbsp;&nbsp;"key_value": any<br>}</pre>                                                                                                                                                                                                                                                                                   |
| Variable <br>Assign <br>Value     | assign value to a variable                              | <pre>{<br>&nbsp;"type" : "Fill Data",<br>&nbsp;&nbsp;"from": "string",<br>&nbsp;&nbsp;"to": "string",<br>&nbsp;&nbsp;"result": True/False<br>}</pre>                                                                                                                                                                                                                                                                                                                                  | 
| Conditional <br>Execution         | Execute instructions based on a condition               | <pre>{<br>&nbsp;"type" : "Check Condition",<br>&nbsp;&nbsp;"condition": "string",<br>&nbsp;&nbsp;"if_else": "string",<br>&nbsp;&nbsp;"if_end": "string"<br>}</pre>                                                                                                                                                                                                                                                                                                                    | 
| Loop/<br>Repeated <br>Execution   | Repeatedly execute some instructions                    | <pre>{<br>&nbsp;"type" : "Repeat",<br>&nbsp;&nbsp;"lc_name": "string",<br>&nbsp;&nbsp;"until": "string",<br>&nbsp;&nbsp;"count": integer,<br>&nbsp;&nbsp;"end": "string"<br>}</pre>                                                                                                                                                                                                                                                                                                   | 
| Go to/<br>Jump                    | Directly Jump to an instruction's location              | <pre>{<br>&nbsp;"type" : "Goto",<br>&nbsp;&nbsp;"goto": "string"<br>}</pre>                                                                                                                                                                                                                                                                                                                                                                                                           | 
| Exception <br>Handle              | Handle an Exception case                                | <pre>{<br>&nbsp;"type" : "Exception Handler",<br>&nbsp;&nbsp;"cause": "string",<br>&nbsp;&nbsp;"cdata": any<br>}</pre>                                                                                                                                                                                                                                                                                                                                                                | 
| End <br>Exception                 | End of handling an Exception case                       | <pre>{<br>&nbsp;"type" : "End Exception",<br>&nbsp;&nbsp;"cause": "string",<br>&nbsp;&nbsp;"cdata": any<br>}</pre>                                                                                                                                                                                                                                                                                                                                                                    | 
| Stub                              | Stub Instructions                                       | <pre>{<br>&nbsp;"type" : "Stub",<br>&nbsp;&nbsp;"stub name": "string",<br>&nbsp;&nbsp;"func name": "string"<br>}</pre>                                                                                                                                                                                                                                                                                                                                                                | 
| Call <br>Function                 | Call a Function                                         | <pre>{<br>&nbsp;"type" : "Call Function",<br>&nbsp;&nbsp;"fname": "string",<br>&nbsp;&nbsp;"args": "string",<br>&nbsp;&nbsp;"return_to": "string",<br>&nbsp;&nbsp;"output": "string"<br>}</pre>                                                                                                                                                                                                                                                                                       | 
| Call <br>Extern                   | Call an extern python routine.                          | <pre>{<br>&nbsp;"type" : "Call Extern",<br>&nbsp;&nbsp;"file": "string",<br>&nbsp;&nbsp;"args": "string",<br>&nbsp;&nbsp;"entity": "string",<br>&nbsp;&nbsp;"output": "string"<br>}</pre>                                                                                                                                                                                                                                                                                             | 

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

###### Conditional Execution Instruction
- *condition* - the condition to be checked
- *if_else* - the address of the instruction to be executed if condition returns False
- *if_end* - the address of the instruction at the end of the conditional execution.

###### Loop Execution Instruction
- *lc_name* - the name of the loop counter
- *until* - the loop end condition
- *count* - the number of times to iterate the loop. (if this parameter is specified, then the until parameter will be ignored.)
- *end* - the address of end of the loop

###### Go To Execution Instruction
- *goto* - the instruction address to jump to

###### Exception Handling Instruction
- *cause* - cause of the exception
- *cdata* - data related to the cause

###### End Exception Instruction
- *cause* - cause of the exception
- *cdata* - data related to the cause

###### Stub Instruction
- *func_name* - the name of the function to be executed.
- *stub_name* - "function/end function/else/end loop/end condition"

###### Call Function Instruction
- *func_name* - the name of the function to be executed.
- *stub_name* - "function/end function"

###### Call External Instruction
- *file* - the file name or the external python code in string to be executed.
- *args* - "" this is scroll speed
- *entity* - integer, amount to scroll (equivalent to mouse wheel is minimum step)
- *output* - the name of the variable that will hold the output of the external instructions run.


With the above basic instruction set, one can pretty much create a skill for any task flow.

##### Runnable Skill File (.rsk file)
this is a file to be run by the RPA virtual machine. 
it contains reformated address including namespace.
and as well as the entire code, also skill settings is
put in place and ready to be used at run time.
(skill settings is a set of parameters used by various
instructions. some at compile time, some at run time.)

##### The Contents Skill File (.csk file)
This file resides on both cloud side and local side and is used to describe useful contents expected to be seen a page.
This file is in JSON format.
Here are the contents related instruction sets of the ecbots RPA virtual machine:

| Name                      | Description                        | Syntax                                                                                                                                                                                                                                                                                                                           | Attributes |
|---------------------------|------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------| ------- |
| Page Specification        | Define structureded text on a page | <pre>{<br>&nbsp;"page name" :<br>&nbsp;&nbsp;"section name1": {<br>&nbsp;&nbsp;&nbsp;&nbsp;"anchors": [...],<br>&nbsp;&nbsp;&nbsp;&nbsp;"info": [...]<br>&nbsp;&nbsp;}, ....<br>}</pre>                                                                                                                                          |
| Anchor Specification      | Define anchors on on a page        | <pre>{<br>&nbsp;"anchor name" : "string",<br>&nbsp;"anchor type": "string" <br>&nbsp;"template": "string",<br>&nbsp;"ref_method": "string",<br>&nbsp;"ref_location": {<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "string",<br>&nbsp;&nbsp;&nbsp;&nbsp;"refs": {}<br>&nbsp;&nbsp;}<br>}</pre>                                             |
| Information Specification | Define informations on on a page   | <pre>{<br>&nbsp;"info name" : "string",<br>&nbsp;"info type": "table 5x6" <br>&nbsp;"template": "string",<br>&nbsp;"ref_method": "string",<br>&nbsp;"refs": [{<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "string",<br>&nbsp;&nbsp;&nbsp;&nbsp;"ref": "",<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset": ""<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset_unit": ""<br>&nbsp;&nbsp;}]<br>}</pre>  |

With the above basic instruction set, one can pretty much define any structured screen content.
The contents related instruction sets resides on the cloud side to facilitate screen extraction. 

A page could be a web page, or any document page and a page could have different sections and when extract 
information on the screen, different sections might have different structured text information that we're 
interested in. 

On any screen, we define a set of "anchors" on the screen, these are the texts or icons, or a combination of 
texts and icons to form the distinct features of the interested contents. Anchors will help us keep track the 
locations on the page while we scroll up and down the page.

Anchor types:

| Types       | Description      | Syntax                                                                 | Attributes                                                                                                                 |
|-------------|------------------|------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------|
| "text"      | a piece of text  | template is the text itself  | <br> * anchor text could be regular expression <br> * anchor can have location restraints which is defined  in ref section |
| "icon"      | an icon image    | template is the file name of the image of the icon. |
| "icon group" | a group of icons |                                                                        | nearest could be specified in both x and y direction, targeted info could be a regular expression definition               |

Anchor Reference Methods:

| Ref Method | Description                                       | Syntax                                                                 | Attributes                                                                                                                 |
|------------|---------------------------------------------------|------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------|
| 0          | a dinstinct piece of text or icon on a page       | template is the text itself or the file name of the image of the icon. | <br> * anchor text could be regular expression <br> * anchor can have location restraints which is defined  in ref section |
| 1          | a polygan shape                                   |                                                                        |
| 2          | a line                                            |                                                                        | nearest could be specified in both x and y direction, targeted info could be a regular expression definition               |
| 3          | anchor group, a group of icons (example, 5 stars) |                                                                        | nearest could be specified in both x and y direction, targeted info could be a regular expression definition               |

For type 0 anchors, one can also specify certain constraints, for example, in the ref_location method, one can do something like this:

 <pre>"ref_constraints": [{<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "<",<br>&nbsp;&nbsp;&nbsp;&nbsp;"ref": "bottom",<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset": 90;<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset_unit": "%";<br>},...]</pre>

For type 3 anchors, one can also specify certain constraints, for example, in the ref_location method, one can do something like this:

 <pre>"ref_constraints": [{<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "<",<br>&nbsp;&nbsp;&nbsp;&nbsp;"ref": "star",<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset": 1;<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset_unit": "box";<br>},...]</pre>

![](resource/images/icons/anchor_def.png)

Info section:

Info json elements defines a piece of screen area that contains interested/structred information, 
the area is referred by previously defined anchors one way or another.


![](resource/images/icons/info0.png)


there are multiple ways of referring to anchors and define the area that contains the useful text:

Info types:

| Types           | Description             | Syntax                                                                                | Attributes                                                                                                                 |
|-----------------|-------------------------|---------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------|
| "lines, 5"      | at most N lines of text | template could be the regular expression pattern that the lines of text must contain. | <br> * anchor text could be regular expression |
| "bound box"     | an virtual bound box    |                                   |
| "words, 5"      | at most N words         |                                                                                       | nearest could be specified in both x and y direction, targeted info could be a regular expression definition               |
| "paragraphs, 5" | at most N paragraphs    |                                                                                       | nearest could be specified in both x and y direction, targeted info could be a regular expression definition               |


Info Reference Methods:

| Ref Methods | Description                                  | Syntax                                                                 | Attributes                                                                                                                                                                                                            |
|-------------|----------------------------------------------|------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 0           | bound box bounded by at least 2 anchors      |                                                                        | the anchors should define the upper left corner and lower right cornerof the bounded area. (Note, the bound could be special keywords, "top", "left" "right" "bottom" which represent the boundry of the screen image |
| 1           | a piece of text adjacent to certain anchors. | for example: at most 7 lines below an anchor.                          |
| 2           | a piece of text nearest to certain anchor    | for example: a line contains "$" on +y direction nearest to an anchor. |
| 3           | info adjacent to info.                       |                                                                        |
| 4           | info nearest to info. (not yet implemented)  |                                                                        |
| 5           | calendar  (not yet implemented)              | need to provide template text for shorhand for Sunday to Monday        |
| 6           | table                                        | need to provide template text for all col titles and/or row titles     |

For type 0 anchors, one can also specify certain constraints, for example, in the ref_location method, one can do something like this:

 <pre>"refs": [{<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "top, left",<br>&nbsp;&nbsp;&nbsp;&nbsp;"ref": "anchor0",<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset": 0;<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset_unit": "box";<br>},<br>{<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "bottom, right",<br>&nbsp;&nbsp;&nbsp;&nbsp;"ref": "anchor1",<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset": 0;<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset_unit": "box";<br>},</br>...]</pre>


For type 1 infos, one can also certain lines of text with certain regular expression pattern in certain locational relation to a reference anchor, for example, in the ref_location method, one can do something like this:

 <pre>{<br>&nbsp;"info_name": "available_fund",<br>&nbsp;"info_type"  : "lines 1",<br>&nbsp;"template"     : "\\$ *[0-9]+",<br>&nbsp;"ref_method"   : "1",<br>&nbsp;"refs": [{<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "below",<br>&nbsp;&nbsp;&nbsp;&nbsp;"ref": "anchor0",<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset": 1;<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset_unit": "box";<br>&nbsp;}]<br>}</pre>

Info_type here specify the information type, "lines 1" means 1 line of text.
in this ref_method 1 example, template specifys a money amount format regular expression, which will appear "below" the reference anchor "anchor0", within 1 bound box (height) offset. 

For type 2 infos, one can also specify up to N lines of texts within certain pararaph that's relative to certain anchor, i.e. , for example, in the ref_location method, one can do something like this:

 <pre>{<br>&nbsp;"info_name": "address",<br>&nbsp;"info_type"  : "lines 3",<br>&nbsp;"template"     : "",<br>&nbsp;"ref_method"   : "2",<br>&nbsp;"refs": [{<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "below",<br>&nbsp;&nbsp;&nbsp;&nbsp;"ref": "Address",<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset": 3;<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset_unit": "box";<br>&nbsp}]<br>}</pre>
Info_type here specify the information type, "lines 3" means no more than 3 line of text. 
Note: right now only "below" direction is implemented.

For type 3, 4 infos, the specification is similar to type 1 & 2, except the anchor names are info names instead.

for type 5 infos.
<pre>{<br>&nbsp;"info name" : "string",<br>&nbsp;"info type": "calendar" <br>&nbsp;"template": "",<br>&nbsp;"ref_method": "5",<br>&nbsp;"refs": [{<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "string",<br>&nbsp;&nbsp;&nbsp;&nbsp;"ref": "comma seperated sunday to monday shorthand",<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset": ""<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset_unit": ""<br>&nbsp;&nbsp;}]<br>}</pre> 


for type 6 infos.

<pre>{<br>&nbsp;"info name" : "string",<br>&nbsp;"info type": "table 5x6" <br>&nbsp;"template": "",<br>&nbsp;"ref_method": "6",<br>&nbsp;"refs": [{<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "string",<br>&nbsp;&nbsp;&nbsp;&nbsp;"ref": "comma seperated col titles string",<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset": ""<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset_unit": ""<br>&nbsp;&nbsp;}]<br>}</pre> 


### Exception Handling
An exception happens whenever there is an instance where a web page doesn't load correctly. This could be
caused by several reason:
- internet service provider outage
- modem/router/switch outage
- web server down
- etc.

in such a case, the workflow will be interrupted, and the bot can can deal with this by wait for network
to recover and once its recovered, the work will resume from the most recent roll-back point. As the JOBS instructions
gets executed, the most recent mouse click or keyboard action instruction is automatically memorized as a 
potential roll-back point, in the event of an exception and recover, we can then resume
from this roll-back point. 
In case of a persistent outage, if a designated timeout is reached, the bot will claim failure on executing
the current RPA mission.

### Seller's Product Inventory
For sellers, one could create an inventory json file so that it can be loaded and then when seller needs to calculate 
shipping label costs, for example:
- one can search the ordered products, and retrieve product weight and dimension will be needed to calculate the the shipping label cost.

the inventory file is located in the installation user data directory ($ECBOT_DATA_HOME) +"/resource/inventory.json", a
sample inventory file is included in the software distribution.


### Mission Skill match
Each mission has a "skills" attributes, it's a string in the format of comma separated skill IDs, for example "1,5,6 ..."
means this mission requires skill # 1, 5, 6 and so on. It's very important to make sure the main skill is the FIRST one 
in the list. (for example for skills "72,18,33", skill#72 has to be the main skill which will in turn uses skill#18 and
skill #33)

### Using Fingerprint Browers
Many sellers use finger print browsers, ECBot supports ADS Power out of box, and will have support for other browsers 
such as purple bird(ziniao) or multi-login down the road. 
For ADS Power, ECBot has skills to auto batch generate, batch save and batch load profiles.
Here some default settings and assumptions:
- under $ECBOT_DATA_HOME direction, there will be an "ads_profiles" directory, under this dir, there will be an
 "ads_settings.json" this json file should have the following form: {"user name": "", "user pwd": "", "batch_size": 2} 
 where user name and password are the ADS Power's account user name and password so that ECBOT can auto log into ADS 
 if logged out. The "batch_size" parameter specifieds the number of ADS profiles ADS Power can load at a time, for
 for the free version of the ADS power, 2 profiles can be loaded at a time.
- When ECBot runs on top of ADS Power, the assumption is that proper ADS power profiles have already been setup and 
  stored under the $ECBOT_DATA_HOME\ads_profiles directory, each profile is stored in a .txt file with file name 
  following this convetion: user name before the "@" sign in the ecommerce site account email address, for example 
  if a bot's email address is "john.smith@abc.com", then this user's ADS profile name should be "john.smith.txt". 
  Built-in ADS skill will collect the necessary number of these txt profiles and convert them into .xlsx format and
  the resulting xlsx will be batch importable to ADS Power. 

### Steps to Create a custom Skill on GUI


### Steps to Create a custom Skill with Code
- create a directory $ECBOT_DATA_HOME/my_skills/%platform_%app_%site_%page/ where %page, %app, %site, %page are the shorthand name of the platform, app, site, page of your skill.
  - for example: win_chrome_ebay_home will be a settings directory your skill will be applied to: windows, chrome browser, ebay site, seller homepage.
- under this directory, create a %skill_name.json file and a %skill_name diretory and inside the directory there will be two sub-directories: "images" and "scripts"
    - for example: if your skill about fullfill orders, you can name your skill directory "fullfill_orders", and also the corresponding skill defining json file.
- an example .json file can be seen here: html link here...
- an example generator script is shown here: html link here....
- note in .json file, the "privacy" is set to "private", the "owner" is set to user name, the generator script must starts with "genMy", for example, if your script is to generate a chatbot skill, your generator function should be "genMyChatbot.py"
- note in genMy*.py generator script, your generator function's input arguments must be in a standard form, i.e. (worksettings, stepN, theme, pubSkills), where pubSkills is table of public skill instruction generator functions, you may use pubSkills[public generator function name] to call readily available 
- the "images" directory contains all the icons you expect this skill to be able to recognize on a screen captured image.
- the "scripts" directory contains the .csk file which defines all the anchors and info elements associated on the skill
- This "images" and "scrpts" directories will then be uploaded to the cloud side, using the "CSK Upload" button under the skill editor menu.

### Steps to Create a custom instruction 
- for many scenarios, using ARAIS instrucitons maybe cumbersome to implement, if you know python, it would be much easier to just use python code to create a new instruction and call it in your skill code.
- to augment the existing ARAIS with your own instruction, follow these steps:
  - create "/my_rais_extensions/my_rais_extensions.json" in $ECBOT_DATA_HOME directory
  - when code the instruction generator function, make sure the instrution definition json's "type" starts with "My:", and the instruction execution function name starts with "processMy", and the generator function name starts with "genStepMy". The instruction execution function should take a standard three input arguments: [step, si, pubSkills] where pubSkills holds the context of the main ecbot app.

### Interfacing with Bots over the internet
You will need to install myECB App on Android devices or iOS devices, once logged in, you will be able to view, control or chat with any bot in the field.
Here is the message format in a chat window.
- for regular chat, simply key in the message.
- for sending a command, start the line with ":" character then followed by xml tags.
    - here is a list of commands you can send to a troop.
    - 
| Tag                       | Text             | Description                                                                | Note |
|---------------------------|------------------|----------------------------------------------------------------------------|------|
| `<cmd>``</cmd>`           | "list"           | list bots/missions/skills/vehicles                                         |      |
|                           | "halt"           | halt missions                                                              |      |
|                           | "cancel"         | cancel missions                                                            |      |
|                           | "resume"         | resume missions                                                            |      |
|                           | "skip"           | skip missions                                                              |      |
|                           | "show"           | logs                                                                       |      |
|                           | "hide"           | logs                                                                       |      |
| `<bots>``</bots>`         | "1,2,3"          | this is bot related info                                                   |      |
| `<missions>``</missions>` | "full path here" | this is mission related info                                               
| `<vehicles>``</vehicles>` | "1,2,3"          | this is vehicle related info                                               |      |
| `<skills>``</skills>`     | "full path here" | this is skill related info                                                 
| `<data>``</data>`         | "1,2,3"          | this is data for the commands, for example comma separated bot/mission ids |      |
| `<file>``</file>`         | "full path here" | specify file name                                                          |      |


Example: 
here is the string for show/hide logs： ":<cmd>show<logs>all</logs></cmd>" or ":<cmd>hide<logs>all</logs></cmd>"

# Chat Service

一个基于 SQLAlchemy 的聊天服务实现，支持用户管理、会话管理、消息处理等功能。

## 功能特性

- 用户管理（创建、查询、更新、删除）
- 会话管理（创建、查询、成员管理）
- 消息处理（发送、编辑、删除、状态管理）
- 附件支持
- 消息状态追踪
- 会话管理
- 线程安全
- 可配置的数据库路径

## 安装

```bash
pip install -r requirements.txt
```

## 使用方法

### 基本使用

```python
from agent.chats.chat_service import ChatService

# 使用默认数据库路径
chat_service = ChatService.initialize()

# 使用自定义数据库路径
chat_service = ChatService.initialize('custom/path/to/database.db')
```

### 用户管理

```python
# 创建用户
user = chat_service.create_user(
    username="john_doe",
    display_name="John Doe",
    avatar_url="https://example.com/avatar.jpg"
)

# 获取用户
user = chat_service.get_user(user_id)
user = chat_service.get_user_by_username("john_doe")

# 更新用户
updated_user = chat_service.update_user(
    user_id,
    display_name="John Updated",
    avatar_url="https://example.com/new_avatar.jpg"
)

# 删除用户
success = chat_service.delete_user(user_id)
```

### 会话管理

```python
# 创建会话
conversation = chat_service.create_conversation(
    name="Group Chat",
    is_group=True,
    description="Team discussion"
)

# 获取会话
conversation = chat_service.get_conversation(conversation_id)

# 获取用户的所有会话
conversations = chat_service.get_user_conversations(user_id)

# 添加用户到会话
member = chat_service.add_user_to_conversation(
    conversation_id=conversation_id,
    user_id=user_id,
    role="member"
)

# 从会话中移除用户
success = chat_service.remove_user_from_conversation(
    conversation_id,
    user_id
)
```

### 消息处理

```python
# 发送消息
message = chat_service.send_message(
    conversation_id=conversation_id,
    sender_id=user_id,
    content="Hello, world!",
    message_type=MessageType.TEXT
)

# 获取会话消息
messages = chat_service.get_conversation_messages(
    conversation_id,
    limit=50,
    offset=0
)

# 编辑消息
updated_message = chat_service.edit_message(
    message_id,
    content="Updated message"
)

# 删除消息
success = chat_service.delete_message(message_id)
```

## 数据库配置

聊天服务支持多种数据库配置方式：

1. 使用默认数据库路径：
```python
chat_service = ChatService.initialize()
```

2. 使用自定义数据库路径：
```python
chat_service = ChatService.initialize('custom/path/to/database.db')
```

3. 使用环境变量：
```bash
export DATABASE_URL='sqlite:///custom/path/to/database.db'
chat_service = ChatService.initialize()
```

4. 使用现有的数据库引擎：
```python
from sqlalchemy import create_engine
engine = create_engine('sqlite:///database.db')
chat_service = ChatService(engine=engine)
```

5. 使用现有的数据库会话：
```python
from sqlalchemy.orm import Session
session = Session()
chat_service = ChatService(session=session)
```

## 测试

运行测试：
```bash
pytest tests/
```

## 注意事项

1. 数据库文件路径必须是有效的文件系统路径
2. 确保应用程序对数据库文件所在目录有读写权限
3. 在多进程环境中，建议使用不同的数据库文件路径
4. 数据库文件会自动创建，但目录必须存在

## 贡献

欢迎提交 Issue 和 Pull Request。

## 许可证

MIT License

## 数据库版本管理

本项目内置了数据库版本管理表 `db_version`，用于记录和管理数据库结构的版本信息，方便后续升级和迁移。

- 每次初始化数据库时会自动插入初始版本（1.0.0）。
- 可通过接口读取当前版本或升级版本。

### 示例代码

```python
from agent.chats.chats_db import DBVersion, get_engine
from sqlalchemy.orm import sessionmaker

engine = get_engine('your_db_path.db')
Session = sessionmaker(bind=engine)
session = Session()

# 获取当前数据库版本
current_version = DBVersion.get_current_version(session)
print(current_version.version)

# 升级数据库版本
DBVersion.upgrade_version(session, '2.0.0', description='升级到2.0.0')

# 再次获取
new_version = DBVersion.get_current_version(session)
print(new_version.version)

session.close()
```

## 数据库迁移管理

本项目提供了数据库迁移管理功能，支持数据库结构的版本控制和升级。

### 基本用法

```python
from agent.chats.db_migration import DBMigration

# 创建迁移管理器实例
migration = DBMigration('your_database.db')

# 获取当前版本
current_version = migration.get_current_version()
print(f"当前数据库版本: {current_version}")

# 升级到新版本
success = migration.upgrade_to_version(
    "2.0.0",
    description="升级到2.0.0版本，添加新功能表"
)
if success:
    print("数据库升级成功")
else:
    print("数据库升级失败")

# 创建新的迁移脚本模板
template = migration.create_migration_script(
    "2.1.0",
    "添加新字段"
)
print(template)
```

### 版本升级流程

1. 获取当前数据库版本
2. 确定目标版本
3. 执行升级操作
4. 验证升级结果

### 创建新的升级脚本

当需要修改数据库结构时，可以按照以下步骤创建升级脚本：

1. 使用 `create_migration_script` 生成脚本模板
2. 在模板中实现具体的升级逻辑
3. 将脚本添加到版本管理系统中
4. 执行升级操作

### 注意事项

1. 升级前请务必备份数据库
2. 确保升级脚本的正确性和可回滚性
3. 在测试环境中验证升级脚本
4. 记录所有数据库结构变更

## 🔨 Building ECBot

ECBot supports multiple build modes for different use cases:

### Quick Build (Recommended for Development)
```bash
python build.py fast                    # Fast build with caching and parallel compilation
python build.py fast --force           # Force rebuild (ignore cache)
python build.py fast --skip-frontend   # Skip frontend build
python build.py fast --skip-installer  # Generate executable only
```

### Other Build Modes
```bash
python build.py dev                     # Development build (with console)
python build.py prod                    # Production build (fully optimized)
```

### Build Features
- **Parallel Compilation**: Uses multiple CPU cores for faster builds (all modes)
- **Parallel Installer Creation**: Multi-threaded compression for Windows installers
- **Smart Caching**: Incremental builds that only recompile changed files (fast mode only)
- **Auto Data Collection**: Automatically collects data files, binaries, and submodules from key packages
- **Cross-platform**: Works on Windows, macOS, and Linux
- **Optimized Packaging**: Excludes unnecessary dependencies to reduce size

### Build Mode Differences
- **fast**: Enables caching and parallel compilation for fastest builds (~2-5 min)
  - Uses ZIP compression for installer (fastest)
  - Minimal data collection for essential packages only
  - Optimized for development speed
- **dev**: Parallel compilation with console output for debugging (~5-10 min)
  - Uses ZIP compression for installer
  - Full data collection for comprehensive testing
  - Includes debug symbols and console output
- **prod**: Parallel compilation with full optimization and clean builds (~15-25 min)
  - Uses LZMA compression with solid compression (smallest size)
  - Complete data collection for all packages
  - Maximum compression for distribution

### Build Time Optimization
Choose the right mode for your needs:
- **Development**: Use `fast` mode for quick iterations (`python build.py fast`)
- **Testing**: Use `dev` mode for comprehensive testing (`python build.py dev`)
- **Distribution**: Use `prod` mode for final releases (`python build.py prod`)

If build time is critical:
- Skip installer creation: `python build.py [mode] --skip-installer`
- Use fast mode for development: `python build.py fast`

**Expected installer creation times:**
- fast/dev modes: 3-5 minutes (ZIP compression)
- prod mode: 15-25 minutes (LZMA compression with solid compression)

### Build Output
- Executable files are generated in the `dist/` directory
- Installation packages (if enabled) are created as `ECBot-Setup.exe` (Windows) or equivalent for other platforms