import os

def load_documents(path):
    docs = []
    for fname in os.listdir(path):
        if fname.endswith('.txt'):
            with open(os.path.join(path, fname), 'r', encoding='utf-8') as f:
                docs.append(f.read())
    return docs 