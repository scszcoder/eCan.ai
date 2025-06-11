

def run_tests(web_gui, data_holder, tests):
    return run_default_tests(web_gui, data_holder)

def run_default_tests(web_gui,data_holder):
    # test sending data to frontend
    web_gui.self_confirm()
    results = web_gui.update_all(data_holder)

    return results