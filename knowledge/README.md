# Knowledge 模块

本模块基于 lightrag 实现知识库智能问答能力，并整合 embedding、faiss、neo4j 实现智能文档与知识图谱。

## 依赖
- lightrag
- faiss-cpu
- sentence-transformers
- neo4j

## 目录结构
- config.py：配置文件
- loader.py：知识库文档加载器
- embedding.py：文本向量化
- faiss_index.py：faiss 向量库
- kg_neo4j.py：neo4j 知识图谱接口
- rag_engine.py：RAG 检索与问答引擎
- pipeline.py：端到端问答流程
- api.py：对外问答接口

## 端到端流程
1. 加载文档，分段。
2. 用 embedding.py 向量化所有片段。
3. 用 faiss_index.py 构建向量索引。
4. 用 kg_neo4j.py 抽取实体/关系并写入 neo4j。
5. 用户提问时，pipeline.py 检索相关文档片段和知识图谱，拼接 context，调用 rag_engine.py 生成答案。

## 示例
```python
from knowledge.pipeline import answer_question, FaissIndex, embed
# 假设 doc_texts = ["...", "..."]
doc_vectors = embed(doc_texts)
faiss_index = FaissIndex(dim=doc_vectors.shape[1])
faiss_index.add(doc_vectors)
answer = answer_question("你的问题是什么？", doc_texts, faiss_index)
print(answer)
``` 