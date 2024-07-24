# ECBOT

电子商务机器人（E-Commerce Bot），一款旨在将电子商务业主从日常运营的繁琐事务中解脱出来的 RPA 软件。尽管其专为电子商务设计，然而，ECBot 实际是一款具备扩展性的通用 RPA 软件，允许用户实现任何任务的自动化。该机器人软件通过提取结构化的屏幕内容，并依据屏幕内容创建鼠标和键盘操作，以此模拟人类的查看和移动工作模式。ecbot 由 Python 编写，适用于 Windows PC（后续将适配 MAC 和 Linux）。

# 功能

### 联网机器人

ecbot 能够在局域网上的多台计算机上运行多个机器人。始终会有一台计算机充当指挥官，其他计算机则作为承载一组机器人的载体。

![](resource/images/icons/top_cp_model.png)

### 机器人、任务、技能

使用 ecbot，用户能够创建、编辑和删除任意数量的：
- 一个**机器人**——能够执行任务自动化的虚拟机。
- 一个**任务**——需要完成的事务。
- 一个**技能**——完成任务的指令。

一个机器人能够承担多项任务，并且在执行这些任务之前，机器人需要具备（或被赋予）相关的技能。在配备了技能之后，机器人可以被安排运行任务。

ecbots 还涵盖一个调度程序，它会依据可用资源和特定业务逻辑来分配机器人以运行任务。

![](resource/images/icons/bms_relationship.png)

### JOBS-DL（基于 Json 对象的技能描述语言）

为了支持屏幕视图、鼠标和键盘操作，并能够描述要自动化的工作流程，我们为此创建了一种宏语言，称为基于 Json 对象的技能描述语言（JOBS-DL）。对于每个要自动化的工作流程/任务，都需要一个“技能”，这是一组逐步执行以完成任务的指令。一个技能将使用 JOBS-DL 语言编写。

JOBS-DL 将 RPA 机器人视为工作执行虚拟机，其核心由一组虚拟机能够执行的指令组成。指令集分为两个部分，一部分与程序工作相关，另一部分用于描述屏幕图像上的结构化内容。

与 JOBS-DL 相关的关键文件是.psk、.rsk 和.csk 文件。它们的描述如下。

##### 程序技能文件（.psk）

.PSK 文件是一个包含要自动化的流程描述的文件。它是一种基于 Json 对象的技能（JOBS）描述语言，具有抽象的指令集。每个指令都编写为一个 json 对象。

###### 与程序相关的 JOBS 指令集

以下是 ecbots RPA 虚拟机的与程序相关的指令集：

