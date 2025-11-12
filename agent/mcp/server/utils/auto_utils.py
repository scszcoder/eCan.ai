import pyautogui

def mouseClick(loc):
    pyautogui.moveTo(loc[0], loc[1])
    pyautogui.click()

def mousePressAndHold(loc, duration):
    # Move to the position
    pyautogui.moveTo(loc[0], loc[1])

    # Press and hold left mouse button down
    pyautogui.mouseDown()

    # Wait
    time.sleep(duration)

    # Release the mouse button
    pyautogui.mouseUp()

