"""
Helper module for working with Apache AGE (A Graph Extension for PostgreSQL)
"""
import psycopg2
from psycopg2 import pool
from typing import Any, Dict, List, Optional
import logging
import re

logger = logging.getLogger(__name__)


class AGEHelper:
    """Helper class for executing Cypher queries via Apache AGE"""
    
    def __init__(self, connection_string: str, graph_name: str = "power_atlas_graph"):
        self.connection_string = connection_string
        
        # Validate graph_name to prevent SQL injection
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', graph_name):
            raise ValueError(f"Invalid graph name: {graph_name}. Must be a valid identifier.")
        self.graph_name = graph_name
        
        # Create connection pool
        self.pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=connection_string
        )
        
        self._ensure_graph_exists()
    
    def _get_connection(self):
        """Get a connection from the pool"""
        return self.pool.getconn()
    
    def _put_connection(self, conn):
        """Return a connection to the pool"""
        self.pool.putconn(conn)
    
    def _ensure_graph_exists(self):
        """Ensure the graph exists, create if it doesn't"""
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                # Load AGE extension and set search path
                cur.execute("LOAD 'age'")
                cur.execute("SET search_path = ag_catalog, '$user', public")
                
                # Check if graph exists
                cur.execute(
                    "SELECT * FROM ag_catalog.ag_graph WHERE name = %s",
                    (self.graph_name,)
                )
                if cur.fetchone() is None:
                    # Create graph using validated graph_name (regex-validated in __init__)
                    # Note: PostgreSQL doesn't support parameterization for identifiers,
                    # so we use f-string with validated input
                    cur.execute(f"SELECT ag_catalog.create_graph('{self.graph_name}')")
                    conn.commit()
                    logger.info(f"Created graph: {self.graph_name}")
                else:
                    logger.info(f"Graph {self.graph_name} already exists")
        except Exception as e:
            logger.error(f"Error ensuring graph exists: {e}")
            raise
        finally:
            if conn:
                self._put_connection(conn)
    
    def execute_cypher(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute a Cypher query via Apache AGE
        
        Args:
            query: Cypher query string
            params: Optional parameters dictionary (currently not used in query execution,
                    reserved for future implementation. For now, queries are executed as-is.)
            
        Returns:
            List of result dictionaries
            
        Security Note:
            This is a local development tool. The query parameter is directly interpolated
            into the AGE SQL wrapper. **DO NOT use in production without implementing proper
            input validation or parameterization.** For production use, implement query
            sanitization or a query builder that prevents SQL injection.
        """
        if params is None:
            params = {}
        
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                # Load AGE and set search path
                cur.execute("LOAD 'age'")
                cur.execute("SET search_path = ag_catalog, '$user', public")
                
                # Prepare the Cypher query wrapped in AGE's SQL function
                # Note: query is directly interpolated - acceptable for local dev tool
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
        finally:
            if conn:
                self._put_connection(conn)
    
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
    
    def close(self):
        """Close all connections in the pool"""
        if self.pool:
            self.pool.closeall()
            logger.info("Connection pool closed")