| 名称                              | 描述                                             | 语法                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
|-----------------------------------|---------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 鼠标点击                         | 执行鼠标点击操作                            | <pre>{<br>&nbsp;"type" : "Mouse Click",<br>&nbsp;&nbsp;"action": "string",<br>&nbsp;&nbsp;"action args": "string",<br>&nbsp;&nbsp;"save_rb": True/False,<br>&nbsp;&nbsp;"screen": "string",<br>&nbsp;&nbsp;"target_name": "string",<br>&nbsp;&nbsp;"target_type": "string",<br>&nbsp;&nbsp;"text": "string",<br>&nbsp;&nbsp;"nth": [x-int, y-int],<br>&nbsp;&nbsp;"offset from": "string",<br>&nbsp;&nbsp;"offset unit": "string",<br>&nbsp;&nbsp;"offset": [x-int, y-int]<br>}</pre> | 
| 鼠标滚动                         | 执行鼠标滚动操作                           | <pre>{<br>&nbsp;"type" : "Mouse Scroll",<br>&nbsp;&nbsp;"action": "string",<br>&nbsp;&nbsp;"screen": "string",<br>&nbsp;&nbsp;"amount": integer,<br>&nbsp;&nbsp;"resolution": "string",<br>&nbsp;&nbsp;"random_min": integer,<br>&nbsp;&nbsp;"random_max": integer,<br>&nbsp;&nbsp;"unit": "string"<br>}</pre>                                                                                                                                                                        | 
| 键盘文本输入                     | 执行键盘文本输入操作                    | <pre>{<br>&nbsp;"type" : "Text Input",<br>&nbsp;&nbsp;"action": "string",<br>&nbsp;&nbsp;"save_rb": True/False,<br>&nbsp;&nbsp;"text": "string",<br>&nbsp;&nbsp;"speed": float,<br>&nbsp;&nbsp;"key_after": "string",<br>&nbsp;&nbsp;"wait_after": "string"<br>}</pre>                                                                                                                                                                                                                | 
| 键盘按键按下                     | 执行键盘按键操作                    | <pre>{<br>&nbsp;"type" : "Key Input",<br>&nbsp;&nbsp;"action": "string",<br>&nbsp;&nbsp;"action value": "string",<br>&nbsp;&nbsp;"save_rb": True/False,<br>&nbsp;&nbsp;"location": "string",<br>&nbsp;&nbsp;"wait_after": "string"<br>}</pre>                                                                                                                                                                                                                                         | 
| 屏幕内容提取                     | 从屏幕捕获图像中提取文本和图像信息 | <pre>{<br>&nbsp;"type" : "Extract Info",<br>&nbsp;&nbsp;"root": obj,<br>&nbsp;&nbsp;"template": "string",<br>&nbsp;&nbsp;"option": "string",<br>&nbsp;&nbsp;"option": "string",<br>&nbsp;&nbsp;"data_sink": "string",<br>&nbsp;&nbsp;"page": "string",<br>&nbsp;&nbsp;"page_data_info": "string",<br>&nbsp;&nbsp;"theme": "string",<br>&nbsp;&nbsp;"section": "string"<br>}</pre>                                                                                                     | 
| 屏幕内容搜索                     | 搜索屏幕图像提取的结果          | <pre>{<br>&nbsp;"type" : "Search",<br>&nbsp;&nbsp;"screen": "string",<br>&nbsp;&nbsp;"names": ["string"...],<br>&nbsp;&nbsp;"target_types": ["string"...],<br>&nbsp;&nbsp;"logic": "string",<br>&nbsp;&nbsp;"result": "string",<br>&nbsp;&nbsp;"site": "string",<br>&nbsp;&nbsp;"status": "string"<br>}</pre> |
| 时间等待                         | 等待 N 秒                                          | <pre>{<br>&nbsp;"type" : "Wait",<br>&nbsp;&nbsp;"random_min": integer,<br>&nbsp;&nbsp;"random_max": integer,<br>&nbsp;&nbsp;"time": integer<br>}</pre>                                                                                                                                                                                                                                                                                                                                | 
| 变量创建                         | 创建一个变量                                       | <pre>{<br>&nbsp;"type" : "Create Data",<br>&nbsp;&nbsp;"data_type": "string",<br>&nbsp;&nbsp;"data_name": "string",<br>&nbsp;&nbsp;"key_name": "string",<br>&nbsp;&nbsp;"key_value": any<br>}</pre>                                                                                                                                                                                                                                                                                   |
| 变量赋值                         | 给变量赋值                              | <pre>{<br>&nbsp;"type" : "Fill Data",<br>&nbsp;&nbsp;"from": "string",<br>&nbsp;&nbsp;"to": "string",<br>&nbsp;&nbsp;"result": True/False<br>}</pre>                                                                                                                                                                                                                                                                                                                                  | 
| 条件执行                         | 根据条件执行指令               | <pre>{<br>&nbsp;"type" : "Check Condition",<br>&nbsp;&nbsp;"condition": "string",<br>&nbsp;&nbsp;"if_else": "string",<br>&nbsp;&nbsp;"if_end": "string"<br>}</pre>                                                                                                                                                                                                                                                                                                                    | 
| 循环/重复执行                     | 重复执行某些指令                    | <pre>{<br>&nbsp;"type" : "Repeat",<br>&nbsp;&nbsp;"lc_name": "string",<br>&nbsp;&nbsp;"until": "string",<br>&nbsp;&nbsp;"count": integer,<br>&nbsp;&nbsp;"end": "string"<br>}</pre>                                                                                                                                                                                                                                                                                                   | 
| 跳转/跳转到                      | 直接跳转到指令的位置              | <pre>{<br>&nbsp;"type" : "Goto",<br>&nbsp;&nbsp;"goto": "string"<br>}</pre>                                                                                                                                                                                                                                                                                                                                                                                                           | 
| 异常处理                         | 处理异常情况                                | <pre>{<br>&nbsp;"type" : "Exception Handler",<br>&nbsp;&nbsp;"cause": "string",<br>&nbsp;&nbsp;"cdata": any<br>}</pre>                                                                                                                                                                                                                                                                                                                                                                | 
| 结束异常处理                     | 结束异常处理情况                       | <pre>{<br>&nbsp;"type" : "End Exception",<br>&nbsp;&nbsp;"cause": "string",<br>&nbsp;&nbsp;"cdata": any<br>}</pre>                                                                                                                                                                                                                                                                                                                                                                    | 
| 存根                             | 存根指令                                       | <pre>{<br>&nbsp;"type" : "Stub",<br>&nbsp;&nbsp;"stub name": "string",<br>&nbsp;&nbsp;"func name": "string"<br>}</pre>                                                                                                                                                                                                                                                                                                                                                                | 
| 调用函数                         | 调用函数                                         | <pre>{<br>&nbsp;"type" : "Call Function",<br>&nbsp;&nbsp;"fname": "string",<br>&nbsp;&nbsp;"args": "string",<br>&nbsp;&nbsp;"return_to": "string",<br>&nbsp;&nbsp;"output": "string"<br>}</pre>                                                                                                                                                                                                                                                                                       | 
| 调用外部程序                     | 调用外部 Python 例程。                          | <pre>{<br>&nbsp;"type" : "Call Extern",<br>&nbsp;&nbsp;"file": "string",<br>&nbsp;&nbsp;"args": "string",<br>&nbsp;&nbsp;"entity": "string",<br>&nbsp;&nbsp;"output": "string"<br>}</pre>                                                                                                                                                                                                                                                                                             | 

