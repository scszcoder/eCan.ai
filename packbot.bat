::cd C:\Users\songc\PycharmProjects\ecbot\ecbot-ui
::call yarn
::call yarn build
IF NOT EXIST "C:\Users\songc\ECBotApp" (
    mkdir "C:\Users\songc\ECBotApp"
)
cd /d C:\Users\songc\PycharmProjects\ecbot
::call venv\Scripts\activate
::pyinstaller.exe @pyinstaller_args.txt
C:\Users\songc\PycharmProjects\ecbot\venv\Scripts\pyinstaller.exe --noconfirm pyinstaller_args.spec
::cd C:\Users\songc\ECBotApp
cd C:\Users\songc\PycharmProjects\ecbot\dist
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" .\packECBot.iss


