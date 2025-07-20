from .rag_engine import KnowledgeRag

rag = KnowledgeRag()

def ask(question: str) -> str:
    return rag.query(question) 