# -*- coding:utf-8 -*-
# @Time: 2021/1/30 11:40
# @Author: Zhanyi Hou
# @Email: 1295752786@qq.com
# @File: autocomp.py
import re
import time
from qtpy.QtCore import QThread, Signal

# logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)
from utils.logger_helper import logger_helper


class AutoCompThread(QThread):
    '''
    当一段时间没有补全需求之后，后台自动补全线程会进入休眠模式。下一次补全请求则会唤醒该后台线程。
    '''
    trigger = Signal(tuple, list)

    def __init__(self):
        super(AutoCompThread, self).__init__()
        self.text = ''
        self.text_cursor_pos = (0, 1)
        self.activated = True
        self.stop_flag = False

    def run(self):
        text = ''
        last_complete_time = time.time()
        try:
            import jedi
        except ImportError:
            print('Jedi not installed.install jedi for better auto-completion!')
            return
        while (1):
            if self.stop_flag:
                return

            target_text = self.text
            target_text_cursor_pos = self.text_cursor_pos

            if target_text == text:
                if time.time() - last_complete_time >= 30:
                    self.activated = False
                time.sleep(0.02 if self.activated else 0.1)
                continue

            try:
                row_text = target_text.splitlines()[target_text_cursor_pos[0] - 1]
                hint = re.split(
                    '[.:;,?!\s \+ \- = \* \\ \/  \( \)\[\]\{\} ]', row_text)[-1]
                content = (
                    target_text_cursor_pos[0], target_text_cursor_pos[1], hint
                )
                logger_helper.debug('Text of current row:%s' % content[2])
                script = jedi.Script(target_text)
                l = script.complete(*target_text_cursor_pos)

            except:
                import traceback
                traceback.print_exc()
                l = []
            self.trigger.emit(content, l)
            last_complete_time = time.time()

            self.activated = True
            text = target_text

    def on_exit(self):
        self.stop_flag = True
        self.exit(0)
        if self.isRunning():
            self.quit()
        self.wait(500)
