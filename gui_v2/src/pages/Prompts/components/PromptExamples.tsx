import React, { useState, useEffect } from 'react';
import { Card, Typography, Space, Tag, Divider, Collapse, Tabs, Spin, Alert } from 'antd';
import {
  CheckCircleOutlined,
  ThunderboltOutlined,
  StarOutlined,
  ShoppingOutlined,
  FileTextOutlined,
  CodeOutlined,
  BookOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import ReactMarkdown from 'react-markdown';

const { Title, Text, Paragraph } = Typography;

interface Example {
  id: string;
  category: string;
  title: string;
  description: string;
  level: 'beginner' | 'intermediate' | 'advanced';
  icon: React.ReactNode;
  prompt: string;
  highlights: string[];
  results: string;
}

const PromptExamples: React.FC = () => {
  const { t } = useTranslation();
  const [markdownContent, setMarkdownContent] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadMarkdown = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch('/tests/ECOMMERCE_TEST_PROMPTS.md');
        if (!response.ok) {
          throw new Error('Failed to load documentation');
        }
        const text = await response.text();
        setMarkdownContent(text);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };
    loadMarkdown();
  }, []);

  const examples: Example[] = [
    {
      id: 'ecommerce-basic',
      category: t('pages.prompts.examples.categories.ecommerce', { defaultValue: '电商场景' }),
      title: t('pages.prompts.examples.ecommerceBasic.title', { 
        defaultValue: '基础商品搜索' 
      }),
      description: t('pages.prompts.examples.ecommerceBasic.desc', { 
        defaultValue: '在电商网站搜索特定商品并提取关键信息' 
      }),
      level: 'beginner',
      icon: <ShoppingOutlined />,
      prompt: t('pages.prompts.examples.ecommerceBasic.prompt', { 
        defaultValue: `任务：在 Amazon 搜索 "无线鼠标"

步骤：
1. 打开 Amazon 首页
2. 在搜索框输入 "无线鼠标"
3. 点击搜索按钮
4. 提取前 5 个商品的以下信息：
   - 商品名称
   - 价格
   - 评分
   - 评论数

输出格式：
| 商品名称 | 价格 | 评分 | 评论数 |
|---------|------|------|--------|

验证点：
✓ 成功打开网站
✓ 搜索执行成功
✓ 提取到 5 个商品信息
✓ 所有字段完整` 
      }),
      highlights: [
        t('pages.prompts.examples.ecommerceBasic.highlight1', { 
          defaultValue: '明确的步骤分解（4步）' 
        }),
        t('pages.prompts.examples.ecommerceBasic.highlight2', { 
          defaultValue: '清晰的数据字段定义' 
        }),
        t('pages.prompts.examples.ecommerceBasic.highlight3', { 
          defaultValue: '表格化输出格式' 
        }),
        t('pages.prompts.examples.ecommerceBasic.highlight4', { 
          defaultValue: '完整的验证清单' 
        }),
      ],
      results: t('pages.prompts.examples.ecommerceBasic.results', { 
        defaultValue: '成功率: 95% | 平均耗时: 15秒 | 数据完整性: 98%' 
      }),
    },
    {
      id: 'ecommerce-advanced',
      category: t('pages.prompts.examples.categories.ecommerce', { defaultValue: '电商场景' }),
      title: t('pages.prompts.examples.ecommerceAdvanced.title', { 
        defaultValue: '多条件筛选对比' 
      }),
      description: t('pages.prompts.examples.ecommerceAdvanced.desc', { 
        defaultValue: '使用多个筛选条件，对比不同商品' 
      }),
      level: 'intermediate',
      icon: <ShoppingOutlined />,
      prompt: t('pages.prompts.examples.ecommerceAdvanced.prompt', { 
        defaultValue: `任务：在 Amazon 对比游戏笔记本

筛选条件：
- 价格范围：$800 - $1500
- 品牌：ASUS, MSI, Lenovo
- 最低评分：4.0 星
- 配送：仅限免费配送

步骤：
1. 访问 Amazon
2. 搜索 "gaming laptop"
3. 应用价格筛选器
4. 应用品牌筛选器
5. 应用评分筛选器
6. 应用配送筛选器
7. 按 "最佳评价" 排序
8. 提取前 3 个商品的详细信息

输出格式：
| 商品 | 价格 | CPU | 内存 | 显卡 | 评分 | 评论数 |
|------|------|-----|------|------|------|--------|

对比分析：
- 性价比最高：[商品名]
- 配置最强：[商品名]
- 用户评价最好：[商品名]

验证点：
✓ 所有筛选条件已应用
✓ 提取到 3 个商品
✓ 包含完整的对比分析` 
      }),
      highlights: [
        t('pages.prompts.examples.ecommerceAdvanced.highlight1', { 
          defaultValue: '多维度筛选条件' 
        }),
        t('pages.prompts.examples.ecommerceAdvanced.highlight2', { 
          defaultValue: '详细的产品规格提取' 
        }),
        t('pages.prompts.examples.ecommerceAdvanced.highlight3', { 
          defaultValue: '智能对比分析' 
        }),
        t('pages.prompts.examples.ecommerceAdvanced.highlight4', { 
          defaultValue: '结构化验证流程' 
        }),
      ],
      results: t('pages.prompts.examples.ecommerceAdvanced.results', { 
        defaultValue: '成功率: 88% | 平均耗时: 35秒 | 筛选准确性: 92%' 
      }),
    },
    {
      id: 'content-generation',
      category: t('pages.prompts.examples.categories.content', { defaultValue: '内容生成' }),
      title: t('pages.prompts.examples.contentGen.title', { 
        defaultValue: '营销邮件生成' 
      }),
      description: t('pages.prompts.examples.contentGen.desc', { 
        defaultValue: '生成专业的营销邮件内容' 
      }),
      level: 'beginner',
      icon: <FileTextOutlined />,
      prompt: t('pages.prompts.examples.contentGen.prompt', { 
        defaultValue: `角色：你是一位专业的营销文案撰写专家

任务：为新产品发布撰写营销邮件

产品信息：
- 产品名称：智能降噪耳机 Pro
- 核心功能：主动降噪、40小时续航、快速充电
- 目标受众：25-40岁职场人士
- 优惠活动：限时8折优惠

要求：
1. 邮件标题：吸引人，不超过50字
2. 正文内容：
   - 开头：引起兴趣
   - 中间：介绍产品核心优势（3个要点）
   - 结尾：明确的行动号召（CTA）
3. 语气：专业但友好
4. 长度：150-200字

约束：
- 不使用夸张或虚假宣传
- 避免垃圾邮件常用词
- 包含优惠信息

输出格式：
【邮件标题】
[标题内容]

【邮件正文】
[正文内容]` 
      }),
      highlights: [
        t('pages.prompts.examples.contentGen.highlight1', { 
          defaultValue: '明确的角色定义' 
        }),
        t('pages.prompts.examples.contentGen.highlight2', { 
          defaultValue: '详细的产品信息' 
        }),
        t('pages.prompts.examples.contentGen.highlight3', { 
          defaultValue: '结构化的内容要求' 
        }),
        t('pages.prompts.examples.contentGen.highlight4', { 
          defaultValue: '清晰的约束条件' 
        }),
      ],
      results: t('pages.prompts.examples.contentGen.results', { 
        defaultValue: '质量评分: 4.5/5.0 | 用户满意度: 90% | 转化率提升: 25%' 
      }),
    },
    {
      id: 'code-generation',
      category: t('pages.prompts.examples.categories.code', { defaultValue: '代码生成' }),
      title: t('pages.prompts.examples.codeGen.title', { 
        defaultValue: 'API 接口生成' 
      }),
      description: t('pages.prompts.examples.codeGen.desc', { 
        defaultValue: '生成 RESTful API 接口代码' 
      }),
      level: 'intermediate',
      icon: <CodeOutlined />,
      prompt: t('pages.prompts.examples.codeGen.prompt', { 
        defaultValue: `任务：生成用户管理 RESTful API

技术栈：
- 语言：Python
- 框架：FastAPI
- 数据库：PostgreSQL
- ORM：SQLAlchemy

功能需求：
1. 用户注册（POST /api/users/register）
2. 用户登录（POST /api/users/login）
3. 获取用户信息（GET /api/users/{user_id}）
4. 更新用户信息（PUT /api/users/{user_id}）

代码要求：
- 包含完整的类型注解
- 添加输入验证
- 包含错误处理
- 添加必要的注释
- 遵循 PEP 8 规范

输出格式：
1. 数据模型定义
2. API 路由实现
3. 请求/响应示例

示例：
\`\`\`python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

class User(BaseModel):
    username: str
    email: str
    ...
\`\`\`` 
      }),
      highlights: [
        t('pages.prompts.examples.codeGen.highlight1', { 
          defaultValue: '完整的技术栈说明' 
        }),
        t('pages.prompts.examples.codeGen.highlight2', { 
          defaultValue: '详细的功能需求' 
        }),
        t('pages.prompts.examples.codeGen.highlight3', { 
          defaultValue: '明确的代码规范' 
        }),
        t('pages.prompts.examples.codeGen.highlight4', { 
          defaultValue: '提供代码示例' 
        }),
      ],
      results: t('pages.prompts.examples.codeGen.results', { 
        defaultValue: '代码质量: A级 | 可运行性: 95% | 规范符合度: 98%' 
      }),
    },
  ];

  const getLevelColor = (level: string) => {
    switch (level) {
      case 'beginner':
        return '#52c41a';
      case 'intermediate':
        return '#faad14';
      case 'advanced':
        return '#ff4d4f';
      default:
        return '#1890ff';
    }
  };

  const getLevelText = (level: string) => {
    switch (level) {
      case 'beginner':
        return t('pages.prompts.examples.levels.beginner', { defaultValue: '初级' });
      case 'intermediate':
        return t('pages.prompts.examples.levels.intermediate', { defaultValue: '中级' });
      case 'advanced':
        return t('pages.prompts.examples.levels.advanced', { defaultValue: '高级' });
      default:
        return level;
    }
  };

  const groupedExamples = examples.reduce((acc, example) => {
    if (!acc[example.category]) {
      acc[example.category] = [];
    }
    acc[example.category].push(example);
    return acc;
  }, {} as Record<string, Example[]>);

  const tabItems = [
    {
      key: 'builtin',
      label: (
        <Space>
          <StarOutlined />
          {t('pages.prompts.examples.tabs.builtin', { defaultValue: '内置示例' })}
        </Space>
      ),
      children: (
        <div style={{ height: '100%', overflow: 'auto', overflowY: 'scroll', paddingBottom: '40px' }}>
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <Card
            size="small"
            style={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', border: 'none' }}
            styles={{ body: { padding: 16 } }}
          >
            <Space direction="vertical" size={4}>
              <Title level={4} style={{ margin: 0, color: '#fff' }}>
                <StarOutlined /> {t('pages.prompts.examples.title', { defaultValue: '优秀提示词示例' })}
              </Title>
              <Text style={{ color: 'rgba(255,255,255,0.85)', fontSize: 13 }}>
                {t('pages.prompts.examples.subtitle', { 
                  defaultValue: '学习实战案例，掌握提示词设计精髓' 
                })}
              </Text>
            </Space>
          </Card>

          {/* Examples by Category */}
          {Object.entries(groupedExamples).map(([category, categoryExamples]) => (
          <div key={category}>
            <Title level={5} style={{ color: '#fff', marginBottom: 16 }}>
              {category}
            </Title>
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              {categoryExamples.map((example) => (
                <Card
                  key={example.id}
                  size="small"
                  style={{ background: 'rgba(15,23,42,0.55)', border: '1px solid rgba(148,163,184,0.14)' }}
                  styles={{ body: { padding: 16 } }}
                >
                  <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    {/* Title and Level */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Space>
                        {example.icon}
                        <Text strong style={{ color: '#fff', fontSize: 16 }}>
                          {example.title}
                        </Text>
                      </Space>
                      <Tag color={getLevelColor(example.level)}>
                        {getLevelText(example.level)}
                      </Tag>
                    </div>

                    {/* Description */}
                    <Paragraph style={{ color: 'rgba(255,255,255,0.75)', margin: 0 }}>
                      {example.description}
                    </Paragraph>

                    <Divider style={{ margin: '8px 0', borderColor: 'rgba(148,163,184,0.14)' }} />

                    {/* Prompt Content */}
                    <Collapse
                      ghost
                      items={[
                        {
                          key: 'prompt',
                          label: (
                            <Text strong style={{ color: '#1890ff' }}>
                              <ThunderboltOutlined /> {t('pages.prompts.examples.viewPrompt', { 
                                defaultValue: '查看完整提示词' 
                              })}
                            </Text>
                          ),
                          children: (
                            <Card
                              size="small"
                              style={{ background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(148,163,184,0.1)' }}
                              styles={{ body: { padding: 12 } }}
                            >
                              <pre style={{ 
                                color: 'rgba(255,255,255,0.85)', 
                                margin: 0, 
                                whiteSpace: 'pre-wrap',
                                fontFamily: 'monospace',
                                fontSize: 13,
                                lineHeight: 1.6,
                              }}>
                                {example.prompt}
                              </pre>
                            </Card>
                          ),
                        },
                      ]}
                    />

                    {/* Highlights */}
                    <div>
                      <Text strong style={{ color: '#fff', fontSize: 13 }}>
                        <CheckCircleOutlined style={{ color: '#52c41a' }} /> {t('pages.prompts.examples.highlights', { 
                          defaultValue: '设计亮点' 
                        })}:
                      </Text>
                      <div style={{ marginTop: 8 }}>
                        {example.highlights.map((highlight, idx) => (
                          <Tag key={idx} color="green" style={{ marginTop: 4 }}>
                            {highlight}
                          </Tag>
                        ))}
                      </div>
                    </div>

                    {/* Results */}
                    <Card
                      size="small"
                      style={{ background: 'rgba(82,196,26,0.1)', border: '1px solid rgba(82,196,26,0.3)' }}
                      styles={{ body: { padding: 8 } }}
                    >
                      <Text style={{ color: '#52c41a', fontSize: 12 }}>
                        📊 {t('pages.prompts.examples.performanceMetrics', { 
                          defaultValue: '性能指标' 
                        })}: {example.results}
                      </Text>
                    </Card>
                  </Space>
                </Card>
              ))}
            </Space>
          </div>
          ))}
          </Space>
        </div>
      ),
    },
    {
      key: 'documentation',
      label: (
        <Space>
          <BookOutlined />
          {t('pages.prompts.examples.tabs.documentation', { defaultValue: '完整文档' })}
        </Space>
      ),
      children: (
        <div style={{ width: '100%', height: '100%', overflow: 'auto', overflowY: 'scroll', paddingBottom: '40px' }}>
          {loading && (
            <div style={{ textAlign: 'center', padding: '40px' }}>
              <Spin size="large" />
              <div style={{ marginTop: 16, color: 'rgba(255,255,255,0.65)' }}>
                {t('pages.prompts.examples.loadingDoc', { defaultValue: '加载文档中...' })}
              </div>
            </div>
          )}
          {error && (
            <Alert
              message={t('pages.prompts.examples.loadError', { defaultValue: '加载失败' })}
              description={error}
              type="error"
              showIcon
            />
          )}
          {!loading && !error && markdownContent && (
            <Card
              size="small"
              style={{ background: 'rgba(15,23,42,0.55)', border: '1px solid rgba(148,163,184,0.14)' }}
              styles={{ body: { padding: 24 } }}
            >
              <div 
                className="markdown-content"
                style={{
                  color: 'rgba(255,255,255,0.85)',
                  lineHeight: 1.8,
                }}
              >
                <ReactMarkdown
                  components={{
                    h1: ({ children }) => (
                      <Title level={2} style={{ color: '#fff', marginTop: 24, marginBottom: 16 }}>
                        {children}
                      </Title>
                    ),
                    h2: ({ children }) => (
                      <Title level={3} style={{ color: '#fff', marginTop: 20, marginBottom: 12 }}>
                        {children}
                      </Title>
                    ),
                    h3: ({ children }) => (
                      <Title level={4} style={{ color: '#fff', marginTop: 16, marginBottom: 8 }}>
                        {children}
                      </Title>
                    ),
                    h4: ({ children }) => (
                      <Title level={5} style={{ color: 'rgba(255,255,255,0.85)', marginTop: 12, marginBottom: 8 }}>
                        {children}
                      </Title>
                    ),
                    p: ({ children }) => (
                      <Paragraph style={{ color: 'rgba(255,255,255,0.75)', marginBottom: 12 }}>
                        {children}
                      </Paragraph>
                    ),
                    ul: ({ children }) => (
                      <ul style={{ color: 'rgba(255,255,255,0.75)', paddingLeft: 24, marginBottom: 12 }}>
                        {children}
                      </ul>
                    ),
                    ol: ({ children }) => (
                      <ol style={{ color: 'rgba(255,255,255,0.75)', paddingLeft: 24, marginBottom: 12 }}>
                        {children}
                      </ol>
                    ),
                    li: ({ children }) => (
                      <li style={{ marginBottom: 4 }}>{children}</li>
                    ),
                    code: ({ node, inline, className, children, ...props }: any) =>
                      inline ? (
                        <code
                          style={{
                            background: 'rgba(0,0,0,0.3)',
                            padding: '2px 6px',
                            borderRadius: 4,
                            color: '#52c41a',
                            fontSize: '0.9em',
                          }}
                        >
                          {children}
                        </code>
                      ) : (
                        <pre
                          style={{
                            background: 'rgba(0,0,0,0.3)',
                            padding: 16,
                            borderRadius: 8,
                            overflow: 'auto',
                            marginBottom: 16,
                            border: '1px solid rgba(148,163,184,0.1)',
                          }}
                        >
                          <code style={{ color: 'rgba(255,255,255,0.85)', fontSize: '0.9em' }}>
                            {children}
                          </code>
                        </pre>
                      ),
                    blockquote: ({ children }) => (
                      <blockquote
                        style={{
                          borderLeft: '4px solid #1890ff',
                          paddingLeft: 16,
                          marginLeft: 0,
                          marginBottom: 16,
                          color: 'rgba(255,255,255,0.65)',
                          fontStyle: 'italic',
                        }}
                      >
                        {children}
                      </blockquote>
                    ),
                    table: ({ children }) => (
                      <div style={{ overflowX: 'auto', marginBottom: 16 }}>
                        <table
                          style={{
                            width: '100%',
                            borderCollapse: 'collapse',
                            border: '1px solid rgba(148,163,184,0.2)',
                          }}
                        >
                          {children}
                        </table>
                      </div>
                    ),
                    th: ({ children }) => (
                      <th
                        style={{
                          background: 'rgba(0,0,0,0.3)',
                          padding: '8px 12px',
                          border: '1px solid rgba(148,163,184,0.2)',
                          color: '#fff',
                          fontWeight: 'bold',
                          textAlign: 'left',
                        }}
                      >
                        {children}
                      </th>
                    ),
                    td: ({ children }) => (
                      <td
                        style={{
                          padding: '8px 12px',
                          border: '1px solid rgba(148,163,184,0.2)',
                          color: 'rgba(255,255,255,0.75)',
                        }}
                      >
                        {children}
                      </td>
                    ),
                  }}
                >
                  {markdownContent}
                </ReactMarkdown>
              </div>
            </Card>
          )}
        </div>
      ),
    },
  ];

  return (
    <div style={{ 
      height: '100%', 
      overflow: 'auto', 
      overflowY: 'scroll',
      padding: '16px 20px', 
      paddingBottom: '40px',
      background: '#0f172a' 
    }}>
      <Tabs
        defaultActiveKey="builtin"
        items={tabItems}
        style={{ height: '100%' }}
        tabBarStyle={{ 
          marginBottom: 16,
          borderBottom: '1px solid rgba(148,163,184,0.14)',
        }}
      />
    </div>
  );
};

export default PromptExamples;
