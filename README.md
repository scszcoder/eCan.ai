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

| Name                              | Description                                             | Syntax                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
|-----------------------------------|---------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Mouse <br>Click                   | Execute a mouse click action                            | <pre>{<br>&nbsp;"type" : "string",<br>&nbsp;&nbsp;"action": "string",<br>&nbsp;&nbsp;"action args": "string",<br>&nbsp;&nbsp;"save_rb": True/False,<br>&nbsp;&nbsp;"screen": "string",<br>&nbsp;&nbsp;"target_name": "string",<br>&nbsp;&nbsp;"target_type": "string",<br>&nbsp;&nbsp;"text": "string",<br>&nbsp;&nbsp;"nth": [x-int, y-int],<br>&nbsp;&nbsp;"offset from": "string",<br>&nbsp;&nbsp;"offset unit": "string",<br>&nbsp;&nbsp;"offset": [x-int, y-int]<br>}</pre>       | 
| Mouse <br>Scroll                  | Execute a mouse scroll action                           | <pre>{<br>&nbsp;"type" : "string",<br>&nbsp;&nbsp;"action": "string",<br>&nbsp;&nbsp;"action args": "string",<br>&nbsp;&nbsp;"save_rb": True/False,<br>&nbsp;&nbsp;"screen": "string",<br>&nbsp;&nbsp;"target_name": "string",<br>&nbsp;&nbsp;"target_type": "string",<br>&nbsp;&nbsp;"text": "string",<br>&nbsp;&nbsp;"nth": [x-int, y-int],<br>&nbsp;&nbsp;"offset from": "string",<br>&nbsp;&nbsp;"offset unit": "string",<br>&nbsp;&nbsp;"offset": [x-int, y-int]<br>}</pre>       | 
| Keyboard <br>Text <br>Typing      | Execute a keyboard text input action                    | <pre>{<br>&nbsp;"type" : "string",<br>&nbsp;&nbsp;"action": "string",<br>&nbsp;&nbsp;"action args": "string",<br>&nbsp;&nbsp;"save_rb": True/False,<br>&nbsp;&nbsp;"screen": "string",<br>&nbsp;&nbsp;"target_name": "string",<br>&nbsp;&nbsp;"target_type": "string",<br>&nbsp;&nbsp;"text": "string",<br>&nbsp;&nbsp;"nth": [x-int, y-int],<br>&nbsp;&nbsp;"offset from": "string",<br>&nbsp;&nbsp;"offset unit": "string",<br>&nbsp;&nbsp;"offset": [x-int, y-int]<br>}</pre>       | 
| Keyboard <br>Key <br>Press        | Execute a keyboard key stroke action                    | <pre>{<br>&nbsp;"type" : "string",<br>&nbsp;&nbsp;"action": "string",<br>&nbsp;&nbsp;"action args": "string",<br>&nbsp;&nbsp;"save_rb": True/False,<br>&nbsp;&nbsp;"screen": "string",<br>&nbsp;&nbsp;"target_name": "string",<br>&nbsp;&nbsp;"target_type": "string",<br>&nbsp;&nbsp;"text": "string",<br>&nbsp;&nbsp;"nth": [x-int, y-int],<br>&nbsp;&nbsp;"offset from": "string",<br>&nbsp;&nbsp;"offset unit": "string",<br>&nbsp;&nbsp;"offset": [x-int, y-int]<br>}</pre>       | 
| Screen <br>Content <br>Extraction | Extract text and image info from a screen capture image | <pre>{<br>&nbsp;"type" : "Extract Info",<br>&nbsp;&nbsp;"root": obj,<br>&nbsp;&nbsp;"template": "string",<br>&nbsp;&nbsp;"option": "string",<br>&nbsp;&nbsp;"option": "string",<br>&nbsp;&nbsp;"data_sink": "string",<br>&nbsp;&nbsp;"page": "string",<br>&nbsp;&nbsp;"page_data_info": "string",<br>&nbsp;&nbsp;"theme": "string",<br>&nbsp;&nbsp;"section": "string"<br>}</pre>                                                                                                      | 
| Screen <br>Content <br>Search     | Search the result of a screen image extraction          | <pre>{<br>&nbsp;"type" : "Search",<br>&nbsp;&nbsp;"screen": "string",<br>&nbsp;&nbsp;"names": ["string"...],<br>&nbsp;&nbsp;"target_types": ["string"...],<br>&nbsp;&nbsp;"logic": "string",<br>&nbsp;&nbsp;"target_name": "string",<br>&nbsp;&nbsp;"target_type": "string",<br>&nbsp;&nbsp;"text": "string",<br>&nbsp;&nbsp;"nth": [x-int, y-int],<br>&nbsp;&nbsp;"offset from": "string",<br>&nbsp;&nbsp;"offset unit": "string",<br>&nbsp;&nbsp;"offset": [x-int, y-int]<br>}</pre> | 
| Time <br>Wait                     | wait N seconds                                          | <pre>{<br>&nbsp;"type" : "Wait",<br>&nbsp;&nbsp;"random_min": integer,<br>&nbsp;&nbsp;"random_max": integer,<br>&nbsp;&nbsp;"time": integer<br>}</pre>                                                                                                                                                                                                                                                                                                                                 | 
| Variable <br>Creation             | create a variable                                       | <pre>{<br>&nbsp;"type" : "Create Data",<br>&nbsp;&nbsp;"data_type": "string",<br>&nbsp;&nbsp;"data_name": "string",<br>&nbsp;&nbsp;"key_name": "string",<br>&nbsp;&nbsp;"key_value": any<br>}</pre>                                                                                                                                                                                                                                                                                    |
| Variable <br>Assign <br>Value     | assign value to a variable                              | <pre>{<br>&nbsp;"type" : "Fill Data",<br>&nbsp;&nbsp;"from": "string",<br>&nbsp;&nbsp;"to": "string",<br>&nbsp;&nbsp;"result": True/False<br>}</pre>                                                                                                                                                                                                                                                                                                                                   | 
| Conditional <br>Execution         | Execute instructions based on a condition               | <pre>{<br>&nbsp;"type" : "Check Condition",<br>&nbsp;&nbsp;"condition": "string",<br>&nbsp;&nbsp;"if_else": "string",<br>&nbsp;&nbsp;"if_end": "string"<br>}</pre>                                                                                                                                                                                                                                                                                                                     | 
| Loop/<br>Repeated <br>Execution   | Repeatedly execute some instructions                    | <pre>{<br>&nbsp;"type" : "Repeat",<br>&nbsp;&nbsp;"lc_name": "string",<br>&nbsp;&nbsp;"until": "string",<br>&nbsp;&nbsp;"count": integer,<br>&nbsp;&nbsp;"end": "string"<br>}</pre>                                                                                                                                                                                                                                                                                                    | 
| Go to/<br>Jump                    | Directly Jump to an instruction's location              | <pre>{<br>&nbsp;"type" : "Goto",<br>&nbsp;&nbsp;"goto": "string"<br>}</pre>                                                                                                                                                                                                                                                                                                                                                                                                            | 
| Exception <br>Handle              | Handle an Exception case                                | <pre>{<br>&nbsp;"type" : "Exception Handler",<br>&nbsp;&nbsp;"cause": "string",<br>&nbsp;&nbsp;"cdata": any<br>}</pre>                                                                                                                                                                                                                                                                                                                                                                 | 
| End <br>Exception                 | End of handling an Exception case                       | <pre>{<br>&nbsp;"type" : "End Exception",<br>&nbsp;&nbsp;"cause": "string",<br>&nbsp;&nbsp;"cdata": any<br>}</pre>                                                                                                                                                                                                                                                                                                                                                                     | 
| Stub                              | Stub Instructions                                       | <pre>{<br>&nbsp;"type" : "Stub",<br>&nbsp;&nbsp;"stub name": "string",<br>&nbsp;&nbsp;"func name": "string"<br>}</pre>                                                                                                                                                                                                                                                                                                                                                                 | 
| Call <br>Function                 | Call a Function                                         | <pre>{<br>&nbsp;"type" : "Call Function",<br>&nbsp;&nbsp;"fname": "string",<br>&nbsp;&nbsp;"args": "string",<br>&nbsp;&nbsp;"return_to": "string",<br>&nbsp;&nbsp;"output": "string"<br>}</pre>                                                                                                                                                                                                                                                                                        | 
| Call <br>Extern                   | Call an extern python routine.                          | <pre>{<br>&nbsp;"type" : "Call Extern",<br>&nbsp;&nbsp;"file": "string",<br>&nbsp;&nbsp;"args": "string",<br>&nbsp;&nbsp;"entity": "string",<br>&nbsp;&nbsp;"output": "string"<br>}</pre>                                                                                                                                                                                                                                                                                              | 

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