###### 鼠标点击指令

- *action*：可以是“单击/双击/右键单击/拖放”。
- *action args*：与操作参数相关，例如可以指定 。
- *save_rb*：是否将此指令保存为回滚点。（大多数情况下应为 True）。
- *screen*：保存屏幕提取结果的变量名。
- *target_name*：“screen”变量中锚点或信息或其他元素的名称，将点击此目标项的位置。这在云端的内容相关 JOBS 指令中指定。
- *target_type*：“screen”变量中锚点或信息或其他元素的类型，将点击此目标项的位置。这在云端的内容相关 JOBS 指令中指定。
- *target_type*：“screen”变量中的一段文本，将点击此文本的位置。
- *nth*：如果屏幕上有多个目标，则为第 n 个出现，[x, y] 表示在水平方向（从左到右）为第 x 个出现，在垂直方向（从上到下）为第 y 个出现。
- *offset from*：可以是“左/上/右/下/中心”，意味着点击位置在目标项的偏移位置，例如“左”表示点击目标项左边缘的左侧。
- *offset unit*：可以是“像素/框/屏幕”，偏移单位。
- *offset*：可以是整数或分数，这是偏移量。例如，我们可以指定点击名为“搜索”的文本锚点右边缘右侧 120 像素的位置。
- *move_pause*：将鼠标指针移动到目标后暂停的秒数。
- *post_wait*：鼠标点击操作后等待的秒数。

###### 鼠标滚动指令

- *action*：可以是“向上滚动/向下滚动”。
- *action args*：这是滚动速度。
- *screen*：保存屏幕提取结果的变量名。
- *amount*：整数，滚动量（相当于鼠标滚轮的最小步长）。
- *resolution*：保存像素/滚动分辨率变量的变量名。
- *random min*：整数，向滚动量添加随机量，随机量范围的下限。 
- *random max*：整数，向滚动量添加随机量，随机量范围的上限。将 min 和 max 都设置为 0 表示没有随机性。
- *unit*：滚动的单位，可以是“原始/屏幕”。

###### 键盘文本输入指令

- *action*：可以是“向上滚动/向下滚动”。
- *save_rb*：是否将此指令保存为回滚点。（大多数情况下应为 True）。
- *text*：要在键盘上输入的文本。
- *speed*：浮点数，输入速度，每个按键之间的时间间隔。
- *key_after*：输入文本后要按下的非文本键，例如“enter”表示输入后按下<Enter>键。
- *wait_after*：整数，输入操作后的等待秒数。例如，等待输入某些内容后网站加载。

###### 键盘按键输入指令

