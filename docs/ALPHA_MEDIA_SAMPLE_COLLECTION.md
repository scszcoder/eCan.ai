# 采集买家视频/图片样本（给 alpha 客户）

目的：让 eCan 能看懂买家在售后里发的**视频**（以及千牛里的**图片**），我们需要每个平台各一条真实样本，看清楚它在系统里长什么样。整个过程大约 30 分钟，**只看不回**，不会给买家发任何消息。

## 准备

- 一个**买家账号**（自己的小号即可），能给你的**测试店铺**发消息。
- 一段**短视频**（10–20 秒，手机随便拍，例如拍一下桌上的杯子）和一张**照片**。
- 电脑上有最新的 `cs_stress_bot.exe`（1.3.9 或更新；运行 `cs_stress_bot.exe --version` 查看）。

## 步骤

1. **照常打开 eCan**（抖店、拼多多、千牛都正常登录在线）。
2. 打开一个命令行窗口（Win 键 → 输入 `cmd` → 回车），进入放 `cs_stress_bot.exe` 的文件夹，运行：

   ```
   cs_stress_bot.exe --raw-all --duration 30
   ```

   eCan 开着时它会自动进入**只看不回**模式（窗口里会写 `WATCH ONLY`）。让它一直开着。
3. 用**买家小号**，按下面顺序给每个店铺发消息，每条之间隔 **1 分钟**，并**记下每条的发送时间**（到分钟就行）：

   | 平台 | 第 1 条 | 第 2 条 | 第 3 条 |
   |---|---|---|---|
   | 抖店（飞鸽） | 文字「视频样本测试」 | **视频** | 文字「视频发完了」 |
   | 拼多多 | 文字「视频样本测试」 | **视频** | 文字「视频发完了」 |
   | 千牛（淘宝） | 文字「样本测试」 | **视频** | **照片** |

   前后的文字是为了在日志里准确找到中间那条视频。
4. 每个平台发完后，在**商家后台的聊天窗口**里对视频那条消息**截一张图**（能看到视频缩略图和时间就行）。
5. 全部发完、等 1 分钟后，在 `cs_stress_bot` 窗口按 **Ctrl+C** 结束。
6. **千牛额外一步**：打开 PowerShell（Win 键 → 输入 `powershell` → 回车），复制粘贴下面这一整行，回车。它只**列出**最近 1 小时里千牛保存的视频/图片文件名（不会改动任何文件），结果存到桌面的 `qianniu_media_files.txt`：

   ```
   Get-ChildItem -Path "$env:APPDATA","$env:LOCALAPPDATA","$env:USERPROFILE\Documents" -Recurse -File -ErrorAction SilentlyContinue -Include *.mp4,*.mov,*.jpg,*.jpeg,*.png,*.webp | Where-Object { $_.LastWriteTime -gt (Get-Date).AddHours(-1) -and $_.FullName -match 'Ali|Wang|qianniu|千牛|Workbench' } | Select-Object LastWriteTime,Length,FullName | Format-Table -AutoSize | Out-File "$env:USERPROFILE\Desktop\qianniu_media_files.txt" -Width 400
   ```

## 需要 FTP 回来的文件

1. `cs_stress_bot.exe` 旁边的 `cs_bot_out\` 里**最新的那个文件夹**（按时间命名，整个文件夹）。
2. `%LOCALAPPDATA%\eCan.cn\runlogs\` 里的 `eCan.log`（如果有 `eCan.log.1` 或 `.rollover` 文件且时间覆盖测试时段，也一起）、`eCan.wscap.log`，以及 `qianniu_ocr\history\` 文件夹。
3. 桌面上的 `qianniu_media_files.txt`。
4. 第 4 步的三张截图。
5. 一行说明：每个平台视频/照片的**发送时间**，以及视频大约多长。

## 注意

- 用**测试店铺**和**自己的小号**，不要用真实顾客。
- 过程中**不用回复**，也不要关 eCan。
- 视频里不要拍到个人信息（脸、证件、地址等）。
