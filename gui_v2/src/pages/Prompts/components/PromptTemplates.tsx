import React from 'react';
import { Card, Typography, Space, Button, Tag, Collapse, Divider, Tooltip, message } from 'antd';
import {
  CopyOutlined,
  ShoppingOutlined,
  SearchOutlined,
  BarChartOutlined,
  FileTextOutlined,
  CodeOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

const { Title, Text } = Typography;

interface PromptTemplate {
  id: string;
  category: string;
  title: string;
  description: string;
  complexity: 'simple' | 'medium' | 'complex';
  steps: string;
  template: string;
  tags: string[];
  icon: React.ReactNode;
  annotations: {
    key: string;
    label: string;
    explanation: string;
  }[];
}

interface PromptTemplatesProps {
  onUseTemplate?: (template: PromptTemplate) => void;
}

const PromptTemplates: React.FC<PromptTemplatesProps> = ({ onUseTemplate }) => {
  const { t } = useTranslation();

  const templates: PromptTemplate[] = [
    {
      id: 'ecommerce-simple-search',
      category: 'E-commerce',
      title: t('pages.prompts.templates.ecommerceSimple.title', { 
        defaultValue: '电商简单搜索' 
      }),
      description: t('pages.prompts.templates.ecommerceSimple.desc', { 
        defaultValue: '在电商网站搜索商品并获取基本信息' 
      }),
      complexity: 'simple',
      steps: '3-5',
      tags: ['搜索', '基础', '电商'],
      icon: <SearchOutlined />,
      template: t('pages.prompts.templates.ecommerceSimple.template', { 
        defaultValue: `任务：在 {website} 搜索 '{product_name}'

步骤：
1. 访问 {website}
2. 在搜索框输入搜索词
3. 提取前 {count} 个结果

输出格式：
| 商品 | 价格 | 评分 |
|------|------|------|
| ...  | ...  | ...  |

验证点：
- ✓ 成功访问网站
- ✓ 搜索执行成功
- ✓ 商品详情已提取` 
      }),
      annotations: [
        {
          key: 'variables',
          label: '变量使用',
          explanation: '使用 {product_name}, {website}, {count} 等占位符，方便复用',
        },
        {
          key: 'steps',
          label: '步骤分解',
          explanation: '将任务分解为 3 个清晰的步骤，易于执行和验证',
        },
        {
          key: 'output',
          label: '输出格式',
          explanation: '使用表格格式，结构化展示结果',
        },
        {
          key: 'validation',
          label: '验证点',
          explanation: '明确列出成功标准，便于检查任务完成情况',
        },
      ],
    },
    {
      id: 'ecommerce-filter-compare',
      category: 'E-commerce',
      title: t('pages.prompts.templates.ecommerceFilter.title', { 
        defaultValue: '电商筛选对比' 
      }),
      description: t('pages.prompts.templates.ecommerceFilter.desc', { 
        defaultValue: '搜索并筛选商品，对比多个结果' 
      }),
      complexity: 'medium',
      steps: '5-8',
      tags: ['筛选', '对比', '中等'],
      icon: <BarChartOutlined />,
      template: t('pages.prompts.templates.ecommerceFilter.template', { 
        defaultValue: `任务：在 {website} 搜索并对比 {product_category}

筛选条件：
- 价格范围：{min_price} - {max_price}
- 品牌：{brand_list}
- 评分：{min_rating}+ 星
- 配送：{shipping_requirement}

步骤：
1. 访问 {website}
2. 搜索 '{product_category}'
3. 应用价格筛选
4. 应用品牌筛选
5. 应用评分筛选
6. 按 {sort_criteria} 排序
7. 提取前 {count} 个商品
8. 生成对比表格

输出格式：
| 商品 | 品牌 | 价格 | 评分 | 评论数 | 配送 |
|------|------|------|------|--------|------|
| ...  | ...  | ...  | ...  | ...    | ...  |

推荐：
基于对比结果，推荐最佳性价比选项并说明理由。

验证点：
- ✓ 所有筛选条件正确应用
- ✓ 提取了 {count} 个商品
- ✓ 生成了对比表格
- ✓ 提供了推荐` 
      }),
      annotations: [
        {
          key: 'filters',
          label: '筛选条件',
          explanation: '明确列出所有筛选条件，确保结果符合要求',
        },
        {
          key: 'steps',
          label: '详细步骤',
          explanation: '8 个步骤覆盖完整流程，包括筛选、排序、提取、分析',
        },
        {
          key: 'recommendation',
          label: '智能推荐',
          explanation: '要求 AI 基于数据提供推荐和理由，增加价值',
        },
      ],
    },
    {
      id: 'ecommerce-multi-store',
      category: 'E-commerce',
      title: t('pages.prompts.templates.ecommerceMulti.title', { 
        defaultValue: '跨店比价' 
      }),
      description: t('pages.prompts.templates.ecommerceMulti.desc', { 
        defaultValue: '访问多个店铺，对比价格和服务' 
      }),
      complexity: 'complex',
      steps: '8-12',
      tags: ['比价', '复杂', '多店铺'],
      icon: <ShoppingOutlined />,
      template: t('pages.prompts.templates.ecommerceMulti.template', { 
        defaultValue: `任务：在 {website} 对比 {store_count} 个不同店铺的 '{product_name}'

对比维度：
- 商品价格
- 店铺评分
- 月销量
- 评论数
- 好评率
- 发货地
- 是否包邮
- 退换政策

步骤：
1. 访问 {website}
2. 搜索 '{product_name}'
3. 点击第一个店铺的商品
4. 提取所有对比维度
5. 返回搜索结果
6. 点击第二个店铺的商品（不同卖家）
7. 提取所有对比维度
8. 对第三个店铺重复操作
9. 汇总对比数据
10. 计算每个店铺的价值评分
11. 生成详细对比表格
12. 提供推荐及理由

输出格式：
## 对比表格
| 店铺 | 价格 | 评分 | 销量 | 评论数 | 好评率 | 发货地 | 配送 | 退换 |
|------|------|------|------|--------|--------|--------|------|------|
| ...  | ...  | ...  | ...  | ...    | ...    | ...    | ...  | ...  |

## 价值分析
- 店铺1：[评分] - [理由]
- 店铺2：[评分] - [理由]
- 店铺3：[评分] - [理由]

## 推荐
最佳选择：[店铺名称]
理由：[综合考虑价格、质量、服务的详细说明]

错误处理：
- 如果店铺数据不足，跳过并尝试下一个
- 如果找到的店铺少于 {store_count} 个，报告实际数量
- 如果商品缺货，报告并建议替代品

验证点：
- ✓ 访问了 {store_count} 个不同店铺
- ✓ 提取了所有对比维度
- ✓ 生成了对比表格
- ✓ 提供了价值分析
- ✓ 给出了最终推荐` 
      }),
      annotations: [
        {
          key: 'dimensions',
          label: '对比维度',
          explanation: '列出 8 个关键对比维度，确保全面评估',
        },
        {
          key: 'steps',
          label: '复杂流程',
          explanation: '12 个步骤处理多店铺访问、数据提取、分析、推荐',
        },
        {
          key: 'error_handling',
          label: '错误处理',
          explanation: '预设异常情况处理方案，提高鲁棒性',
        },
        {
          key: 'analysis',
          label: '深度分析',
          explanation: '不仅对比数据，还要求价值分析和推荐理由',
        },
      ],
    },
    {
      id: 'content-generation',
      category: 'Content',
      title: t('pages.prompts.templates.contentGen.title', { 
        defaultValue: '内容生成' 
      }),
      description: t('pages.prompts.templates.contentGen.desc', { 
        defaultValue: '生成营销文案、邮件等内容' 
      }),
      complexity: 'simple',
      steps: '3-5',
      tags: ['内容', '营销', '文案'],
      icon: <FileTextOutlined />,
      template: t('pages.prompts.templates.contentGen.template', { 
        defaultValue: `角色：你是一位专业的营销文案撰写专家

任务：为 {product/service} 创作 {content_type}

目标受众：
- 人口统计：{age_group}，{location}
- 兴趣爱好：{interests}
- 痛点需求：{pain_points}

语气：{tone}（例如：专业、友好、紧迫）

要求：
- 长度：{word_count} 字
- 包含：{key_points}
- 行动号召：{cta}
- 避免：{avoid_list}

输出格式：
## 标题（如果是邮件）
[吸引人的标题]

## 正文内容
[内容主体]

## 行动号召
[清晰的 CTA]

指导原则：
- 使用有力的词汇和情感触发点
- 保持句子简短易读
- 如有可能包含社会证明
- 以明确的下一步行动结尾` 
      }),
      annotations: [
        {
          key: 'role',
          label: '角色定义',
          explanation: '明确 AI 的专业角色，提高输出质量',
        },
        {
          key: 'audience',
          label: '受众分析',
          explanation: '详细描述目标受众，确保内容针对性',
        },
        {
          key: 'requirements',
          label: '具体要求',
          explanation: '列出长度、要点、CTA 等明确要求',
        },
      ],
    },
    {
      id: 'code-generation',
      category: 'Development',
      title: t('pages.prompts.templates.codeGen.title', { 
        defaultValue: '代码生成' 
      }),
      description: t('pages.prompts.templates.codeGen.desc', { 
        defaultValue: '生成特定功能的代码' 
      }),
      complexity: 'medium',
      steps: '5-8',
      tags: ['代码', '开发', '技术'],
      icon: <CodeOutlined />,
      template: `Role: You are an expert {language} developer

Task: Create a {component_type} that {functionality}

Technical Requirements:
- Language: {language}
- Framework: {framework}
- Dependencies: {dependencies}
- Performance: {performance_requirements}
- Error handling: {error_handling_level}

Specifications:
- Input: {input_format}
- Output: {output_format}
- Edge cases: {edge_cases}
- Validation: {validation_rules}

Code Style:
- Follow {style_guide} conventions
- Include type annotations
- Add inline comments for complex logic
- Use meaningful variable names

Output Format:
\`\`\`{language}
// Code implementation
\`\`\`

## Usage Example
\`\`\`{language}
// Example usage
\`\`\`

## Test Cases
\`\`\`{language}
// Unit tests
\`\`\`

## Documentation
- Function purpose
- Parameters
- Return value
- Exceptions`,
      annotations: [
        {
          key: 'technical',
          label: '技术规格',
          explanation: '明确语言、框架、依赖等技术要求',
        },
        {
          key: 'specifications',
          label: '功能规格',
          explanation: '详细定义输入输出、边界情况、验证规则',
        },
        {
          key: 'complete',
          label: '完整输出',
          explanation: '要求代码、示例、测试、文档一应俱全',
        },
      ],
    },
  ];

  const complexityColors = {
    simple: 'green',
    medium: 'orange',
    complex: 'red',
  };

  const complexityLabels = {
    simple: t('pages.prompts.templates.complexity.simple', { defaultValue: '简单' }),
    medium: t('pages.prompts.templates.complexity.medium', { defaultValue: '中等' }),
    complex: t('pages.prompts.templates.complexity.complex', { defaultValue: '复杂' }),
  };

  const categories = Array.from(new Set(templates.map(t => t.category)));

  const copyTemplate = async (template: PromptTemplate) => {
    try {
      await navigator.clipboard.writeText(template.template);
      message.success(t('pages.prompts.templates.copied', { defaultValue: '模板已复制到剪贴板' }));
    } catch {
      message.error(t('pages.prompts.templates.copyFailed', { defaultValue: '复制失败' }));
    }
  };

  const handleUseTemplate = (template: PromptTemplate) => {
    if (onUseTemplate) {
      onUseTemplate(template);
    } else {
      copyTemplate(template);
    }
  };

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* Quick Action Banner */}
        <Card
          size="small"
          style={{ background: 'rgba(82,196,26,0.1)', border: '1px solid rgba(82,196,26,0.3)' }}
          styles={{ body: { padding: '12px 16px' } }}
        >
          <Typography.Text style={{ color: 'rgba(255,255,255,0.85)' }}>
            ⚡ {t('pages.prompts.templates.usageTip', { defaultValue: '点击"使用模板"按钮可将模板内容复制到编辑器' })}
          </Typography.Text>
        </Card>
        {/* Header */}
        <Card
          size="small"
          style={{ background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)', border: 'none' }}
          styles={{ body: { padding: 16 } }}
        >
          <Space direction="vertical" size={4}>
            <Title level={4} style={{ margin: 0, color: '#fff' }}>
              <ThunderboltOutlined /> {t('pages.prompts.templates.title', { defaultValue: '提示词模板库' })}
            </Title>
            <Text style={{ color: 'rgba(255,255,255,0.9)' }}>
              {t('pages.prompts.templates.subtitle', { 
                defaultValue: '精选优质模板，快速开始你的提示词设计' 
              })}
            </Text>
          </Space>
        </Card>

        {/* Templates by Category */}
        {categories.map((category) => (
          <Card
            key={category}
            size="small"
            title={
              <Text strong style={{ color: '#fff' }}>
                {category}
              </Text>
            }
            style={{ background: 'rgba(15,23,42,0.55)', border: '1px solid rgba(148,163,184,0.14)' }}
            styles={{ body: { padding: 16 } }}
          >
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              {templates
                .filter((t) => t.category === category)
                .map((template) => (
                  <Card
                    key={template.id}
                    size="small"
                    style={{ background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(148,163,184,0.1)' }}
                    styles={{ body: { padding: 16 } }}
                  >
                    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                      {/* Template Header */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                        <Space direction="vertical" size={4}>
                          <Space>
                            {template.icon}
                            <Text strong style={{ color: '#fff', fontSize: 16 }}>
                              {template.title}
                            </Text>
                          </Space>
                          <Text style={{ color: 'rgba(255,255,255,0.65)' }}>
                            {template.description}
                          </Text>
                          <Space size={4} wrap>
                            <Tag color={complexityColors[template.complexity]}>
                              {complexityLabels[template.complexity]}
                            </Tag>
                            <Tag>{template.steps} {t('pages.prompts.templates.steps', { defaultValue: '步' })}</Tag>
                            {template.tags.map((tag) => (
                              <Tag key={tag} color="blue">
                                {tag}
                              </Tag>
                            ))}
                          </Space>
                        </Space>
                        <Space>
                          <Tooltip title={t('pages.prompts.templates.copy', { defaultValue: '复制模板' })}>
                            <Button
                              type="text"
                              icon={<CopyOutlined />}
                              onClick={() => copyTemplate(template)}
                            />
                          </Tooltip>
                          <Button
                            type="primary"
                            size="small"
                            onClick={() => handleUseTemplate(template)}
                          >
                            {t('pages.prompts.templates.use', { defaultValue: '使用模板' })}
                          </Button>
                        </Space>
                      </div>

                      <Divider style={{ margin: 0, borderColor: 'rgba(148,163,184,0.1)' }} />

                      {/* Template Content */}
                      <Collapse
                        ghost
                        items={[
                          {
                            key: 'template',
                            label: (
                              <Text strong style={{ color: '#fff' }}>
                                {t('pages.prompts.templates.viewTemplate', { defaultValue: '查看模板' })}
                              </Text>
                            ),
                            children: (
                              <Card
                                size="small"
                                style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(148,163,184,0.1)' }}
                                styles={{ body: { padding: 12 } }}
                              >
                                <pre
                                  style={{
                                    margin: 0,
                                    color: '#a5f3fc',
                                    fontFamily: 'monospace',
                                    fontSize: 13,
                                    whiteSpace: 'pre-wrap',
                                    wordBreak: 'break-word',
                                  }}
                                >
                                  {template.template}
                                </pre>
                              </Card>
                            ),
                          },
                          {
                            key: 'annotations',
                            label: (
                              <Text strong style={{ color: '#fff' }}>
                                {t('pages.prompts.templates.keyPoints', { defaultValue: '要点解析' })}
                              </Text>
                            ),
                            children: (
                              <Space direction="vertical" size="small" style={{ width: '100%' }}>
                                {template.annotations.map((annotation, idx) => (
                                  <div key={annotation.key}>
                                    <Space direction="vertical" size={4}>
                                      <Tag color="cyan">{annotation.label}</Tag>
                                      <Text style={{ color: 'rgba(255,255,255,0.75)' }}>
                                        {annotation.explanation}
                                      </Text>
                                    </Space>
                                    {idx !== template.annotations.length - 1 && (
                                      <Divider style={{ margin: '8px 0', borderColor: 'rgba(148,163,184,0.1)' }} />
                                    )}
                                  </div>
                                ))}
                              </Space>
                            ),
                          },
                        ]}
                      />
                    </Space>
                  </Card>
                ))}
            </Space>
          </Card>
        ))}
      </Space>
  );
};

export default PromptTemplates;
