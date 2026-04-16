# AppSync Resolvers — readScreen API (`ydusqd3wgfb6loiu2daej6qa6y`)

Last updated: 2026-03-18

## Query

| Field | Data Source |
|---|---|
| `checkSkillExists` | `agentScheduler` |
| `genSchedules` | `botScheduler` |
| `getA2AMessages` | `chatter` |
| `getAgentKnowledges` | `agentScheduler` |
| `getAgentSkills` | `agentScheduler` |
| `getAgentTasks` | `agentScheduler` |
| `getAgentTools` | `agentScheduler` |
| `getAgents` | `agentScheduler` |
| `getAllMine` | `AgentLambdaDS` |
| `getAvatars` | `agentScheduler` |
| `getBots` | `botScheduler` |
| `getEditorCache` | `agentScheduler` |
| `getFB` | `agentScheduler` |
| `getLabelFormats` | `agentScheduler` |
| `getNodeStateSchema` | `agentScheduler` |
| `getOrgAgentTree` | `AgentLambdaDS` |
| `getOrgTree` | `AgentLambdaDS` |
| `getOrgs` | `AgentLambdaDS` |
| `getPromptVersion` | `agentScheduler` |
| `getPrompts` | `agentScheduler` |
| `getScene` | `agentScheduler` |
| `getSceneRequestStatus` | `startSceneChange` |
| `getSceneTemplates` | `startSceneChange` |
| `getSettings` | `startSceneChange` |
| `getSkillEditorChatHistory` | `skillEditorAgent` |
| `getSkillEditorChatSessions` | `skillEditorAgent` |
| `getSkillEditorEvents` | `skillEditorAgent` |
| `getSkillRunStatus` | `AgentLambdaDS` |
| `getStory` | `skillEditorAgent` |
| `getVehicles` | `AgentLambdaDS` |
| `getWanMessage` | `agentScheduler` |
| `getWarehouses` | `agentScheduler` |
| `listPromptVersions` | `agentScheduler` |
| `listSkillFiles` | `agentScheduler` |
| `listSkillRevisions` | `skillEditorAgent` |
| `listStories` | `agentScheduler` |
| `loadSkillEditorContexts` | `skillEditorAgent` |
| `loadSkillSchemas` | `skillEditorAgent` |
| `openSkillFile` | `agentScheduler` |
| `queryAgentKnowledges` | `agentScheduler` |
| `queryAgentOrgRels` | `agentScheduler` |
| `queryAgentSkillKnowledgeRels` | `agentScheduler` |
| `queryAgentSkillRels` | `agentScheduler` |
| `queryAgentSkillToolRels` | `agentScheduler` |
| `queryAgentSkills` | `agentScheduler` |
| `queryAgentTaskRels` | `agentScheduler` |
| `queryAgentTaskSkillRels` | `agentScheduler` |
| `queryAgentTasks` | `agentScheduler` |
| `queryAgentTools` | `agentScheduler` |
| `queryAgents` | `agentScheduler` |
| `queryApiKeys` | `getKey` |
| `queryAvatars` | `agentScheduler` |
| `queryBots` | `botScheduler` |
| `queryChats` | `chatter` |
| `queryCloudTaskRunId` | `taskStatus` |
| `queryOrgs` | `agentScheduler` |
| `queryPrompts` | `agentScheduler` |
| `queryPromptVersions` | `agentScheduler` |
| `queryRAGs` | `agentScheduler` |
| `queryScenes` | `agentScheduler` |
| `querySkills` | `botScheduler` |
| `queryVehicles` | `agentScheduler` |
| `readSkillFile` | `agentScheduler` |
| `regSteps` | `agentScheduler` |
| `reqAccountInfo` | `ecbAccountManager` |
| `reqFileOp` | `agentScheduler` |
| `reqMachineLanAddr` | `getMachineLanAddr` |
| `reqOrderInfo` | `ecbAccountManager` |
| `reqScreenIconRead` | `rdPCScreen001` |
| `reqScreenTxtRead` | `rdPCScreen001` |
| `requestSkillFileDownloadUrl` | `agentScheduler` |

## Mutation

