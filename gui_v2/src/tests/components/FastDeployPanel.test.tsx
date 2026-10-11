import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, params?: Record<string, any>) => (params && params.id ? `${key}:${params.id}` : key),
    i18n: { language: 'zh-CN' },
  }),
}));

const executeRequest = jest.fn();
const getStoreCatalog = jest.fn();
jest.mock('@/services/ipc_api', () => ({
  get_ipc_api: () => ({ executeRequest, getStoreCatalog }),
}));
jest.mock('../../services/ipc_api', () => ({
  get_ipc_api: () => ({ executeRequest, getStoreCatalog }),
}));
jest.mock('@/pages/Agents/utils/refreshOrgAgents', () => ({ refreshOrgAgents: jest.fn().mockResolvedValue(true) }));
jest.mock('../../pages/Agents/utils/refreshOrgAgents', () => ({ refreshOrgAgents: jest.fn().mockResolvedValue(true) }));

import FastDeployPanel from '@/components/FastDeploy/FastDeployPanel';
import { areasFor, PLATFORM_DEPLOYS, newStoreId } from '@/components/FastDeploy/scenarios';

const openSelect = (testId: string) => {
  const sel = screen.getByTestId(testId);
  fireEvent.mouseDown(sel.querySelector('.ant-select-selector') as Element);
};
const pickOption = async (text: string) => {
  const opt = await waitFor(() => {
    const el = Array.from(document.querySelectorAll('.ant-select-item-option'))
      .find((n) => n.textContent === text);
    if (!el) throw new Error(`option ${text} not shown`);
    return el;
  });
  fireEvent.click(opt as Element);
};

beforeEach(() => {
  executeRequest.mockReset();
  getStoreCatalog.mockReset();
  getStoreCatalog.mockResolvedValue({ success: true, data: { stores: [
    { store_id: 'douyin-老店', name: '老店', platform: 'douyin', store_urls: ['https://im.jinritemai.com/x'] },
    { store_id: 'pdd-别家', name: '别家', platform: 'pinduoduo', store_urls: [] },
  ] } });
  executeRequest.mockResolvedValue({ success: true, data: { status: 'success', log: ['ok'], store_created: true } });
});

describe('Fast Deploy areas', () => {
  it('lists 客服 first, the rest grayed; JD has nothing to deploy yet', () => {
    const douyin = PLATFORM_DEPLOYS.find((p) => p.platform === 'douyin')!;
    const rows = areasFor(douyin);
    expect(rows.map((r) => r.area.nameZh)).toEqual(['客服', '售前', '售后', '营销', '调研', '经理']);
    expect(rows.filter((r) => r.scenario).map((r) => r.area.key)).toEqual(['cs']);
    expect(areasFor(PLATFORM_DEPLOYS.find((p) => p.platform === 'jd')!).every((r) => !r.scenario)).toBe(true);
    expect(newStoreId('douyin', ' 小店 ')).toBe('douyin-小店');
  });
});

describe('FastDeployPanel', () => {
  it('creates a new store and deploys 客服 into it', async () => {
    render(<FastDeployPanel open onClose={() => {}} />);
    await waitFor(() => expect(getStoreCatalog).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId('fd-platform-douyin'));

    // store list: this platform's stores, then "new store"
    openSelect('fd-store');
    await pickOption('＋ pages.agents.fast_deploy_store_new');
    expect(document.body.textContent).not.toContain('别家');
    fireEvent.change(screen.getByTestId('fd-store-name'), { target: { value: '小店' } });
    expect(screen.getByText('pages.agents.fast_deploy_store_id:douyin-小店')).toBeInTheDocument();

    // 客服 is preselected; add it and its options appear
    fireEvent.click(screen.getByTestId('fd-area-add'));
    const cs = screen.getByTestId('fd-area-cs');
    expect(within(cs).getByText('pages.agents.fast_deploy_qa_agents')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('fd-generate'));
    await waitFor(() => expect(executeRequest).toHaveBeenCalledTimes(1));
    const [method, payload] = executeRequest.mock.calls[0];
    expect(method).toBe('fast_deploy.generate');
    expect(payload).toEqual({ scenario: 'douyin_cs', config: {
      store_id: 'douyin-小店',
      new_store: { name: '小店', platform: 'douyin', urls: [] },
      qa_agents: 8, mode: 'add', fetch_catalog: true,   // on by default: export the store's products once
    } });
    await waitFor(() => expect(screen.getByText('pages.agents.fast_deploy_success')).toBeInTheDocument());
  });

  it('a custom platform creates just the store, under the typed platform', async () => {
    executeRequest.mockResolvedValue({ success: true, data: { status: 'success', store_created: true, log: ['created'] } });
    render(<FastDeployPanel open onClose={() => {}} />);
    await waitFor(() => expect(getStoreCatalog).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId('fd-platform-custom'));
    fireEvent.change(screen.getByTestId('fd-platform-name'), { target: { value: '微店' } });
    openSelect('fd-store');
    await pickOption('＋ pages.agents.fast_deploy_store_new');
    fireEvent.change(screen.getByTestId('fd-store-name'), { target: { value: '小铺' } });
    expect(screen.getByTestId('fd-area-add')).toBeDisabled();       // nothing deploys to 微店 yet
    fireEvent.click(screen.getByTestId('fd-generate'));
    await waitFor(() => expect(executeRequest).toHaveBeenCalledTimes(1));
    expect(executeRequest.mock.calls[0][0]).toBe('fast_deploy.create_store');
    expect(executeRequest.mock.calls[0][1]).toEqual({ store_id: '微店-小铺', name: '小铺', platform: '微店', urls: [] });
    await waitFor(() => expect(screen.getByText('pages.agents.fast_deploy_success')).toBeInTheDocument());
  });

  it('removing an area takes it out of the deploy; nothing added is refused', async () => {
    render(<FastDeployPanel open onClose={() => {}} />);
    await waitFor(() => expect(getStoreCatalog).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId('fd-platform-douyin'));
    openSelect('fd-store');
    await pickOption('老店 (douyin-老店)');
    expect((screen.getByTestId('fd-store-url') as HTMLInputElement).value).toBe('https://im.jinritemai.com/x');
    fireEvent.click(screen.getByTestId('fd-area-add'));
    fireEvent.click(screen.getByTestId('fd-area-del-cs'));
    expect(screen.queryByTestId('fd-area-cs')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('fd-generate'));
    await new Promise((r) => setTimeout(r, 0));
    expect(executeRequest).not.toHaveBeenCalled();
  });
});
