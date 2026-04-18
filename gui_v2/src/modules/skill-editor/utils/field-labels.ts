/**
 * Shared field label internationalization utilities
 * Provides common field label translations to avoid duplication across nodes
 */
import { TFunction } from 'i18next';

/**
 * Get internationalized label for common field names
 * @param key - Field name
 * @param t - Translation function from useTranslation('skillEditor')
 * @returns Internationalized label or original key if no mapping exists
 */
export function getCommonFieldLabel(key: string, t: TFunction): string {
  const commonFieldMap: Record<string, string> = {
    // LLM related fields
    'temperature': t('nodes.llm.temperature'),
    'maxTokens': t('nodes.llm.maxTokens'),
    'systemPrompt': t('nodes.llm.systemPrompt'),
    'prompt': t('nodes.llm.prompt'),
    'topP': t('nodes.llm.topP'),
    'frequencyPenalty': t('nodes.llm.frequencyPenalty'),
    'presencePenalty': t('nodes.llm.presencePenalty'),
    'stopSequences': t('nodes.llm.stopSequences'),
    'seed': t('nodes.llm.seed'),
    'responseFormat': t('nodes.llm.responseFormat'),
    'tools': t('nodes.llm.tools'),
    'toolChoice': t('nodes.llm.toolChoice'),
    'attachments': t('nodeState.fields.attachments'),
    
    // Browser automation fields
    'tool': t('nodes.browserAutomation.tool'),
    'browser': t('nodes.browserAutomation.browser'),
    'browserDriver': t('nodes.browserAutomation.browserDriver'),
    'cdpPort': t('nodes.browserAutomation.cdpPort'),
    'headless': t('nodes.browserAutomation.headless'),
    'runEnvironment': t('nodes.browserAutomation.runEnvironment'),
    'privacyStrategy': t('nodes.browserAutomation.privacyStrategy'),
    'enableJudge': t('nodes.browserAutomation.enableJudge'),
    'shopName': t('nodes.browserAutomation.shop'),
    'customShopName': t('nodes.browserAutomation.customShopName'),
    'modelProvider': t('nodes.browserAutomation.modelProvider'),
    'modelName': t('nodes.browserAutomation.model'),
    'useThinking': t('nodes.browserAutomation.useThinking'),
    'useVision': t('nodes.browserAutomation.useVision'),
    'profile': t('nodes.browserAutomation.profile'),
    'flashMode': t('nodes.browserAutomation.flashMode'),
    'maxSteps': t('nodes.browserAutomation.maxSteps'),
    'maxActionsPerStep': t('nodes.browserAutomation.maxActionsPerStep'),
    'domFocusSelector': t('nodes.browserAutomation.domFocusSelector'),
    'domLimit': t('nodes.browserAutomation.domLimit'),
    'promptSelection': t('nodes.llm.promptSelection'),
    'promptId': t('nodes.llm.promptId'),
    'promptId_selector': t('nodes.llm.promptSelector'),
    'systemPromptId': t('nodes.llm.systemPromptId'),
    'systemPromptId_selector': t('nodes.llm.systemPromptSelector'),
    
    // Loop fields
    'loopMode': t('nodeState.fields.loopMode'),
    'loopWhileExpr': t('nodeState.fields.loopWhileExpr'),
    'loopCountExpr': t('nodeState.fields.loopCountExpr'),
    'loopOutputs': t('nodeState.fields.loopOutputs'),
    
    // MCP fields
    'run_local': t('nodeState.fields.run_local'),
    
    // HTTP fields
    'apiKey': t('nodeState.fields.apiKey'),
    
    // Common fields
    'name': t('nodes.common.name'),
    'description': t('nodes.common.description'),
    'type': t('nodes.common.type'),
    'value': t('nodes.common.value'),
  };
  
  return commonFieldMap[key] || key;
}

/**
 * Create a field label getter function bound to a translation function
 * Useful for creating a reusable getter in components
 */
export function createFieldLabelGetter(t: TFunction) {
  return (key: string) => getCommonFieldLabel(key, t);
}