- *type*：可以是“向上滚动/向下滚动”。
- *action*：这是滚动速度。
- *action* 值：保存屏幕提取结果的变量名。
- *save_rb*：是否将此指令保存为回滚点。（大多数情况下应为 True）。
- *location*：整数，滚动量（相当于鼠标滚轮的最小步长）。
- *wait_after*：整数，输入操作后的等待秒数。例如，等待输入某些内容后网站加载。

###### 屏幕提取指令

- *root*：可以是“向上滚动/向下滚动”。
- *template*：这是滚动速度。
- *option*：保存屏幕提取结果的变量名。
- *data_sink*：是否将此指令保存为回滚点。（大多数情况下应为 True）。
- *page*：页面的节名称（参考 JOBS-DL 指令集的内容部分）。
- *page_data_info*：整数，输入操作后的等待秒数。例如，等待输入某些内容后网站加载。
- *theme*： 。
- *section*：页面的节名称（参考 JOBS-DL 指令集的内容部分）。

###### 屏幕搜索指令

- *screen*：可以是“向上滚动/向下滚动”。
- *names*：这是滚动速度。
- *target_types*：保存屏幕提取结果的变量名。
- *logic*：是否将此指令保存为回滚点。（大多数情况下应为 True）。
- *result*：整数，滚动量（相当于鼠标滚轮的最小步长）。
- *site*：整数，输入操作后的等待秒数。例如，等待输入某些内容后网站加载。
- *status*：整数，输入操作后的等待秒数。例如，等待输入某些内容后网站加载。

###### 时间等待指令

- *random_min*：在“time”参数指定的秒数上添加随机秒数。这设置随机数的下限。
- *random_max*：在“time”参数指定的秒数上添加随机秒数。这设置随机数的上限。
- *time*：等待的整数秒数。

###### 变量创建指令

- *data_type*：要创建的变量的类型，可以是“int/string/float/obj”。
- *data_name*：要创建的变量的名称。
- *key_name*：如果 data_type 是 obj，则这保存要创建的键的名称。
- *key_value*：如果 data_type 是 obj，则这保存要创建的键的值。

###### 变量赋值指令

- *from*：作为数据值赋值源的变量。
- *to*：作为数据值赋值目标的变量。
- *result*：保存赋值结果的变量的名称。

###### 条件执行指令

- *condition*：要检查的条件。
- *if_else*：如果条件返回 False 要执行的指令的地址。
- *if_end*：条件执行结束时的指令地址。

###### 循环执行指令

- *lc_name*：循环计数器的名称。
- *until*：循环结束条件。
- *count*：循环迭代的次数。（如果指定了此参数，则 until 参数将被忽略。）
- *end*：循环结束的地址。

###### 跳转执行指令

- *goto*：要跳转到的指令地址。

###### 异常处理指令

- *cause*：异常的原因。
- *cdata*：与原因相关的数据。

###### 结束异常处理指令

- *cause*：异常的原因。
- *cdata*：与原因相关的数据。

###### 存根指令

- *func_name*：要执行的函数的名称。
- *stub_name*：“函数/结束函数/否则/结束循环/结束条件”。

###### 调用函数指令

- *func_name*：要执行的函数的名称。
- *stub_name*：“函数/结束函数”。

###### 调用外部指令

- *file*：要执行的外部 Python 代码的文件名或字符串。
- *args*：这是滚动速度。
- *entity*：整数，滚动量（相当于鼠标滚轮的最小步长）。
- *output*：将保存外部指令运行输出的变量的名称。

有了上述基本指令集，用户几乎可以为任何任务流创建一个技能。

##### 可运行技能文件（.rsk 文件）

这是一个由 RPA 虚拟机运行的文件。它包含重新格式化的地址，包括命名空间。以及整个代码，同时技能设置也已就位并准备在运行时使用。（技能设置是一组在编译时或运行时由各种指令使用的参数。）
 ##### 内容技能文件（.csk 文件）

此文件同时存在于云端和本地端，主要用于描述页面上预期可见的有用内容。该文件采用 JSON 格式。

以下是关于 ecbots RPA 虚拟机与内容相关的指令集：