| Field | Data Source |
|---|---|
| `addAccts` | `ecbAccountManager` |
| `addAgentKnowledges` | `agentScheduler` |
| `addAgentOrgRels` | `agentScheduler` |
| `addAgentSkillKnowledgeRels` | `agentScheduler` |
| `addAgentSkillRels` | `agentScheduler` |
| `addAgentSkillToolRels` | `agentScheduler` |
| `addAgentSkills` | `agentScheduler` |
| `addAgentTaskRels` | `agentScheduler` |
| `addAgentTaskSkillRels` | `agentScheduler` |
| `addAgentTasks` | `agentScheduler` |
| `addAgentTools` | `agentScheduler` |
| `addAgents` | `agentScheduler` |
| `addAvatars` | `agentScheduler` |
| `addBots` | `botScheduler` |
| `addLabelFormats` | `agentScheduler` |
| `addMissions` | `botScheduler` |

| `addOrgs` | `agentScheduler` |
| `addProducts` | `agentScheduler` |

| `addPrompts` | `agentScheduler` |
| `addSkills` | `botScheduler` |
| `addVehicles` | `agentScheduler` |
| `addWareHouses` | `agentScheduler` |
| `cancelRunSkill` | `skillEditorAgent` |

| `cancelSkillEditorChatGeneration` | `skillEditorAgent` |
| `clearEditorCache` | `skillEditorAgent` |
| `clearSkillBreakpoints` | `skillEditorAgent` |
| `copySkillTo` | `skillEditorAgent` |
| `createSkillEditorChatSession` | `skillEditorAgent` |
| `deleteScene` | `agentScheduler` |
| `deleteSkillEditorChatSession` | `skillEditorAgent` |
| `deleteSkillFiles` | `skillEditorAgent` |
| `endLongLLMTask` | `llm_notifier` |  pipline resolver -> Mutation_EndLLMTask
| `initReqScene` | `scenesDynamoDB` |
| `injectSkillState` | `agentScheduler` |
| `loadSkillSchemas` | `agentScheduler` |
| `makeBusinessOrders` | `ecbAccountManager` |
| `makeOrder` | `ecbAccountManager` |
| `pauseRunSkill` | `agentScheduler` |
| `processSkillZipUpload` | `skillEditorAgent` |

| `publishAccountNotification` | `acctNotification` |  pipline resolver -> Mutation_publishAccountNotification_Function
| `publishPassiveCommand` | `passiveCommand` |  pipline resolver -> Mutation_publishPassiveCommand_Function
| `publishPassiveHello` | `passiveCommand` |  pipline resolver -> Mutation_publishPassiveCommand_Function
| `publishPassiveStepResult` | `passiveStepResult` |  pipline resolver -> Mutation_publishPassiveStepResult_Function
| `publishSceneResult` | `scene_notifier` |  pipline resolver -> mutation_publish_scene_result
| `publishSkillEditorStreamEvent` | `SkillEditorStreamEvent` |  pipline resolver -> Mutation_PublishSkillEditorStreamEvent_Function
| `publishTaskStatus` | `taskStatus` |  pipline resolver -> Mutation_publishTaskStatus_Function
| `readyReqScene` | `taskStatus` |  pipline resolver -> Mutation_publishTaskStatus_Function
| `removeAccts` | `ecbAccountManager` |
| `removeAgentKnowledges` | `agentScheduler` |
| `removeAgentOrgRels` | `agentScheduler` |
| `removeAgentSkillKnowledgeRels` | `agentScheduler` |
| `removeAgentSkillRels` | `agentScheduler` |
| `removeAgentSkillToolRels` | `agentScheduler` |
| `removeAgentSkills` | `agentScheduler` |
| `removeAgentTaskRels` | `agentScheduler` |
| `removeAgentTaskSkillRels` | `agentScheduler` |

| `removeAgentTasks` | `agentScheduler` |
| `removeAgentTools` | `agentScheduler` |
| `removeAgents` | `agentScheduler` |
| `removeApiKey` | `agentScheduler` |

| `removeAvatars` | `agentScheduler` |
| `removeBots` | `agentScheduler` |
| `removeBusinessOrders` | `ecbAccountManager` |
| `RemoveLabelFormats` | `agentScheduler` |
| `removeMissions` | `agentScheduler` |

| `RemoveWareHouses` | `agentScheduler` |
| `UpdateLabelFormats` | `agentScheduler` |
| `UpdateWarehouses` | `agentScheduler` |

