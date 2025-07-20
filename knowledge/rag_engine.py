from lightrag import RagEngine
from .config import CONFIG

class KnowledgeRag:
    def __init__(self):
        self.engine = RagEngine(
            index_path=CONFIG['index_path'],
            model_name=CONFIG['model_name']
        )

    def query(self, question):
        return self.engine.ask(question) 