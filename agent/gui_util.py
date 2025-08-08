from PySide6.QtCore import QObject, Signal, Slot
import json
from agent.ec_skill import *

class IPCBridge(QObject):
    sendToJS = Signal(str)

    def route_logic(self):
        if True:
            result = "a"
        else:
            result = "b"

        return result


    def switch_case_logic(self):
        if True:
            result = "a"
        else:
            result = "b"

        return result



    @Slot(str)
    def receiveFromJS(self, message: str):
        print(f"[JS → Python] {message}")
        # optionally: parse JSON and call backend logic

        diagram_json = json.loads(message)
        # translate diagram json to langgraph
        if diagram_json["nodes"]:
            workflow = StateGraph(NodeState, WorkFlowContext)

            for node in diagram_json["nodes"]:
                if node["type"] == "start":
                    workflow.set_entry_point(node.title)
                elif node["type"] == "end":
                    workflow.add_node(node.title, END)
                elif node["type"] == "condition":
                    workflow.add_node("message_handler", supervisor_task_scheduler)
                    workflow.add_conditional_edges("verify", route_logic, {
                        "llm_loop": "llm_loop",
                        END: END
                    })

                elif node["type"] == "loop":
                    workflow.add_node("message_handler", supervisor_task_scheduler)
                elif node["type"] == "llm":
                    workflow.add_node("message_handler", supervisor_task_scheduler)
                elif node["type"] == "tool call":
                    workflow.add_node(node.title, node.callable)

            for edge in diagram_json["edges"]:
                workflow.add_edge(edge["sourceNodeID"], edge["targetNodeID"])