| `removeOrgs` | `agentScheduler` |
| `removeProducts` | `agentScheduler` |

| `removePrompts` | `agentScheduler` |
| `removeSkills` | `botScheduler` |
| `removeVehicles` | `agentScheduler` |
| `reportRunExtSkillStatus` | `skillEditorAgent` |
| `reportStatus` | `agentScheduler` |
| `reqApiKey` | `agentScheduler` |
| `reqLogAnalysis` | `agentScheduler` |
| `reqPromptAutoCompletion` | `agentScheduler` |

| `reqPuzzleSolver` | `agentScheduler` |
| `reqRAGStore` | `agentScheduler` |
| `reqScene` | `agentScheduler` |

| `reqTrain` | `agentScheduler` |
| `requestPuzzleSolve` | `puzzle_problem` |  pipline resolver -> 
Mutation_RequestPuzzleSolve_Function
| `requestRunExtSkill` | `skillEditorAgent` |
| `requestSkillFileUploadUrl` | `skillEditorAgent` |

| `requestSkillState` | `skillEditorAgent` |
| `resumeRunSkill` | `skillEditorAgent` |
| `revertSkillRevision` | `skillEditorAgent` |

| `runCloudTasks` | `skillEditorAgent` |
| `runSkill` | `skillEditorAgent` |
| `runTest` | `skillEditorAgent` |



| `saveEditorCache` | `skillEditorAgent` |
| `scaffoldSkill` | `skillEditorAgent` |
| `sendA2AMessage` | `a2a` |  pipline resolver -> Mutation_sendA2AMessage_Function
| `sendCloudA2AMessage` | `a2a` |  pipline resolver -> Mutation_sendA2AMessage_Function
| `sendPuzzleSolution` | `Puzzle_Solution` |  pipline resolver -> Mutation_SendPuzzleSolution_Function
| `sendSkillEditorChatMessage` | `skillEditorAgent` |
| `sendWanMessage` | `nada` |  pipline resolver -> Mutation_sendWanMessage_Function

| `setSkillBreakpoints` | `agentScheduler` |
| `setupSimStep` | `agentScheduler` |
| `simSseEvent` | `agentScheduler` |
| `simTimerEvent` | `agentScheduler` |
| `simWebhookEvent` | `agentScheduler` |
| `simWebsocketEvent` | `agentScheduler` |
| `startLongLLMTask` | `agentScheduler` |

| `startSoap` | `agentScheduler` |
| `stepRunSkill` | `agentScheduler` |
| `stepSim` | `agentScheduler` |

| `stopSoap` | `agentScheduler` |
| `testLanggraph2Flowgram` | `agentScheduler` |

| `updateAccts` | `ecbAccountManager` |

| `updateAgentKnowledges` | `agentScheduler` |
| `updateAgentOrgRels` | `agentScheduler` |

| `updateAgentSkillKnowledgeRels` | `agentScheduler` |
| `updateAgentSkillRels` | `agentScheduler` |
| `updateAgentSkillToolRels` | `agentScheduler` |

| `updateAgentSkills` | `agentScheduler` |


| `updateAgentTaskRels` | `agentScheduler` |

| `updateAgentTaskSkillRels` | `agentScheduler` |

| `updateAgentTasks` | `agentScheduler` |
| `updateAgentTools` | `agentScheduler` |
| `updateAgents` | `agentScheduler` |
| `updateAvatars` | `agentScheduler` |
| `updateBots` | `botScheduler` |

| `updateBusinessOrders` | `ecbAccountManager` |

| `updateMissions` | `agentScheduler` |

| `updateMissionsExStatus` | `agentScheduler` |

| `updateOrgs` | `agentScheduler` |
| `updateProducts` | `agentScheduler` |
| `updatePrompts` | `agentScheduler` |

| `updateScene` | `scene_notifier` |  pipline resolver -> Mutation_changeScene_Function
| `updateSettings` | `agentScheduler` |

| `updateSkills` | `botScheduler` |
| `updateStory` |  `scene_notifier` |  pipline resolver -> Mutation_updateScene_Function
| `updateVehicles` | `agentScheduler` |
| `writeSkillFile` | `agentScheduler` |
