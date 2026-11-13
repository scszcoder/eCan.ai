import {
  claimManagerSave,
  confirmManagerSave,
  releaseManagerSave,
  managerSaveKey,
  readManagerBuild,
  suppressCanvasLoad,
  consumeCanvasLoadSuppression,
  handleManagerBuildDone,
} from './manager-skill-save';

const flowgram = {
  nodes: [{ id: 'start_0', type: 'start' }, { id: 'end_0', type: 'end' }],
  edges: [{ sourceNodeID: 'start_0', targetNodeID: 'end_0' }],
  metadata: { skillName: 'etsy_reply' },
};
const handoff = { skill_name: 'etsy_reply', store_id: 'etsy_0', sessionId: 'thread-1' };

describe('manager skill save guard', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('claims a (sessionId, skill_name, messageId) only once', () => {
    const key = managerSaveKey(handoff, 'msg-a');
    expect(claimManagerSave(key)).toBe(true);
    expect(claimManagerSave(key)).toBe(false);          // in flight
    confirmManagerSave(key);
    expect(claimManagerSave(key)).toBe(false);          // saved
    expect(claimManagerSave(managerSaveKey(handoff, 'msg-b'))).toBe(true);
  });

  it('lets a failed save be retried', () => {
    const key = managerSaveKey(handoff, 'msg-fail');
    expect(claimManagerSave(key)).toBe(true);
    releaseManagerSave(key);
    expect(claimManagerSave(key)).toBe(true);
  });

  it('remembers saves across reloads (localStorage)', () => {
    const key = managerSaveKey(handoff, 'msg-persist');
    confirmManagerSave(key);
    expect(JSON.parse(localStorage.getItem('ecan_manager_skill_saves') || '[]')).toContain(key);
  });

  it('does not start a second save for a repeated stream_end', () => {
    const payload = { sessionId: 's1', messageId: 'msg-repeat', managerHandoff: handoff, flowgram, state: 'complete' };
    confirmManagerSave(managerSaveKey(handoff, 'msg-repeat'));
    expect(handleManagerBuildDone(payload)).toBeNull();
  });

  it('ignores stream_ends that are not Manager builds', () => {
    expect(readManagerBuild({ flowgram })).toBeNull();
    expect(readManagerBuild({ managerHandoff: handoff })).toBeNull();
    expect(handleManagerBuildDone({ sessionId: 's1', messageId: 'm', flowgram })).toBeNull();
    expect(readManagerBuild({ managerHandoff: JSON.stringify(handoff), flowgram })?.handoff.sessionId).toBe('thread-1');
    expect(readManagerBuild({ managerHandoff: handoff, flowgram, state: 'awaiting_plan_approval' })).toBeNull();
  });

  it('skips the canvas load of a Manager-built flowgram once', () => {
    suppressCanvasLoad(flowgram);
    expect(consumeCanvasLoadSuppression(JSON.parse(JSON.stringify(flowgram)))).toBe(true);
    expect(consumeCanvasLoadSuppression(flowgram)).toBe(false);
  });
});
