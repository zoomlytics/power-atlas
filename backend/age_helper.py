"""
Helper module for working with Apache AGE (A Graph Extension for PostgreSQL)
"""
import psycopg2
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class AGEHelper:
    """Helper class for executing Cypher queries via Apache AGE"""
    
    def __init__(self, connection_string: str, graph_name: str = "power_atlas_graph"):
        self.connection_string = connection_string
        self.graph_name = graph_name
        self._ensure_graph_exists()
    
    def _get_connection(self):
        """Create a new database connection"""
        return psycopg2.connect(self.connection_string)
    
    def _ensure_graph_exists(self):
        """Ensure the graph exists, create if it doesn't"""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    # Check if graph exists
                    cur.execute(
                        "SELECT * FROM ag_catalog.ag_graph WHERE name = %s",
                        (self.graph_name,)
                    )
                    if cur.fetchone() is None:
                        # Create graph
                        cur.execute(f"SELECT create_graph('{self.graph_name}')")
                        conn.commit()
                        logger.info(f"Created graph: {self.graph_name}")
                    else:
                        logger.info(f"Graph {self.graph_name} already exists")
        except Exception as e:
            logger.error(f"Error ensuring graph exists: {e}")
            raise
    
    def execute_cypher(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute a Cypher query via Apache AGE
        
        Args:
            query: Cypher query string
            params: Optional parameters dictionary
            
        Returns:
            List of result dictionaries
        """
        if params is None:
            params = {}
        
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    # Set search path to include ag_catalog
                    cur.execute("SET search_path = ag_catalog, '$user', public")
                    
                    # Prepare the Cypher query wrapped in AGE's SQL function
                    # AGE uses a specific SQL syntax to execute Cypher queries
                    age_query = f"""
                        SELECT * FROM cypher('{self.graph_name}', $$
                            {query}
                        $$) as (result agtype);
                    """
                    
                    logger.info(f"Executing query: {age_query}")
                    cur.execute(age_query)
                    
                    # Fetch all results
                    rows = cur.fetchall()
                    
                    # Convert to list of dictionaries
                    results = []
                    for row in rows:
                        if row and row[0] is not None:
                            results.append({"result": str(row[0])})
                    
                    conn.commit()
                    return results
                    
        except Exception as e:
            logger.error(f"Error executing Cypher query: {e}")
            raise
    
    def seed_demo_graph(self) -> Dict[str, Any]:
        """
        Seed a small demo graph with a few nodes and relationships
        
        Returns:
            Dictionary with status information
        """
        try:
            # Clear existing data
            self.execute_cypher("MATCH (n) DETACH DELETE n")
            
            # Create demo nodes and relationships
            queries = [
                # Create person nodes
                "CREATE (:Person {name: 'Alice', age: 30})",
                "CREATE (:Person {name: 'Bob', age: 35})",
                "CREATE (:Person {name: 'Charlie', age: 28})",
                
                # Create relationships
                """
                MATCH (a:Person {name: 'Alice'}), (b:Person {name: 'Bob'})
                CREATE (a)-[:KNOWS {since: 2020}]->(b)
                """,
                """
                MATCH (b:Person {name: 'Bob'}), (c:Person {name: 'Charlie'})
                CREATE (b)-[:KNOWS {since: 2021}]->(c)
                """
            ]
            
            for query in queries:
                self.execute_cypher(query)
            
            logger.info("Demo graph seeded successfully")
            return {
                "status": "success",
                "message": "Demo graph created with 3 persons and 2 relationships"
            }
            
        except Exception as e:
            logger.error(f"Error seeding demo graph: {e}")
            raise
