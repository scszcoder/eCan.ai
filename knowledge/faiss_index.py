import faiss
import numpy as np

class FaissIndex:
    def __init__(self, dim):
        self.index = faiss.IndexFlatL2(dim)
    def add(self, vectors):
        self.index.add(np.array(vectors).astype('float32'))
    def search(self, query_vector, topk=5):
        D, I = self.index.search(np.array(query_vector).astype('float32'), topk)
        return I[0] 