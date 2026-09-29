import { nanoid } from 'nanoid';

import { WorkflowNodeType } from '../constants';
import { FlowNodeRegistry } from '../../typings';
import iconMediaGen from '../../assets/icon-media-gen.svg';
import { DEFAULT_NODE_OUTPUTS } from '../../typings/node-outputs';
import { formMeta } from './form-meta';

let index = 0;
export const MediaGenNodeRegistry: FlowNodeRegistry = {
  type: WorkflowNodeType.MediaGen,
  info: {
    icon: iconMediaGen,
    description: 'nodes.mediaGen.description',
  },
  meta: {
    size: {
      width: 360,
      height: 390,
    },
  },
  onAdd() {
    return {
      id: `media-gen_${nanoid(5)}`,
      type: 'media-gen',
      data: {
        title: `MediaGen_${++index}`,
        inputsValues: {
          mediaType: { type: 'constant', content: 'image' },
          modelName: { type: 'constant', content: 'wan2.2-t2i-plus' },
          prompt: { type: 'template', content: '' },
          negativePrompt: { type: 'constant', content: '' },
          referenceImages: { type: 'template', content: '' },
          firstFrame: { type: 'template', content: '' },
          lastFrame: { type: 'template', content: '' },
          size: { type: 'constant', content: '' },
          aspectRatio: { type: 'constant', content: '' },
          n: { type: 'constant', content: 1 },
          durationSeconds: { type: 'constant', content: 5 },
          resolution: { type: 'constant', content: '' },
          generateAudio: { type: 'constant', content: '' },
          voice: { type: 'constant', content: '' },
          audioFormat: { type: 'constant', content: '' },
          speed: { type: 'constant', content: 1 },
          timeoutSeconds: { type: 'constant', content: '' },
          outputSubdir: { type: 'constant', content: '' },
        },
        inputs: {
          type: 'object',
          required: ['mediaType', 'modelName', 'prompt'],
          properties: {
            mediaType: { type: 'string' },
            modelName: { type: 'string' },
            prompt: { type: 'string', extra: { formComponent: 'prompt-editor' } },
            negativePrompt: { type: 'string' },
            referenceImages: { type: 'string', extra: { formComponent: 'prompt-editor' } },
            firstFrame: { type: 'string', extra: { formComponent: 'prompt-editor' } },
            lastFrame: { type: 'string', extra: { formComponent: 'prompt-editor' } },
            size: { type: 'string' },
            aspectRatio: { type: 'string' },
            n: { type: 'number' },
            durationSeconds: { type: 'number' },
            resolution: { type: 'string' },
            generateAudio: { type: 'boolean' },
            voice: { type: 'string' },
            audioFormat: { type: 'string' },
            speed: { type: 'number' },
            timeoutSeconds: { type: 'number' },
            outputSubdir: { type: 'string' },
          },
        },
        outputs: DEFAULT_NODE_OUTPUTS,
      },
    };
  },
  formMeta: formMeta,
};