| 名称 | 描述 | 语法 | 属性 |
|--|--|--|--|
| 页面规范 | 对页面上的结构化文本进行定义 | <pre>{<br>&nbsp;"page name" :<br>&nbsp;&nbsp;"section name1": {<br>&nbsp;&nbsp;&nbsp;&nbsp;"anchors": [...],<br>&nbsp;&nbsp;&nbsp;&nbsp;"info": [...]<br>&nbsp;&nbsp;},....<br>}</pre> |  |
| 锚点规范 | 定义页面上的锚点 | <pre>{<br>&nbsp;"anchor name" : "string",<br>&nbsp;"anchor type": "string" <br>&nbsp;"template": "string",<br>&nbsp;"ref_method": "string",<br>&nbsp;"ref_location": {<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "string",<br>&nbsp;&nbsp;&nbsp;&nbsp;"refs": {}<br>&nbsp;&nbsp;}<br>}</pre> |  |
| 信息规范 | 定义页面上的信息 | <pre>{<br>&nbsp;"info name" : "string",<br>&nbsp;"info type": "table 5x6" <br>&nbsp;"template": "string",<br>&nbsp;"ref_method": "string",<br>&nbsp;"refs": [{<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "string",<br>&nbsp;&nbsp;&nbsp;&nbsp;"ref": "",<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset": ""<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset_unit": ""<br>&nbsp;&nbsp;}]<br>}</pre> |  |

拥有上述基本指令集，用户几乎能够定义任何结构化的屏幕内容。与内容相关的指令集存于云端，以利于屏幕提取。

页面既可以是网页，也可以是任何文档页面，并且页面可能存在不同部分，当在屏幕上提取信息时，不同部分可能具有我们感兴趣的不同结构化文本信息。

在任何屏幕上，我们都能在屏幕上定义一组“锚点”，其可以是文本、图标，或者是文本与图标的组合，从而形成感兴趣内容的独特特征。当我们在页面上上下滚动时，锚点能够帮助我们追踪页面上的位置。

锚点类型：

| 类型 | 描述 | 语法 | 属性 |
|--|--|--|--|
| “文本” | 一段文本 | 模板即文本本身 | <br> * 锚点文本可以是正则表达式 <br> * 锚点可以具有在引用部分中定义的位置限制 |
| “图标” | 一个图标图像 | 模板是图标的图像文件名。 |  |
| “图标组” | 一组图标 |  | 在 x 和 y 方向上都可以指定最近距离，目标信息可以是正则表达式定义 |

锚点引用方法：

| 引用方法 | 描述 | 语法 | 属性 |
|--|--|--|--|
| 0 | 页面上的一段独特文本或图标 | 模板是文本本身或图标的文件名。 | <br> * 锚点文本可以是正则表达式 <br> * 锚点可以具有在引用部分中定义的位置限制 |
| 1 | 一个多边形形状 |  |  |
| 2 | 一条线 |  | 在 x 和 y 方向上都可以指定最近距离，目标信息可以是正则表达式定义 |
| 3 | 锚点组，一组图标（例如，5 颗星） |  | 在 x 和 y 方向上都可以指定最近距离，目标信息可以是正则表达式定义 |

对于 0 型锚点，还能够指定某些约束，比如在 ref_location 方法中，可以如此操作：

 <pre>"ref_constraints": [{<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "<",<br>&nbsp;&nbsp;&nbsp;&nbsp;"ref": "bottom",<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset": 90;<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset_unit": "%";<br>},...]</pre>

对于 3 型锚点，同样可以指定某些约束，例如在 ref_location 方法中，可以这样：

 <pre>"ref_constraints": [{<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "<",<br>&nbsp;&nbsp;&nbsp;&nbsp;"ref": "star",<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset": 1;<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset_unit": "box";<br>},...]</pre>

![](resource/images/icons/anchor_def.png)

信息部分：

信息的 JSON 元素定义了包含感兴趣/结构化信息的屏幕区域，该区域通过先前定义的锚点以某种方式引用。

![](resource/images/icons/info0.png)

存在多种引用锚点并定义包含有用文本区域的方法：

信息类型：

