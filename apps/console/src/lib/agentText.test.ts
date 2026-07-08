import { describe, expect, it } from 'vitest';
import { formatAgentText } from './agentText';

describe('formatAgentText', () => {
  it('removes raw markdown emphasis and strips markdown bullet markers for operator readability', () => {
    expect(formatAgentText('当前项目 **33**\n- **Series 57** - `task_fMRI_BOLD`')).toBe(
      '当前项目 33\nSeries 57 - task_fMRI_BOLD',
    );
  });

  it('turns model-style markdown lists and headings into plain readable chat text', () => {
    expect(
      formatAgentText(
        [
          '### **项目33当前状态概要：**',
          '',
          '- **数据情况**：1个T1序列（`MPRAGE`），已检测。',
          '- **处理完成**：DeepPrep T1解剖处理。',
          '1. **建议**：查看 `reports/index.html`。',
          '',
          '',
          '请问有什么可以帮您的？',
        ].join('\n'),
      ),
    ).toBe(
      [
        '项目33当前状态概要：',
        '',
        '数据情况：1个T1序列（MPRAGE），已检测。',
        '处理完成：DeepPrep T1解剖处理。',
        '建议：查看 reports/index.html。',
        '',
        '请问有什么可以帮您的？',
      ].join('\n'),
    );
  });
});
