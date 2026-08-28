/**
 * Repro/regression test for the prompt-editor "import from file" button:
 * picking a .md file must load its contents into the editor draft, switch
 * to MD mode, and enter edit mode.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import PromptsDetail from '../../pages/Prompts/PromptsDetail';
import type { Prompt } from '../../pages/Prompts/types';

jest.mock('../../config/platform', () => ({ isWebPlatform: () => true }));
// TextareaAutoComplete transitively imports appSyncClient which uses
// import.meta (unsupported in jest's CJS transform) — stub it out.
jest.mock('../../pages/Prompts/components/TextareaAutoComplete', () => ({
  __esModule: true,
  default: () => null,
}));
jest.mock('../../stores/toolStore', () => ({
  useToolStore: () => ({ tools: [], fetchTools: jest.fn().mockResolvedValue(undefined) }),
}));
jest.mock('../../stores/userStore', () => ({
  useUserStore: (sel: any) => sel({ username: 'tester' }),
}));
jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_k: string, opts?: any) =>
      (opts && typeof opts === 'object' && 'defaultValue' in opts ? opts.defaultValue : _k),
  }),
}));

const basePrompt: Prompt = {
  id: 'pr-test1',
  title: 'Test Prompt',
  topic: 'testing',
  usageCount: 0,
  sections: [],
  userSections: [],
  humanInputs: [],
  source: 'my_prompts',
  readOnly: false,
  format: 'json',
};

function pickFile(input: HTMLInputElement, file: File) {
  Object.defineProperty(input, 'files', { value: [file], configurable: true });
  fireEvent.change(input);
}

describe('PromptsDetail import-from-file', () => {
  it('loads a .md file into the draft, switches to MD mode, enters edit mode', async () => {
    const { container } = render(
      <PromptsDetail prompt={basePrompt} onChange={jest.fn()} />
    );

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    expect(input).toBeTruthy();

    const md = '# Imported Title\n\nHello from file.';
    const file = new File([md], 'sample.md', { type: 'text/markdown' });
    if (typeof (file as any).text !== 'function') {
      (file as any).text = () => Promise.resolve(md);
    }
    pickFile(input, file);

    await waitFor(() => {
      const tas = Array.from(container.querySelectorAll('textarea'));
      expect(tas.some((ta) => ta.value.includes('Hello from file.'))).toBe(true);
    });
  });

  it('loads a prompt .json file, switches to JSON mode, enters edit mode', async () => {
    const { container } = render(
      <PromptsDetail prompt={{ ...basePrompt, id: 'pr-test2' }} onChange={jest.fn()} />
    );
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    const doc = JSON.stringify({
      sections: [{ id: 's1', type: 'role', items: ['You are a test robot.'] }],
    });
    const file = new File([doc], 'sample.json', { type: 'application/json' });
    if (typeof (file as any).text !== 'function') {
      (file as any).text = () => Promise.resolve(doc);
    }
    pickFile(input, file);

    await waitFor(() => {
      expect(screen.getByDisplayValue('You are a test robot.')).toBeTruthy();
    });
  });
});
