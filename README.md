# ecbot
E-Commerce Bot is an RPA software to free e-business owners from the daily chores of running an e-business.
Even though ECBot is for e-commerce, but it is designed to be extensible be a general purpose RPA software allowing
one to automate any task. The bot software emulates human's view and move work pattern by extracting structured
screen contents and create mouse and keyboard actions according to the screen contents. ecbot is written in 
Python, and works on windows PC (it will be adapated to MAC, and linux later on)

# Features

### Networked Bots

ecbot can run many bots cross many computers on a LAN. There will always be a computer serves as a commander, and other 
computers serve as vehicles that carries a platoon of bots.

![](resource/images/icons/top_cp_model.png)

### Bots, Missions, Skills

with ecbot, one can create, edit and delete any number of:
- a **bot** - a virtual machine can execute a task automation. 
- a **mission** - a task to be completed.
- a **skill** - the instructions to completes the task.

a bot can take on multiple missions, and before executing those missions, 
the bot needs to be empowered with (or given) the associated skills.
Armed with skills, the bots can be scheduled to run the tasks.

ecbots also contains a scheduler that will assign the bots to run based 
the available resources and certain business logics.

![](resource/images/icons/bms_relationship.png)

### JOBS-DL (Json Object Based Skill Description Language)

To support the screen view, mouse and keyboard action, and to be able to describe a work flow to be automated,
we created a macro language for this purpose, called Json Object Based Skill Description Language (JOBS-DL).
For each work flow/task to be automated, it will require a "skill", which is a collection of 
step-by-step instructions to be executed to complete the task. A skill will be written with the 
JOBS-DL language.

JOBS-DL treats RPA bots as a work execution virtual machine, and at the core, it is consisted of a set
of instructions that the virtual machine can execute. The instruction set is divided into two sections,
one set is for the procedural work related, the other set is for describing structured 
contents on a screen image.

##### The Procedures Related JOBS Instruction Set
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

##### The Contents Related JOBS Instruction Set
Here are the contents related instruction sets of the ecbots RPA virtual machine:

| Name                      | Description                        | Syntax                                                                                                                                                                                                                                                                                                                           | Attributes |
|---------------------------|------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------| ------- |
| Page Specification        | Define structureded text on a page | <pre>{<br>&nbsp;"page name" :<br>&nbsp;&nbsp;"section name1": {<br>&nbsp;&nbsp;&nbsp;&nbsp;"anchors": [...],<br>&nbsp;&nbsp;&nbsp;&nbsp;"info": [...]<br>&nbsp;&nbsp;}, ....<br>}</pre>                                                                                                                                          |
| Anchor Specification      | Define anchors on on a page        | <pre>{<br>&nbsp;"anchor name" : "string",<br>&nbsp;"anchor type": "string" <br>&nbsp;"template": "string",<br>&nbsp;"ref_method": "string",<br>&nbsp;"ref_location": {<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "string",<br>&nbsp;&nbsp;&nbsp;&nbsp;"refs": {}<br>&nbsp;&nbsp;}<br>}</pre>                                             |
| Information Specification | Define informations on on a page   | <pre>{<br>&nbsp;"info name" : "string",<br>&nbsp;"info type": "string" <br>&nbsp;"template": "string",<br>&nbsp;"ref_method": "string",<br>&nbsp;"ref_location": {<br>&nbsp;&nbsp;&nbsp;&nbsp;"grouping": "string",<br>&nbsp;&nbsp;&nbsp;&nbsp;"anchors": [],<br>&nbsp;&nbsp;&nbsp;&nbsp;"infos": []<br>&nbsp;&nbsp;}<br>}</pre> |

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
| 4           | info nearest to info.                        |                                                                        |

For type 0 anchors, one can also specify certain constraints, for example, in the ref_location method, one can do something like this:

 <pre>"refs": [{<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "top, left",<br>&nbsp;&nbsp;&nbsp;&nbsp;"ref": "anchor0",<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset": 0;<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset_unit": "box";<br>},<br>{<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "bottom, right",<br>&nbsp;&nbsp;&nbsp;&nbsp;"ref": "anchor1",<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset": 0;<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset_unit": "box";<br>},</br>...]</pre>


For type 1 infos, one can also specify certain constraints, for example, in the ref_location method, one can do something like this:

 <pre>"refs": [{<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "below",<br>&nbsp;&nbsp;&nbsp;&nbsp;"ref": "anchor0",<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset": 0;<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset_unit": "box";<br>},<br>{<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "bottom, right",<br>&nbsp;&nbsp;&nbsp;&nbsp;"ref": "anchor1",<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset": 0;<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset_unit": "box";<br>},</br>...]</pre>


For type 2 infos, one can also specify certain constraints, for example, in the ref_location method, one can do something like this:

 <pre>"refs": [{<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "above, left",<br>&nbsp;&nbsp;&nbsp;&nbsp;"ref": "anchor0",<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset": 0;<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset_unit": "box";<br>},<br>{<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "bottom, right",<br>&nbsp;&nbsp;&nbsp;&nbsp;"ref": "anchor1",<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset": 0;<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset_unit": "box";<br>},</br>...]</pre>

For type 3, 4 infos, the specification is similar to type 1 & 2, except the anchor names are info names instead.

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
