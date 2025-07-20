from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))

def query_kg(entity):
    with driver.session() as session:
        result = session.run("MATCH (n)-[r]->(m) WHERE n.name=$name RETURN n,r,m", name=entity)
        return result.data() 