import { platformLabel, platformValue } from './scenarios';

describe('platformValue', () => {
  it('maps a known platform key or name to its key', () => {
    expect(platformValue('天猫')).toBe('tmall');
    expect(platformValue('T-Mall')).toBe('tmall');
    expect(platformValue(' tmall ')).toBe('tmall');
    expect(platformValue('拼多多')).toBe('pinduoduo');
  });
  it('keeps a custom platform as typed', () => {
    expect(platformValue('我的平台')).toBe('我的平台');
    expect(platformValue('')).toBe('');
  });
  it('labels a store saved under the name like one saved under the key', () => {
    expect(platformLabel('天猫', 'zh-CN')).toBe('天猫');
    expect(platformLabel('天猫', 'en-US')).toBe('T-Mall');
  });
});
