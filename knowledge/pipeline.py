from .embedding import embed
from .faiss_index import FaissIndex
from .kg_neo4j import query_kg
from .rag_engine import KnowledgeRag

# 假设已加载文档和向量
# doc_texts = [...]
# doc_vectors = embed(doc_texts)
# faiss_index = FaissIndex(dim=doc_vectors.shape[1])
# faiss_index.add(doc_vectors)

rag = KnowledgeRag()

def extract_entities(question):
    # 简单分词/实体抽取，可用更强NLP工具替换
    return [question]  # 占位实现

def answer_question(question, doc_texts, faiss_index):
    q_vec = embed([question])
    doc_ids = faiss_index.search(q_vec, topk=5)
    docs = [doc_texts[i] for i in doc_ids]
    entities = extract_entities(question)
    kg_info = [query_kg(e) for e in entities]
    context = '\n'.join(docs) + '\n' + str(kg_info)
    return rag.query(question + '\n' + context) 