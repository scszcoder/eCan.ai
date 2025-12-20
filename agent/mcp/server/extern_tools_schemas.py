import os
import json

def add_extern_tools_schemas(tool_schemas):
    # read extern tools json file
    # check whether the file exists
    if not os.path.exists("extern_tools.json"):
        return
    with open("extern_tools.json", "r") as f:
        extern_tools = json.load(f)

    for tool in extern_tools:
        # check if it already exists in the existing tool_schemas
        if tool["name"] in [t["name"] for t in tool_schemas]:
            continue
        tool_schemas.append(tool)

def remove_extern_tools_schemas(tool_schemas, tools_tbd):
    for tool_tbd in tools_tbd:
        # find tool_tbd first using schema name field
        found = next((x for x in tool_schemas if x["name"] == tool_tbd["name"]), None)
        tool_schemas.remove(found)
