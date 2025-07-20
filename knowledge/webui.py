import gradio as gr
from knowledge.pipeline import answer_question, FaissIndex, embed

# 假设 doc_texts 已经加载并向量化
# 这里用简单示例数据

doc_texts = [
    "Python 是一种广泛使用的高级编程语言。",
    "Neo4j 是一个流行的图数据库。",
    "Faiss 用于高效的向量检索。",
    "lightrag 支持 RAG 智能问答。"
]
doc_vectors = embed(doc_texts)
faiss_index = FaissIndex(dim=doc_vectors.shape[1])
faiss_index.add(doc_vectors)

def qa_fn(question):
    return answer_question(question, doc_texts, faiss_index)

iface = gr.Interface(
    fn=qa_fn,
    inputs=gr.Textbox(lines=2, label="请输入你的问题"),
    outputs=gr.Textbox(label="智能答复"),
    title="知识库智能问答 WebUI",
    description="基于 lightrag + faiss + neo4j 的智能文档与知识图谱问答系统"
)

if __name__ == "__main__":
    iface.launch() 