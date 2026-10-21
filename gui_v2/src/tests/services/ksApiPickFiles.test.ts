// fs.selectFiles answers a single pick as { path } and a multiple one as { paths }.
// ksApi.pickFiles read only `paths`, so every single-file pick looked cancelled and
// the product-table import did nothing (alpha 2026-10-21).
const executeRequest = jest.fn();
jest.mock('@/services/ipc_api', () => ({ get_ipc_api: () => ({ executeRequest }) }));

import { ksApi } from '@/services/ipc/ksApi';

describe('ksApi.pickFiles', () => {
  beforeEach(() => executeRequest.mockReset());

  it('returns the one file of a single-file pick', async () => {
    executeRequest.mockResolvedValue({ success: true, data: { path: 'C:/x/商品资料导入模板.xlsx' } });
    await expect(ksApi.pickFiles(['xlsx'], 'Product lists', false)).resolves.toEqual(['C:/x/商品资料导入模板.xlsx']);
  });

  it('returns every file of a multiple pick', async () => {
    executeRequest.mockResolvedValue({ success: true, data: { paths: ['a.pdf', 'b.pdf'] } });
    await expect(ksApi.pickFiles(['pdf'], 'Docs', true)).resolves.toEqual(['a.pdf', 'b.pdf']);
  });

  it('returns nothing when the dialog was cancelled', async () => {
    executeRequest.mockResolvedValue({ success: true, data: { path: '', cancelled: true } });
    await expect(ksApi.pickFiles(['xlsx'], 'Product lists', false)).resolves.toEqual([]);
  });
});