| 类型 | 描述 | 语法 | 属性 |
|--|--|--|--|
| "lines, 5" | 最多 N 行文本 | 模板可以是文本行必须包含的正则表达式模式。 | <br> * 锚点文本可以是正则表达式 |
| "bound box" | 一个虚拟边界框 |  |  |
| "words, 5" | 最多 N 个词 |  | 在 x 和 y 方向上都可以指定最近距离，目标信息可以是正则表达式定义 |
| "paragraphs, 5" | 最多 N 个段落 |  | 在 x 和 y 方向上都可以指定最近距离，目标信息可以是正则表达式定义 |

信息引用方法：

| 引用方法 | 描述 | 语法 | 属性 |
|--|--|--|--|
| 0 | 至少由 2 个锚点界定的边界框 |  | 锚点应定义边界区域的左上角和右下角。（注意，边界可以是特殊关键字，“顶部”、“左侧”、“右侧”、“底部”，它们代表屏幕图像的边界） |
| 1 | 与某些锚点相邻的一段文本。 | 例如：在某个锚点下方最多 7 行。 |  |
| 2 | 与某些锚点最近的一段文本 | 例如：在+y 方向上与某个锚点最近且包含“$”的一行。 |  |
| 3 | 与信息相邻的信息。 |  |  |
| 4 | 与信息最近的信息。 |  |  |
| 5 | 日历 | 需要为周日至周一的缩写提供模板文本 |  |
| 6 | 表格 | 需要为所有列标题和/或行标题提供模板文本 |  |

对于 0 型锚点，还能如此指定某些约束，例如在 ref_location 方法中：

 <pre>"refs": [{<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "top, left",<br>&nbsp;&nbsp;&nbsp;&nbsp;"ref": "anchor0",<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset": 0;<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset_unit": "box";<br>},<br>{<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "bottom, right",<br>&nbsp;&nbsp;&nbsp;&nbsp;"ref": "anchor1",<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset": 0;<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset_unit": "box";<br>},</br>...]</pre>

对于 1 型信息，还能在与参考锚点的特定位置关系中指定具有某些正则表达式模式的某些文本行，例如在 ref_location 方法中，可以这样做：

 <pre>{<br>&nbsp;"info_name": "available_fund",<br>&nbsp;"info_type"  : "lines 1",<br>&nbsp;"template"     : "\\$ *[0-9]+",<br>&nbsp;"ref_method"   : "1",<br>&nbsp;"refs": [{<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "below",<br>&nbsp;&nbsp;&nbsp;&nbsp;"ref": "anchor0",<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset": 1;<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset_unit": "box";<br>&nbsp;}]<br>}</pre>

在此 ref_method 1 示例中，模板指定了一种金额格式的正则表达式，它将出现在参考锚点“anchor0”的“下方”，在 1 个边界框（高度）偏移内。 

对于 2 型信息，还能在与某些锚点相关的特定段落中指定最多 N 行文本，例如在 ref_location 方法中，可以这样做：

 <pre>{<br>&nbsp;"info_name": "address",<br>&nbsp;"info_type"  : "lines 3",<br>&nbsp;"template"     : "",<br>&nbsp;"ref_method"   : "2",<br>&nbsp;"refs": [{<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "below",<br>&nbsp;&nbsp;&nbsp;&nbsp;"ref": "Address",<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset": 3;<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset_unit": "box";<br>&nbsp}]<br>}</pre>

在此，“lines 3”表示不超过 3 行文本。

请注意：目前仅实现了“下方”方向。

对于 3 型和 4 型信息，规范与 1 型和 2 型类似，只是锚点名称改为信息名称。

对于 5 型信息。

<pre>{<br>&nbsp;"info name" : "string",<br>&nbsp;"info type": "calendar" <br>&nbsp;"template": "",<br>&nbsp;"ref_method": "5",<br>&nbsp;"refs": [{<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "string",<br>&nbsp;&nbsp;&nbsp;&nbsp;"ref": "逗号分隔的周日至周一缩写",<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset": ""<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset_unit": ""<br>&nbsp;&nbsp;}]<br>}</pre> 

对于 6 型信息。

