import { describe, expect, it } from 'vitest';
import { formatAgentText } from './agentText';

describe('formatAgentText', () => {
  it('removes raw markdown emphasis and strips markdown bullet markers for operator readability', () => {
    expect(formatAgentText('当前项目 **33**\n- **Series 57** - `task_fMRI_BOLD`')).toBe(
      '当前项目 33\nSeries 57 - task_fMRI_BOLD',
    );
  });
});
