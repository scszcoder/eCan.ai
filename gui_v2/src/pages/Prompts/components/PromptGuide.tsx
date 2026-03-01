import React from 'react';
import { Card, Collapse, Typography, Tag, Space, Divider, Alert } from 'antd';
import {
  BulbOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  InfoCircleOutlined,
  ThunderboltOutlined,
  StarOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

const { Title, Text, Paragraph } = Typography;

interface PromptGuideProps {
  visible?: boolean;
}

const PromptGuide: React.FC<PromptGuideProps> = ({ visible = true }) => {
  const { t } = useTranslation();

  if (!visible) return null;

  const principles = [
    {
      key: 'clarity',
      icon: <CheckCircleOutlined style={{ color: '#52c41a' }} />,
      title: t('pages.prompts.guide.principles.clarity.title', { defaultValue: '明确性 - 清晰的目标和步骤' }),
      good: t('pages.prompts.guide.principles.clarity.good', { 
        defaultValue: '在 Amazon 搜索 "laptop"，找到价格低于 $1000 的第一个商品' 
      }),
      bad: t('pages.prompts.guide.principles.clarity.bad', { defaultValue: '帮我找个便宜的笔记本' }),
      tip: t('pages.prompts.guide.principles.clarity.tip', { 
        defaultValue: '使用具体的数字、品牌、价格范围等明确条件' 
      }),
    },
    {
      key: 'verifiable',
      icon: <CheckCircleOutlined style={{ color: '#52c41a' }} />,
      title: t('pages.prompts.guide.principles.verifiable.title', { defaultValue: '可验证性 - 包含明确的验证点' }),
      good: t('pages.prompts.guide.principles.verifiable.good', { 
        defaultValue: '获取前 3 个商品的标题、价格和评分' 
      }),
      bad: t('pages.prompts.guide.principles.verifiable.bad', { defaultValue: '看看有什么好的商品' }),
      tip: t('pages.prompts.guide.principles.verifiable.tip', { 
        defaultValue: '明确需要提取的数据字段和数量' 
      }),
    },
    {
      key: 'structured',
      icon: <CheckCircleOutlined style={{ color: '#52c41a' }} />,
      title: t('pages.prompts.guide.principles.structured.title', { defaultValue: '结构化 - 使用清晰的格式' }),
      good: t('pages.prompts.guide.principles.structured.good', { 
        defaultValue: 'Task: 搜索\nFilters: 价格 $500-$1000\nOutput: 表格格式' 
      }),
      bad: t('pages.prompts.guide.principles.structured.bad', { 
        defaultValue: '找个500到1000的东西，用表格显示' 
      }),
      tip: t('pages.prompts.guide.principles.structured.tip', { 
        defaultValue: '使用标签、列表、表格等结构化格式' 
      }),
    },
    {
      key: 'scoped',
      icon: <InfoCircleOutlined style={{ color: '#1890ff' }} />,
      title: t('pages.prompts.guide.principles.scoped.title', { defaultValue: '步骤限制 - 控制复杂度' }),
      good: t('pages.prompts.guide.principles.scoped.good', { 
        defaultValue: '简单任务: 3-5步 | 中等: 5-8步 | 复杂: 8-12步' 
      }),
      bad: t('pages.prompts.guide.principles.scoped.bad', { 
        defaultValue: '做一个完整的市场调研报告（无限步骤）' 
      }),
      tip: t('pages.prompts.guide.principles.scoped.tip', { 
        defaultValue: '将复杂任务分解为多个简单任务' 
      }),
    },
  ];

  const techniques = [
    {
      key: 'role',
      title: t('pages.prompts.guide.techniques.role.title', { defaultValue: '1. 角色定义' }),
      description: t('pages.prompts.guide.techniques.role.desc', { 
        defaultValue: '明确 AI 的角色和专业领域' 
      }),
      example: t('pages.prompts.guide.techniques.role.example', { 
        defaultValue: '你是一位专业的电商分析师，擅长产品对比分析。' 
      }),
    },
    {
      key: 'context',
      title: t('pages.prompts.guide.techniques.context.title', { defaultValue: '2. 背景信息' }),
      description: t('pages.prompts.guide.techniques.context.desc', { 
        defaultValue: '提供必要的上下文和约束条件' 
      }),
      example: t('pages.prompts.guide.techniques.context.example', { 
        defaultValue: '背景：用户是大学生，预算有限，需要购买游戏笔记本。' 
      }),
    },
    {
      key: 'task',
      title: t('pages.prompts.guide.techniques.task.title', { defaultValue: '3. 任务描述' }),
      description: t('pages.prompts.guide.techniques.task.desc', { 
        defaultValue: '清晰描述要完成的具体任务' 
      }),
      example: t('pages.prompts.guide.techniques.task.example', { 
        defaultValue: '任务：在 Amazon 搜索游戏笔记本，价格筛选 $800-$1500，对比前 3 款。' 
      }),
    },
    {
      key: 'format',
      title: t('pages.prompts.guide.techniques.format.title', { defaultValue: '4. 输出格式' }),
      description: t('pages.prompts.guide.techniques.format.desc', { 
        defaultValue: '指定期望的输出格式和结构' 
      }),
      example: t('pages.prompts.guide.techniques.format.example', { 
        defaultValue: '输出：Markdown 表格，包含列：产品、价格、CPU、内存、评分。' 
      }),
    },
    {
      key: 'examples',
      title: t('pages.prompts.guide.techniques.examples.title', { defaultValue: '5. 示例说明' }),
      description: t('pages.prompts.guide.techniques.examples.desc', { 
        defaultValue: '提供期望输出的具体示例' 
      }),
      example: t('pages.prompts.guide.techniques.examples.example', { 
        defaultValue: '示例：\n| 产品 | 价格 | CPU | 内存 |\n| ASUS ROG | $1299 | i7-12700H | 16GB |' 
      }),
    },
    {
      key: 'constraints',
      title: t('pages.prompts.guide.techniques.constraints.title', { defaultValue: '6. 约束条件' }),
      description: t('pages.prompts.guide.techniques.constraints.desc', { 
        defaultValue: '明确限制和边界条件' 
      }),
      example: t('pages.prompts.guide.techniques.constraints.example', { 
        defaultValue: '约束：最多 3 个产品，仅限 4 星以上卖家，仅限免费配送。' 
      }),
    },
  ];

  const commonMistakes = [
    {
      mistake: t('pages.prompts.guide.mistakes.vague', { defaultValue: '过于模糊的描述' }),
      fix: t('pages.prompts.guide.mistakes.vagueFix', { defaultValue: '使用具体的数字、品牌、条件' }),
    },
    {
      mistake: t('pages.prompts.guide.mistakes.noFormat', { defaultValue: '未指定输出格式' }),
      fix: t('pages.prompts.guide.mistakes.noFormatFix', { defaultValue: '明确要求表格、JSON、列表等格式' }),
    },
    {
      mistake: t('pages.prompts.guide.mistakes.tooComplex', { defaultValue: '任务过于复杂' }),
      fix: t('pages.prompts.guide.mistakes.tooComplexFix', { defaultValue: '分解为多个简单步骤' }),
    },
    {
      mistake: t('pages.prompts.guide.mistakes.noValidation', { defaultValue: '缺少验证点' }),
      fix: t('pages.prompts.guide.mistakes.noValidationFix', { defaultValue: '添加明确的成功标准' }),
    },
  ];

  return (
    <div style={{
      height: '100%',
      overflow: 'auto',
      padding: '16px 20px',
      background: '#0f172a',
      overflowY: 'scroll'
    }}>
      <Space direction="vertical" size="large" style={{ width: '100%', paddingBottom: '40px' }}>
        {/* Quick Action Banner */}
        <Card
          size="small"
          style={{ background: 'rgba(24,144,255,0.1)', border: '1px solid rgba(24,144,255,0.3)' }}
          styles={{ body: { padding: '12px 16px' } }}
        >
          <Text style={{ color: 'rgba(255,255,255,0.85)' }}>
            💡 {t('pages.prompts.guide.learnTip', { defaultValue: '学习完设计原则后，可以使用模板快速开始' })}
          </Text>
        </Card>
        {/* Header */}
        <Card
          size="small"
          style={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', border: 'none' }}
          styles={{ body: { padding: 16 } }}
        >
          <Space direction="vertical" size={4}>
            <Title level={4} style={{ margin: 0, color: '#fff' }}>
              <BulbOutlined /> {t('pages.prompts.guide.title', { defaultValue: '提示词设计指南' })}
            </Title>
            <Text style={{ color: 'rgba(255,255,255,0.9)' }}>
              {t('pages.prompts.guide.subtitle', { 
                defaultValue: '掌握提示词设计的核心原则和最佳实践' 
              })}
            </Text>
          </Space>
        </Card>

        {/* Design Principles */}
        <Card
          size="small"
          title={
            <Space>
              <StarOutlined style={{ color: '#faad14' }} />
              <Text strong style={{ color: '#fff' }}>
                {t('pages.prompts.guide.principlesTitle', { defaultValue: '核心设计原则' })}
              </Text>
            </Space>
          }
          style={{ background: 'rgba(15,23,42,0.55)', border: '1px solid rgba(148,163,184,0.14)' }}
          styles={{ body: { padding: 16 } }}
        >
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            {principles.map((principle) => (
              <div key={principle.key}>
                <Space align="start" style={{ width: '100%' }}>
                  {principle.icon}
                  <div style={{ flex: 1 }}>
                    <Text strong style={{ color: '#fff', display: 'block', marginBottom: 8 }}>
                      {principle.title}
                    </Text>
                    <div style={{ marginLeft: 0, marginBottom: 8 }}>
                      <Space direction="vertical" size={4} style={{ width: '100%' }}>
                        <div>
                          <Tag color="success" icon={<CheckCircleOutlined />}>
                            {t('pages.prompts.guide.good', { defaultValue: '好' })}
                          </Tag>
                          <Text style={{ color: 'rgba(255,255,255,0.85)' }}>{principle.good}</Text>
                        </div>
                        <div>
                          <Tag color="error" icon={<CloseCircleOutlined />}>
                            {t('pages.prompts.guide.bad', { defaultValue: '差' })}
                          </Tag>
                          <Text style={{ color: 'rgba(255,255,255,0.65)' }}>{principle.bad}</Text>
                        </div>
                      </Space>
                    </div>
                    <Alert
                      message={principle.tip}
                      type="info"
                      showIcon
                      style={{ background: 'rgba(24,144,255,0.1)', border: '1px solid rgba(24,144,255,0.2)' }}
                    />
                  </div>
                </Space>
                {principle.key !== principles[principles.length - 1].key && (
                  <Divider style={{ margin: '12px 0', borderColor: 'rgba(148,163,184,0.1)' }} />
                )}
              </div>
            ))}
          </Space>
        </Card>

        {/* Writing Techniques */}
        <Card
          size="small"
          title={
            <Space>
              <ThunderboltOutlined style={{ color: '#1890ff' }} />
              <Text strong style={{ color: '#fff' }}>
                {t('pages.prompts.guide.techniquesTitle', { defaultValue: '编写技巧' })}
              </Text>
            </Space>
          }
          style={{ background: 'rgba(15,23,42,0.55)', border: '1px solid rgba(148,163,184,0.14)' }}
          styles={{ body: { padding: 16 } }}
        >
          <Collapse
            ghost
            items={techniques.map((tech) => ({
              key: tech.key,
              label: (
                <Text strong style={{ color: '#fff' }}>
                  {tech.title}
                </Text>
              ),
              children: (
                <Space direction="vertical" size="small" style={{ width: '100%' }}>
                  <Paragraph style={{ color: 'rgba(255,255,255,0.75)', margin: 0 }}>
                    {tech.description}
                  </Paragraph>
                  <Card
                    size="small"
                    style={{ background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(148,163,184,0.1)' }}
                    styles={{ body: { padding: 12 } }}
                  >
                    <pre style={{ margin: 0, color: '#a5f3fc', fontFamily: 'monospace', fontSize: 13 }}>
                      {tech.example}
                    </pre>
                  </Card>
                </Space>
              ),
            }))}
          />
        </Card>

        {/* Common Mistakes */}
        <Card
          size="small"
          title={
            <Space>
              <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
              <Text strong style={{ color: '#fff' }}>
                {t('pages.prompts.guide.mistakesTitle', { defaultValue: '常见错误与修正' })}
              </Text>
            </Space>
          }
          style={{ background: 'rgba(15,23,42,0.55)', border: '1px solid rgba(148,163,184,0.14)' }}
          styles={{ body: { padding: 16 } }}
        >
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            {commonMistakes.map((item, idx) => (
              <div key={idx}>
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  <div>
                    <CloseCircleOutlined style={{ color: '#ff4d4f', marginRight: 8 }} />
                    <Text delete style={{ color: 'rgba(255,255,255,0.65)' }}>
                      {item.mistake}
                    </Text>
                  </div>
                  <div style={{ marginLeft: 24 }}>
                    <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 8 }} />
                    <Text strong style={{ color: '#52c41a' }}>
                      {item.fix}
                    </Text>
                  </div>
                </Space>
                {idx !== commonMistakes.length - 1 && (
                  <Divider style={{ margin: '12px 0', borderColor: 'rgba(148,163,184,0.1)' }} />
                )}
              </div>
            ))}
          </Space>
        </Card>
      </Space>
    </div>
  );
};

export default PromptGuide;
