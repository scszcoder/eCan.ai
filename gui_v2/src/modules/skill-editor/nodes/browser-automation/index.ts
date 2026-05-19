/**
 * Browser Automation node
 */
import { nanoid } from 'nanoid';

import { WorkflowNodeType } from '../constants';
import { FlowNodeRegistry } from '../../typings';
import iconBrowserAutomation from '../../assets/icon-browser-automation.svg';
import { DEFAULT_NODE_OUTPUTS } from '../../typings/node-outputs';
import { formMeta } from './form-meta';

let index = 0;

export const BrowserAutomationNodeRegistry: FlowNodeRegistry = {
  type: WorkflowNodeType.BrowserAutomation,
  info: {
    icon: iconBrowserAutomation,
    description: 'nodes.browserAutomation.description',
  },
  meta: {
    size: {
      width: 360,
      height: 420,
    },
  },
  onAdd() {
    return {
      id: `browser_automation_${nanoid(5)}`,
      type: 'browser-automation',
      data: {
        title: `Browser_${++index}`,
        inputsValues: {
          tool: { type: 'constant', content: 'browser-use' },
          browser: { type: 'constant', content: 'new chromium' },
          browserDriver: { type: 'constant', content: 'native' },
          cdpPort: { type: 'constant', content: '9228' },
          cdpPortAuto: { type: 'constant', content: false },
          headless: { type: 'constant', content: false },
          runEnvironment: { type: 'constant', content: 'full_local' },
          privacyStrategy: { type: 'constant', content: 'none' },
          enableJudge: { type: 'constant', content: false },
          shopName: { type: 'constant', content: 'amazon' },
          customShopName: { type: 'constant', content: '' },
          modelProvider: { type: 'constant', content: 'OpenAI' },
          modelName: { type: 'constant', content: 'gpt-3.5-turbo' },
          temperature: { type: 'constant', content: 0.3 },
          useThinking: { type: 'constant', content: false },
          useVision: { type: 'constant', content: false },
          profile: { type: 'constant', content: '' },
          flashMode: { type: 'constant', content: false },
          maxSteps: { type: 'constant', content: 15 },
          maxActionsPerStep: { type: 'constant', content: '' },
          domFocusSelector: { type: 'constant', content: '' },
          domLimit: { type: 'constant', content: '' },
          loopHistoryMode: { type: 'constant', content: 'clear' },
          actionableField: { type: 'constant', content: '' },
          hotPathActions: { type: 'constant', content: '' },
          autoDispatch: { type: 'constant', content: '' },
          assignment: { type: 'constant', content: '' },
          preDispatch: { type: 'constant', content: '' },
          stepPatches: { type: 'constant', content: '' },
          tabPolicy: { type: 'constant', content: '' },
          // ── Per-node performance tunables (2026-05-18) ──
          // Layered resolution: this value (if set) → env ECAN_<NAME> →
          // hardcoded default in
          // agent/ec_skills/browser_use_extension/hooks/external/feige_chat/tunables.py.
          // Empty / 0 means "use the layer below".  Defaults below
          // intentionally empty so the runtime falls through to the
          // conservative v0.9.79 defaults; product-listing skills
          // should override here per-node.
          hotPathToolTimeoutS: { type: 'constant', content: '' },
          hotPathDriftRetryMax: { type: 'constant', content: '' },
          feigeSendCdpEvaluateTimeoutS: { type: 'constant', content: '' },
          browserAutoMaxRetries: { type: 'constant', content: '' },
          browserAutoRetrySleepS: { type: 'constant', content: '' },
          systemPrompt: {
            type: 'template', 
            content: 'You are a helpful browser automation agent.\n\n⚠️ CRITICAL: You MUST respond with VALID JSON ONLY. No text before or after the JSON.\n\nRequired JSON Format:\n{\n  "evaluation_previous_goal": "string - evaluate the previous step",\n  "memory": "string - important information to remember",\n  "next_goal": "string - what to do next",\n  "action": [\n    {"action_name": {action_parameters}}\n  ]\n}\n\nAvailable Actions:\n- go_to_url: {"url": "https://..."}\n- click: {"xpath": "//button[@id=\'submit\']"}\n- input_text: {"xpath": "//input[@name=\'q\']", "text": "search query"}\n- scroll: {"direction": "down", "amount": 500}\n- extract: {"xpath": "//div[@class=\'content\']"}\n- done: {"text": "Task completed", "success": true}\n- search_google: {"query": "search term"}\n- open_tab, close_tab, switch_tab, go_back\n- list_files, read_file, upload_file and other registered local tools when needed\n\n【MULTI-PLATFORM RESEARCH RULES】\n1. Research target: Research up to 2 platforms (e.g. taobao.com, jd.com) as specified in the user prompt.\n2. For each platform: visit → search → extract product info (name, price, rating, reviews, sales count, images, description) → go to next platform.\n3. Stop condition: After completing ALL specified platforms (max 2), use the "done" action immediately with a summary report of all findings. Do NOT visit additional platforms beyond what was requested.\n4. Summary report format: {platform: xxx, products_found: N, avg_price: xxx, top_products: [...], recommendations: "..."}\n5. If a platform is blocked by anti-bot/captcha, skip it and continue with the next platform (if any remain).\n6. NEVER continue browsing after the research is complete.\n\nExample Response:\n{\n  "evaluation_previous_goal": "Researched taobao.com, extracted 15 products",\n  "memory": "Found 15 products on taobao. Need to research JD next.",\n  "next_goal": "Visit JD.com and search for the same product",\n  "action": [{"go_to_url": {"url": "https://www.jd.com"}}]\n}\n\nIMPORTANT Rules:\n1. ALWAYS output valid JSON with all 4 required fields\n2. "action" MUST be an array with at least 1 element\n3. Local file tools are allowed when needed for the task\n4. Use "done" action ONLY after completing all specified platforms\n5. NO text outside the JSON structure' 
          },
          prompt: { type: 'template', content: '' },
          promptSelection: { type: 'constant', content: 'inline' },
        },
        inputs: {
          type: 'object',
          required: ['tool', 'browser', 'browserDriver', 'modelProvider', 'modelName', 'temperature', 'prompt'],
          properties: {
            tool: { type: 'string', extra: { formComponent: 'input' } },
            browser: { type: 'string', extra: { formComponent: 'input' } },
            browserDriver: { type: 'string', extra: { formComponent: 'input' } },
            cdpPort: { type: 'string', extra: { formComponent: 'input' } },
            cdpPortAuto: { type: 'boolean', extra: { formComponent: 'checkbox' } },
            headless: { type: 'boolean', extra: { formComponent: 'checkbox' } },
            runEnvironment: { type: 'string', extra: { formComponent: 'select' } },
            privacyStrategy: { type: 'string', extra: { formComponent: 'select' } },
            enableJudge: { type: 'boolean', extra: { formComponent: 'checkbox' } },
            shopName: { type: 'string', extra: { formComponent: 'input' } },
            customShopName: { type: 'string', extra: { formComponent: 'input' } },
            modelProvider: { type: 'string', extra: { formComponent: 'input' } },
            modelName: { type: 'string', extra: { formComponent: 'input' } },
            temperature: { type: 'number' },
            useThinking: { type: 'boolean', extra: { formComponent: 'checkbox' } },
            useVision: { type: 'boolean', extra: { formComponent: 'checkbox' } },
            profile: { type: 'string', extra: { formComponent: 'input' } },
            flashMode: { type: 'boolean', extra: { formComponent: 'checkbox' } },
            maxSteps: { type: 'number' },
            maxActionsPerStep: { type: 'number' },
            domFocusSelector: { type: 'string', extra: { formComponent: 'input' } },
            domLimit: { type: 'number' },
            loopHistoryMode: { type: 'string', extra: { formComponent: 'select' } },
            actionableField: { type: 'string', extra: { formComponent: 'input' } },
            hotPathActions: { type: 'string', extra: { formComponent: 'textarea' } },
            autoDispatch: { type: 'string', extra: { formComponent: 'textarea' } },
            assignment: { type: 'string', extra: { formComponent: 'textarea' } },
            preDispatch: { type: 'string', extra: { formComponent: 'textarea' } },
            stepPatches: { type: 'string', extra: { formComponent: 'textarea' } },
            tabPolicy: { type: 'string', extra: { formComponent: 'select' } },
            // Per-node performance tunables (see onAdd above for the
            // resolution rules).  All optional; empty means "fall back
            // to env / hardcoded default".
            hotPathToolTimeoutS: { type: 'number' },
            hotPathDriftRetryMax: { type: 'number' },
            feigeSendCdpEvaluateTimeoutS: { type: 'number' },
            browserAutoMaxRetries: { type: 'number' },
            browserAutoRetrySleepS: { type: 'number' },
            systemPrompt: { type: 'string', extra: { formComponent: 'prompt-editor' } },
            prompt: { type: 'string', extra: { formComponent: 'prompt-editor', enablePromptLibrary: true } },
            promptSelection: { type: 'string', extra: { skipDefault: true } },
          },
        },
        outputs: DEFAULT_NODE_OUTPUTS,
      },
    };
  },
  formMeta: formMeta,
};
