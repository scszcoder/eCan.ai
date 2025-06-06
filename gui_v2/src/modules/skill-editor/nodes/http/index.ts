import iconStart from "../../assets/icon-start.jpg";
import { FlowNodeRegistry } from "../../typings";
import { DEFAULT_NODE_OUTPUTS } from "../../typings/node-outputs";
import { WorkflowNodeType } from "../constants";
import { formMeta } from "./form-meta";

export const HttpNodeRegistry: FlowNodeRegistry = {
  type: WorkflowNodeType.Http,
  meta: {
    size: {
      width: 360,
      height: 211,
    },
  },
  info: {
    icon: iconStart,
    description: "Custom Http Node.",
  },
  formMeta,
  onAdd() {
    return {
      id: `http_${Date.now()}`,
      type: "http",
      data: {
        title: "http",
        http: {
          apiUrl: "https://api.example.com",
          apiMethod: "GET",
          bodyType: "none",
          timeout: 10,
          retry: 2,
          ignoreError: false,
          requestHeaders: {
            properties: {
              "Content-Type": {
                type: "string"
              }
            }
          },
          requestHeadersValues: {
            "Content-Type": {
              type: "constant",
              content: "application/json"
            }
          },
          requestParams: {
            properties: {},
            values: {}
          },
          bodyData: "{}",
          bodyFormData: {
            properties: {},
            values: {}
          }
        },
        outputs: DEFAULT_NODE_OUTPUTS,
      },
    };
  },
};
