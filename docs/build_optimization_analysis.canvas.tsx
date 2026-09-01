import React from 'react';
import {
  BarChart,
  Callout,
  Card,
  CardBody,
  CardHeader,
  Code,
  Divider,
  Grid,
  H1,
  H2,
  H3,
  Pill,
  Row,
  Stack,
  Stat,
  Table,
  Text,
  useHostTheme,
} from 'cursor/canvas';

// --- Data: artifact sizes ---
const artifactRows: React.ReactNode[][] = [
  [<Text weight="semibold">Linux amd64</Text>, <Code>.deb</Code>, '877.81 MB', '655s', <Pill>最大</Pill>],
  [<Text weight="semibold">macOS amd64</Text>, <Code>.pkg</Code>, '759.9 MB', '1053s', <Pill>最慢</Pill>],
  [<Text weight="semibold">macOS aarch64</Text>, <Code>.pkg</Code>, '723.1 MB', '456s', <Pill>最快</Pill>],
  [<Text weight="semibold">Windows amd64</Text>, <Code>.exe</Code>, '578.6 MB', '854s', <Pill>最小</Pill>],
];

// --- Data: build timing breakdown (approximate) ---
const timingRows: React.ReactNode[][] = [
  [<Text weight="semibold">总耗时</Text>, '655s', '456s', '1053s', '854s'],
  ['Core (PyInstaller)', '564s (86%)', '259s (57%)', '~600s+', '~700s+'],
  ['Frontend (Vite)', '79s (12%)', '88s (19%)', '~80s', '~80s'],
  ['Installer', '0s', '78s (17%)', '~200s', '~70s'],
];

const buildStages = ['Core', 'Frontend', 'Installer'];
const buildSeries = [
  { name: 'Linux amd64', data: [564, 79, 0] },
  { name: 'macOS aarch64', data: [259, 88, 78] },
  { name: 'macOS amd64', data: [600, 80, 200] },
  { name: 'Windows amd64', data: [700, 80, 70] },
];

// --- Data: priority ranking ---
const priorityRows: React.ReactNode[][] = [
  [
    <Pill>P0</Pill>,
    <Text>修复 linux_builder.py 传递 strip / upx 参数</Text>,
    <Text tone="success" weight="semibold">-10~30% 大小</Text>,
    <Text>2 小时</Text>,
  ],
  [
    <Pill>P0</Pill>,
    <Text>dpkg-deb 加 -Zxz -z9</Text>,
    <Text tone="success" weight="semibold">-30~40% 大小</Text>,
    <Text>1 小时</Text>,
  ],
  [
    <Pill>P1</Pill>,
    <Text>移除 data_files 中的 gui / tests</Text>,
    <Text tone="success" weight="semibold">-13 MB</Text>,
    <Text>10 分钟</Text>,
  ],
  [
    <Pill>P1</Pill>,
    <Text>拆分 vendor chunk (manualChunks)</Text>,
    <Text tone="success" weight="semibold">-30~50% 前端加载</Text>,
    <Text>4 小时</Text>,
  ],
  [
    <Pill>P2</Pill>,
    <Text>LightRAG 可选依赖改为 lazy load</Text>,
    <Text tone="success" weight="semibold">-200~400 MB</Text>,
    <Text>较大重构</Text>,
  ],
  [
    <Pill>P3</Pill>,
    <Text>playwright 运行时下载</Text>,
    <Text tone="success" weight="semibold">-280 MB</Text>,
    <Text>8 小时</Text>,
  ],
  [
    <Pill>P3</Pill>,
    <Text>macOS amd64 runner (2026-09 复评)</Text>,
    <Text tone="muted" weight="semibold">已最优</Text>,
    <Text>无可执行改动</Text>,
  ],
];

// --- Severity helpers ---
function SeverityBadge({ tone }: { tone: 'critical' | 'major' | 'minor' }) {
  const theme = useHostTheme();
  const map = {
    critical: { label: '致命', bg: theme.category.red, fg: '#fff' },
    major: { label: '重要', bg: theme.category.yellow, fg: theme.bg.editor },
    minor: { label: '次要', bg: theme.fill.tertiary, fg: theme.text.primary },
  };
  const item = map[tone];
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '2px 8px',
        borderRadius: 10,
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: 0.3,
        backgroundColor: item.bg,
        color: item.fg,
      }}
    >
      {item.label}
    </span>
  );
}

