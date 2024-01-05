import neo4j

def execute(URI: str, user: str, password: str, db_name: str, 
            query: str, top_k: int | None):
    
    AUTH = (user, password)
    with neo4j.GraphDatabase.driver(URI, auth=AUTH) as driver:
        records, _, _ = driver.execute_query(query, database_=db_name)
        results = []

        for index, res in enumerate(records):
            results.append(res.data())
            
            if top_k and index+1 == top_k:
                break
        
    
    return results
