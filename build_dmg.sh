# 创建临时目录
#mkdir MyApp_temp
#
## 将生成的可执行文件移动到临时目录
#mv dist/MyApp MyApp_temp/

# 使用 hdiutil 创建 DMG 文件
hdiutil create -volname ecbot -srcfolder dist/ecbot.app -ov -format UDZO dist/ecbot.dmg

## 删除临时目录
#rm -r MyApp_temp
