
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from bot.basicSkill import mousePressAndHoldOnScreenWord, readRandomWindow8


async def px_captcha_solve(main_win, keyword, duration, win_title_keyword=""):
    try:
        # take screenshot
        log_user = main_win.user.replace("@", "_").replace(".", "_")
        session = main_win.session
        token = main_win.get_auth_token()

        mission = main_win.getTrialRunMission()

        screen_data = await readRandomWindow8(mission, win_title_keyword, log_user, session,  token)

        # return the result
        if screen_data:
            # hold down this button for 12 seconds. then release
            # Number of seconds to hold the mouse button
            mousePressAndHoldOnScreenWord(screen_data, keyword, duration=duration)

    except Exception as e:
        err_trace = get_traceback(e, "ErrorSolvePxCaptcha")
        logger.debug(err_trace)