export default function BuildOptimizationAnalysis() {
  const theme = useHostTheme();

  return (
    <Stack gap={20}>
      {/* Header */}
      <Stack gap={6}>
        <Text tone="tertiary" size="small">eCan.ai Build Pipeline · 优化分析</Text>
        <H1 style={{ margin: 0 }}>eCan.ai 构建流程优化分析报告</H1>
        <Text tone="secondary">基于 v0.7.0-v0.9.96j 构建日志 · 2026-09-01</Text>
      </Stack>

      {/* KPI strip */}
      <Grid columns={4} gap={12}>
        <Card>
          <CardBody>
            <Stat value="877.81 MB" label="最大产物 (Linux deb)" tone="danger" />
          </CardBody>
        </Card>
        <Card>
          <CardBody>
            <Stat value="1053s" label="最长耗时 (macOS amd64)" tone="warning" />
          </CardBody>
        </Card>
        <Card>
          <CardBody>
            <Stat value="~38 min" label="流水线墙钟时间" tone="info" />
          </CardBody>
        </Card>
        <Card>
          <CardBody>
            <Stat value="P0/P1" label="主要优化项" tone="success" />
          </CardBody>
        </Card>
      </Grid>

      <Divider />

      {/* Section 1 */}
      <Stack gap={12}>
        <H2 style={{ margin: 0 }}>1. 产物大小对比</H2>
        <Text tone="secondary">
          四个平台的产物大小与单次构建耗时。Linux deb 比 Windows installer 大 ~52%，但 build 时长更短。
        </Text>

        <Table
          headers={['平台', '格式', '大小', '构建耗时', '备注']}
          rows={artifactRows}
          columnAlign={['left', 'left', 'right', 'right', 'left']}
        />

        <BarChart
          categories={['Linux amd64', 'macOS amd64', 'macOS aarch64', 'Windows amd64']}
          series={[{ name: '产物大小 (MB)', data: [877.81, 759.9, 723.1, 578.6], tone: 'danger' }]}
          valueSuffix=" MB"
          height={200}
        />
      </Stack>

      <Divider />

      {/* Section 2 */}
      <Stack gap={12}>
        <H2 style={{ margin: 0 }}>2. Linux deb 偏大的根因（按严重程度）</H2>

        <H3 style={{ margin: 0 }}>A. 致命问题：linux_builder.py 不传 strip / upx 参数</H3>
        <Card>
          <CardHeader trailing={<SeverityBadge tone="critical" />}>Root Cause</CardHeader>
          <CardBody>
            <Stack gap={8}>
              <Text>
                <Code>build_config.json</Code> 的 prod profile 声明了 <Code>upx_compression: true</Code> +{' '}
                <Code>strip_debug: true</Code>，但 <Code>build_system/linux_builder.py</Code> 的{' '}
                <Code>build_pyinstaller()</Code> 只读取了 <Code>hiddenimports / collect_all / excludes / data_files</Code>，
                <Text weight="semibold"> 完全忽略了 profile 中这两个开关。</Text>
              </Text>
              <Text tone="secondary">
                影响：所有 .so / .pyc 没有 strip；PyInstaller 产物没有被 UPX 压缩。
              </Text>
              <Callout tone="success" title="预期效果">
                <Text>开启后能减少 <Text weight="bold">10~30%</Text> 体积。</Text>
              </Callout>
            </Stack>
          </CardBody>
        </Card>

        <H3 style={{ margin: 0 }}>B. 致命问题：dpkg-deb 不传最强压缩参数</H3>
        <Card>
          <CardHeader trailing={<SeverityBadge tone="critical" />}>Root Cause</CardHeader>
          <CardBody>
            <Stack gap={8}>
              <Text>
                <Code>linux_builder.py</Code> 调用 <Code>dpkg-deb --build --root-owner-group</Code>，
                缺少 <Code>-Zxz -z9</Code>，让 deb 走 xz 最高压缩等级。
              </Text>
              <Text tone="secondary">
                PyInstaller 产物包含大量 .pyc 和 .so（已压缩过的二进制），再过一遍 xz 还能再降 30~40%。
              </Text>
              <Row gap={8} align="center">
                <Text size="small" tone="tertiary">877 MB</Text>
                <div
                  style={{
                    flex: 1,
                    height: 8,
                    backgroundColor: theme.fill.tertiary,
                    borderRadius: 4,
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      width: '65%',
                      height: '100%',
                      backgroundColor: theme.accent.primary,
                    }}
                  />
                </div>
                <Text size="small" tone="tertiary">~550-620 MB</Text>
              </Row>
              <Callout tone="success" title="预期效果">
                <Text>877 MB → <Text weight="bold">~550-620 MB</Text>，一步可降 30%+。</Text>
              </Callout>
            </Stack>
          </CardBody>
        </Card>

        <H3 style={{ margin: 0 }}>C. 次要问题：死代码被打进包</H3>
        <Card>
          <CardHeader trailing={<SeverityBadge tone="minor" />}>Cleanup</CardHeader>
          <CardBody>
            <Stack gap={8}>
              <Text>
                <Code>build_config.json</Code> 的 <Code>data_files</Code> 包含：
              </Text>
              <Row gap={8} align="center">
                <Pill>gui</Pill>
                <Text>7.4 MB · 废弃的 PyQt5 GUI</Text>
              </Row>
              <Row gap={8} align="center">
                <Pill>tests</Pill>
                <Text>6.1 MB · pytest 用例</Text>
              </Row>
              <Text tone="secondary">
                这两个目录应从 <Code>data_files</Code> 中移除或移入 <Code>excludes</Code>。
              </Text>
            </Stack>
          </CardBody>
        </Card>

        <H3 style={{ margin: 0 }}>D. 重要问题：collect_all 拉入了大量可选依赖</H3>
        <Card>
          <CardHeader trailing={<SeverityBadge tone="major" />}>Heavy Imports</CardHeader>
          <CardBody>
            <Stack gap={8}>
              <Text>
                <Code>neo4j</Code> / <Code>pymilvus</Code> / <Code>qdrant_client</Code> /{' '}
                <Code>pgvector</Code> / <Code>redis</Code> / <Code>pymongo</Code> 全部被{' '}
                <Code>collect_all</Code>。这些是 LightRAG 可选存储后端，多数用户只用 faiss，却默认全打包。
              </Text>
              <Row gap={8} wrap>
                <Pill>neo4j</Pill>
                <Pill>pymilvus</Pill>
                <Pill>qdrant_client</Pill>
                <Pill>pgvector</Pill>
                <Pill>redis</Pill>
                <Pill>pymongo</Pill>
              </Row>
              <Callout tone="warning" title="估算">
                <Text>合计估计多打 <Text weight="bold">200~400 MB</Text>。</Text>
              </Callout>
            </Stack>
          </CardBody>
        </Card>

        <H3 style={{ margin: 0 }}>E. 次要问题：playwright Python 包被全量收集</H3>
        <Card>
          <CardHeader trailing={<SeverityBadge tone="minor" />}>Bloat</CardHeader>
          <CardBody>
            <Stack gap={8}>
              <Text>
                实际未打包 Chromium 浏览器（third_party 不在 data_files），但 playwright Python 包的{' '}
                <Code>collect_data</Code> 仍收集了元数据。建议运行时再下载浏览器二进制。
              </Text>
            </Stack>
          </CardBody>
        </Card>
      </Stack>

      <Divider />

      {/* Section 3 */}
      <Stack gap={12}>
        <H2 style={{ margin: 0 }}>3. 前端构建优化</H2>
        <Text tone="secondary">
          前端 vendor chunk 达 <Text weight="bold">12.1 MB</Text>（gzip 后 <Text weight="bold">3.5 MB</Text>），
          远超 5 MB 警告线。
        </Text>

        <Card>
          <CardHeader>Chunk 体积告警</CardHeader>
          <CardBody>
            <Code>
              vendor-C2IlIxh5.js: 12,131.28 kB → gzip 3,528.54 kB
            </Code>
          </CardBody>
        </Card>

        <H3 style={{ margin: 0 }}>优化建议</H3>
        <Stack gap={8}>
          <Row gap={12} align="start">
            <Pill>1</Pill>
            <Stack gap={2} style={{ flex: 1 }}>
              <Text weight="semibold">拆分 manualChunks</Text>
              <Text tone="secondary">
                当前 <Code>vite.config.ts</Code> 把所有 <Code>node_modules</Code> 归到一个{' '}
                <Code>vendor</Code>，过粗。应拆分为 antd / semi-ui、emotion、flowgram、react-dom 等独立 chunk。
              </Text>
            </Stack>
          </Row>
          <Row gap={12} align="start">
            <Pill>2</Pill>
            <Stack gap={2} style={{ flex: 1 }}>
              <Text weight="semibold">构建时预压缩</Text>
              <Text tone="secondary">
                考虑 gzip / brotli 预压缩（构建时生成 .gz / .br 文件），CDN 直接分发静态压缩版本。
              </Text>
            </Stack>
          </Row>
          <Row gap={12} align="start">
            <Pill>3</Pill>
            <Stack gap={2} style={{ flex: 1 }}>
              <Text weight="semibold">动态导入 heavy 模块</Text>
              <Text tone="secondary">
                <Code>@flowgram.ai/*</Code>、<Code>@react-sigma/*</Code> 只在 skill-editor 页面使用，应 lazy import。
              </Text>
            </Stack>
          </Row>
        </Stack>
      </Stack>

      <Divider />

      {/* Section 4 */}
      <Stack gap={12}>
        <H2 style={{ margin: 0 }}>4. 构建时间分析</H2>

        <Table
          headers={['阶段', 'Linux (s)', 'macOS arm (s)', 'macOS amd64 (s)', 'Windows (s)']}
          rows={timingRows}
          columnAlign={['left', 'right', 'right', 'right', 'right']}
          striped
        />

        <BarChart
          categories={buildStages}
          series={buildSeries}
          stacked
          valueSuffix=" s"
          height={240}
        />

        <H3 style={{ margin: 0 }}>关键观察</H3>
        <Stack gap={6}>
          <Text>
            • macOS amd64 耗时最长 — Intel 模拟器 vs Apple Silicon 原生，运行差异显著。
          </Text>
          <Text>• Linux pip install ~55s（无缓存）；首次构建缓存 MISS 属正常。</Text>
          <Text>
            • PyInstaller 分析阶段 ~9 分钟合理（依赖太重：torch / faiss / playwright 等）。
          </Text>
          <Text>
            • 同 tag 重新构建时，pip / venv / npm / playwright 缓存会命中（缓存 key = platform + arch + requirements hash）。
          </Text>
        </Stack>
      </Stack>

      <Divider />

      {/* Section 5 */}
      <Stack gap={12}>
        <H2 style={{ margin: 0 }}>5. CI/CD 流水线</H2>

        <Card>
          <CardHeader>当前结构</CardHeader>
          <CardBody>
            <Code>
              {`validate-tag → 4 builds (并行) → upload_COS → appcast → download_links → summary`}
            </Code>
          </CardBody>
        </Card>

        <Grid columns={2} gap={12}>
          <Card>
            <CardHeader>墙钟时间</CardHeader>
            <CardBody>
              <Stat value="~38 min" label="05:56 → 06:34" tone="warning" />
              <div style={{ height: 8 }} />
              <Text tone="secondary">
                由最慢的 <Code>macOS amd64 (1053s)</Code> 决定。
              </Text>
            </CardBody>
          </Card>
          <Card>
            <CardHeader>瓶颈节点</CardHeader>
            <CardBody>
              <Stack gap={4}>
                <Row gap={8} align="center">
                  <Pill>SLOW</Pill>
                  <Text>macOS amd64 构建 (~17.5 min)</Text>
                </Row>
                <Row gap={8} align="center">
                  <Pill>MED</Pill>
                  <Text>Windows 构建 (~14 min)</Text>
                </Row>
                <Row gap={8} align="center">
                  <Pill>FAST</Pill>
                  <Text>macOS aarch64 构建 (~7.6 min)</Text>
                </Row>
              </Stack>
            </CardBody>
          </Card>
        </Grid>

        <H3 style={{ margin: 0 }}>可能的优化</H3>
        <Stack gap={6}>
          <Text>
            1. macOS amd64：runner 已升 <Code>macos-15-intel</Code>（不是 macos-latest，避免 Rosetta 2 模拟）；
            GitHub macOS runner 没有 size 维度，真正的加速路径是切 self-hosted <Code>runner_group=ecan-macos-amd64</Code>（仓库已支持）。
          </Text>
          <Text>2. 前端构建复用缓存（同一 tag 重复构建时，npm cache 命中）。</Text>
          <Text>3. playwright browsers 缓存在首次构建后保存，下次命中。</Text>
        </Stack>
      </Stack>

      <Divider />

      {/* Section 6 */}
      <Stack gap={12}>
        <H2 style={{ margin: 0 }}>6. 优化优先级排序</H2>
        <Text tone="secondary">综合收益与工作量，P0 项为性价比最高的两步。</Text>

        <Table
          headers={['优先级', '优化项', '预期收益', '工作量']}
          rows={priorityRows}
          columnAlign={['center', 'left', 'left', 'left']}
          striped
        />

        <Callout tone="success" title="结论">
          <Text>
            <Text weight="bold">前两步（合计 3 小时）</Text> 可让 Linux deb 从 877 MB 降到约 550~620 MB，
            体积下降近 30%+。这是 ROI 最高的杠杆，应优先执行。
          </Text>
        </Callout>
      </Stack>

      <Divider />

      {/* Footer */}
      <Text tone="tertiary" size="small">
        数据采集自 2026-09-01 v0.7.0-v0.9.96j 构建日志 · 报告生成时间 2026-09-01
      </Text>
    </Stack>
  );
}