# this is a template file for user supplied external hook function which will be
# called by the "External Hook" instruction. Note:
# 1) this file should be located under $ECBOT_DATA_HOME\user_log_name directory, where
#    user_log_name is user email with "@" and "." replaced by "_"
# 2) file name externa_hook.py is the default name the actual name depends on the actual hook
#    instruction settings, this should be specified in the skill manual.
# 3) the function name "run" and input params (which is a json data structure) is fixed, and
#    should NOT be renamed. The specific format and definition of params is again specified
#    by the skill manual of the skill that uses the external hook instruction.
# 4) the existence of this file is NOT mandatory, a skill will run if this file doesn't exist,
#    the skill run will treat this as a NOP if this file is not there.
# external_hook.py
def run(params):
    # Example: Perform some task with the input parameters
    print("External script running with parameters:", params)
    return {"status": "success", "data": 42}