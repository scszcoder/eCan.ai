<p align="center">
  <img src="gui_v2/src/assets/logoDark1.png" alt="" style="width:128px;"/>
</p>

# eCanOCR (eCan Opitcal Character Recognition)
eCanOCR is an API service that can convert image to text. eCanOCR is built on top of open source OCR engine Tesseract 
as well as a modified version of state of art OCR engine PaddleOCR. It combines Tesseract's agility with Paddle's accuracy,
and automatically restructure raw outputs into hierarchical segmented paragraphs and lines and words (much better than 
Tesseract's lousy paragraph segmentation and line segmentation). eCanOCR can also do CV icon recognition provided setup correctly.


# Features

### Networked Agents





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

