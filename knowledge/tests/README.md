# Knowledge Module - 真实文件测试

本目录用于存放真实的测试文件（PDF、Excel、CSV 等），用于验证 LightRAG 知识库的处理能力。

---

## 📁 目录结构

```
knowledge/tests/
├── README.md                    # 本文件
├── sample_files/                # 测试样本文件目录
│   ├── excel/                   # Excel 测试文件
│   ├── pdf/                     # PDF 测试文件
│   ├── csv/                     # CSV 测试文件
│   ├── docx/                    # Word 文档测试文件
│   └── pptx/                    # PowerPoint 测试文件
└── test_*.txt                   # 文本测试数据
```

---

## 🧪 测试方法

### 方式 1：通过 UI 上传测试

1. 启动 eCan.ai 应用
2. 进入 Knowledge 页面
3. 上传 `sample_files/` 中的测试文件
4. 观察处理日志和结果

### 方式 2：使用 LightRAG API 测试

```bash
# 上传文件
curl -X POST http://localhost:9621/documents/upload \
  -F "file=@knowledge/tests/sample_files/excel/test.xlsx"

# 查看处理状态
curl http://localhost:9621/documents/statuses
```

---

## 📊 测试文件说明

### Excel 文件测试

**放置位置**：`sample_files/excel/`

**测试重点**：
- 空列清理（16k 列问题）
- 宽表垂直分区
- Pandas 语义化预处理
- 数据清洗和类型推断

**推荐测试文件**：
- 包含多列的价格表
- 包含空值的库存表
- 包含多个 Sheet 的文件

### PDF 文件测试

**放置位置**：`sample_files/pdf/`

**测试重点**：
- 表格识别和提取
- 文本内容提取
- 分块质量

**推荐测试文件**：
- 包含规整表格的报告
- 学术论文（复杂布局）
- 扫描件 PDF

### CSV 文件测试

**放置位置**：`sample_files/csv/`

**测试重点**：
- 分隔符检测
- 数据清洗
- Pandas 预处理

### DOCX/PPTX 测试

**放置位置**：`sample_files/docx/` 和 `sample_files/pptx/`

**测试重点**：
- 表格提取
- 文本内容提取
- 混合内容处理

---

## 🎯 验证清单

### Excel 处理验证

- [ ] 上传包含 16k 空列的 Excel 文件
- [ ] 验证日志显示列数被清理（16384 → 实际列数）
- [ ] 验证 Pandas 预处理生成元数据
- [ ] 验证分块成功，无空 chunks
- [ ] 验证查询准确度

### 停止功能验证

- [ ] 上传大文件开始处理
- [ ] 点击停止按钮
- [ ] 验证日志显示立即停止（< 0.5秒）
- [ ] 验证处理状态变为 FAILED

### Pandas 预处理验证

- [ ] 设置 `ENABLE_PANDAS_PREPROCESSING=1`
- [ ] 上传 Excel/CSV 文件
- [ ] 验证日志显示 "Used Pandas preprocessing"
- [ ] 验证生成的 chunks 包含元数据和统计信息

---

## 📝 测试数据文件

当前已有的测试数据：
- `test_docs.txt` - 文档测试数据
- `test_questions.txt` - 问题测试数据
- `test_transformer.txt` - 转换器测试数据

---

## 🚀 添加测试文件

将你的测试文件放入对应的子目录：

```bash
# Excel 文件
cp your_test.xlsx knowledge/tests/sample_files/excel/

# PDF 文件
cp your_test.pdf knowledge/tests/sample_files/pdf/

# CSV 文件
cp your_test.csv knowledge/tests/sample_files/csv/
```

---

## 📊 推荐的测试文件

### 1. Excel 测试文件

**简单表格**（测试基础功能）：
- 3-5 列
- 10-20 行
- 包含数值和文本

**复杂表格**（测试高级功能）：
- 10+ 列（测试宽表分区）
- 100+ 行（测试性能）
- 包含空值（测试数据清洗）
- 多个 Sheet（测试多表处理）

### 2. PDF 测试文件

**规整表格**：
- 财务报表
- 数据统计表

**复杂文档**：
- 学术论文
- 技术文档

### 3. CSV 测试文件

**标准 CSV**：
- 逗号分隔
- 包含 header

**TSV 文件**：
- Tab 分隔
- 测试分隔符检测

---

**说明**：真实文件测试比单元测试更能验证实际效果。
