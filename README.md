# ecbot
E-Commerce Bot is an RPA software to free e-business owners from the daily chores of running an e-business.
Even though ECBot is for e-commerce, but it is designed to be extensible be a general purpose RPA software allowing
one to automate any task. The bot software emulates human's view and move work pattern by extracting structured
screen contents and create mouse and keyboard actions according to the screen contents. ecbot is written in 
Python, and works on windows PC (it will be adapated to MAC, and linux later on)


# JOBS-DL (Json Object Based Skill Description Language)

To support the screen view, mouse and keyboard action, and to be able to describe a work flow to be automated,
we created a macro language for this purpose, called Json Object Based Skill Description Language (JOBS-DL).
For each work flow/task to be automated, it will require a "skill", which is a collection of 
step-by-step instructions to be executed to complete the task. A skill will be written with the 
JOBS-DL language.

JOBS-DL treats RPA bots as a work execution virtual machine, and at the core, it is consisted of a set
of instructions that the virtual machine can execute. The instruction set is divided into two sections,
one set is for the procedural work related, the other set is for describing structured 
contents on a screen image.

## The Procedures Related JOBS Instruction Set
Here are the procedures related instruction sets of the ecbots RPA virtual machine:

| Name                      | Description                                             | Syntax | Attributes |
|---------------------------|---------------------------------------------------------| ------- | ------- |
| Mouse Click               | Execute a mouse click action                            |
| Mouse Scroll              | Execute a mouse scroll action                           |
| Keyboard Text Typing      | Execute a keyboard text input action                    |
| Keyboard Key Press        | Execute a keyboard key stroke action                    |
| Screen Content Extraction | Extract text and image info from a screen capture image |
| Screen Content Search     | Search the result of a screen image extraction          |
| Time Wait                 | wait N seconds                                          |
| Variable Creation         | create a variable                                       |
| Variable Assign Value     | assign value to a variable                              |
| Conditional Execution     | Execute instructions based on a condition               |
| Loop/Repeated Execution   | Repeatedly execute some instructions                    |
| Go to/Jump                | Directly Jump to an instruction's location              |
| Exception Handle          | Handle an Exception case                                |
| End Exception             | End of handling an Exception case                       |
| Stub                      | Stub Instructions                                       |
| Call Function             | Call a Function                                         |
| Call Extern               | Call an extern python routine.                          |

With the above basic instruction set, one can pretty much create a skill for any task flow.

## The Contents Related JOBS Instruction Set
Here are the procedures related instruction sets of the ecbots RPA virtual machine:

| Name                      | Description                        | Syntax                                                                                                                                                                                                                                                                                                                           | Attributes |
|---------------------------|------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------| ------- |
| Page Specification        | Define structureded text on a page | <pre>{<br>&nbsp;"page name" :<br>&nbsp;&nbsp;"section name1": {<br>&nbsp;&nbsp;&nbsp;&nbsp;"anchors": [...],<br>&nbsp;&nbsp;&nbsp;&nbsp;"info": [...]<br>&nbsp;&nbsp;}, ....<br>}</pre>                                                                                                                                          |
| Anchor Specification      | Define anchors on on a page        | <pre>{<br>&nbsp;"anchor name" : "string",<br>&nbsp;"anchor type": "string" <br>&nbsp;"template": "string",<br>&nbsp;"ref_method": "string",<br>&nbsp;"ref_location": {<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "string",<br>&nbsp;&nbsp;&nbsp;&nbsp;"refs": {}<br>&nbsp;&nbsp;}<br>}</pre>                                             |
| Information Specification | Define informations on on a page   | <pre>{<br>&nbsp;"info name" : "string",<br>&nbsp;"info type": "string" <br>&nbsp;"template": "string",<br>&nbsp;"ref_method": "string",<br>&nbsp;"ref_location": {<br>&nbsp;&nbsp;&nbsp;&nbsp;"grouping": "string",<br>&nbsp;&nbsp;&nbsp;&nbsp;"anchors": [],<br>&nbsp;&nbsp;&nbsp;&nbsp;"infos": []<br>&nbsp;&nbsp;}<br>}</pre> |

With the above basic instruction set, one can pretty much define any structured screen content.