<pre>{<br>&nbsp;"info name" : "string",<br>&nbsp;"info type": "table 5x6" <br>&nbsp;"template": "",<br>&nbsp;"ref_method": "6",<br>&nbsp;"refs": [{<br>&nbsp;&nbsp;&nbsp;&nbsp;"dir": "string",<br>&nbsp;&nbsp;&nbsp;&nbsp;"ref": "逗号分隔的列标题字符串",<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset": ""<br>&nbsp;&nbsp;&nbsp;&nbsp;"offset_unit": ""<br>&nbsp;&nbsp;}]<br>}</pre> 

### 异常处理

每当网页加载不正确时，就会出现异常情况。这可能由以下几种原因导致：

- 互联网服务提供商中断
- 调制解调器/路由器/交换机中断
- 网络服务器宕机
- 等等

在这种情形下，工作流程将会中断，机器人能够通过等待网络恢复来处理该状况，一旦网络恢复，工作将从最近的回滚点继续。随着 JOBS 指令的执行，最近的鼠标点击或键盘操作指令会自动被记为潜在的回滚点，在发生异常并恢复的情况下，我们能够从这个回滚点接着进行。

如果持续中断，并达到指定的超时时间，机器人将判定当前 RPA 任务执行失败。

### 卖家的产品库存

对于卖家而言，可以创建一个库存 JSON 文件以便加载，然后当卖家需要计算运输标签成本时，例如：

- 能够搜索已订购的产品，并检索计算运输标签成本所需的产品重量和尺寸。

库存文件位于安装用户数据目录（$ECBOT_DATA_HOME）+“/resource/inventory.json”，软件分发中包含一个示例库存文件。

### 任务技能匹配

每个任务都拥有一个“技能”属性，它是一个以逗号分隔的技能 ID 字符串，例如“1,5,6...”，这表示此任务需要技能 #1、5、6 等等。确保主技能处于列表中的首位非常重要。（例如对于技能“72,18,33”，技能#72 必须是主技能，它将依次使用技能#18 和技能 #33）

### 使用指纹浏览器

许多卖家会使用指纹浏览器，ECBot 开箱即支持 ADS Power，未来还将支持其他浏览器，如紫鸟（ziniao）或多登录。

对于 ADS Power，ECBot 具备自动批量生成、批量保存和批量加载配置文件的技能。

以下是一些默认设置和假设：

- 在 $ECBOT_DATA_HOME 目录下，会有一个“ads_profiles”目录，在此目录下，会有一个“ads_settings.json”这个 JSON 文件应具有以下形式：{"用户名": "", "用户密码": "", "批量大小": 2} 。其中用户名和密码是 ADS Power 的账户用户名和密码，以便 ECBOT 在登出时自动登录 ADS。“批量大小”参数指定 ADS Power 一次能够加载的 ADS 配置文件数量，对于 ADS Power 的免费版本，一次可以加载 2 个配置文件。

- 当 ECBot 在 ADS Power 之上运行时，假设已经在 $ECBOT_DATA_HOME\ads_profiles 目录下设置并存储了合适的 ADS Power 配置文件，每个配置文件都存储在一个.txt 文件中，文件名遵循此约定：电子商务站点账户电子邮件地址中“@”符号前的用户名，例如，如果机器人的电子邮件地址是“john.smith@abc.com”，则此用户的 ADS 配置文件名称应为“john.smith.txt”。

内置的 ADS 技能会收集这些.txt 配置文件的必要数量，并将它们转换为.xlsx 格式，生成的.xlsx 能够批量导入到 ADS Power。

### 在图形用户界面上创建自定义技能的步骤

### 用代码创建自定义技能的步骤

- 创建一个目录 $ECBOT_DATA_HOME/resource/skills/my/%platform_%app_%site_%page，其中 %page、%app、%site、%page 是您的技能的平台、应用、站点、页面的简写名称。

  - 例如：win_chrome_ebay_home 将是您的技能应用的设置目录：Windows、Chrome 浏览器、eBay 站点、卖家主页。

- 在此目录下，创建一个 %skill_name.json 文件和一个 %skill_name 目录，并且在该目录内将有两个子目录：“images”和“scripts”

    - 例如：如果您的技能是关于履行订单的，您可以将您的技能目录命名为“fullfill_orders”，以及相应的技能定义 JSON 文件。

- “images”目录包含您期望此技能能够在屏幕捕获图像上识别的所有图标。

- “scripts”目录包含定义技能相关的所有锚点和信息元素的.csk 文件

- 然后，整个目录将通过技能编辑器菜单下的“CSK 上传”按钮上传到云端。