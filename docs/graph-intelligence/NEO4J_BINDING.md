<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/graph-intelligence/NEO4J_BINDING.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.5.0
updated: 2026-07-22
/L9_META -->

# Neo4j Graph-Intelligence Binding

Decision: [ADR-085](../adr/ADR-085-graph-intelligence-port-and-neo4j-substrate.md).
Scope: the read-only graph-intelligence adapter reading the Graphiti-managed
Neo4j database. Graphiti keeps its own write-capable credential.

## Selected V1 pair

| Component | Version |
|---|---|
| Graphiti | v0.30.2 |
| Neo4j | 5.26 |
| Graph Data Science | 2.13 |
| Python driver | `neo4j>=5.26,<7` (extra `graph-intelligence`) |

## Settings

| Setting | Environment | Default |
|---|---|---|
| `graph_intelligence_backend` | `L9_MEMORY_GRAPH_BACKEND` | `none` |
| `graph_intelligence_required` | `L9_MEMORY_GRAPH_REQUIRED` | `false` |
| `graph_neo4j_uri` | `L9_MEMORY_GRAPH_NEO4J_URI` | — (required for `neo4j`) |
| `graph_neo4j_database` | `L9_MEMORY_GRAPH_NEO4J_DATABASE` | `neo4j` |
| `graph_neo4j_user` | `L9_MEMORY_GRAPH_NEO4J_USER` | — |
| `graph_neo4j_password` | `L9_MEMORY_GRAPH_NEO4J_PASSWORD` | — (secret; environment or secret manager only) |
| `graph_query_timeout_ms` | `L9_MEMORY_GRAPH_QUERY_TIMEOUT_MS` | `3000` |
| `graph_gds_max_nodes` | `L9_MEMORY_GRAPH_GDS_MAX_NODES` | `50000` |
| `graph_relationship_allowlist` | `L9_MEMORY_GRAPH_RELATIONSHIP_ALLOWLIST` | `RELATES_TO,MENTIONS,HAS_EPISODE,NEXT_EPISODE,HAS_MEMBER` |
| `graph_expected_schema_fingerprint` | `L9_MEMORY_GRAPH_SCHEMA_FINGERPRINT` | — (record after live qualification) |
| `graph_link_prediction_enabled` | `L9_MEMORY_GRAPH_LINK_PREDICTION` | `false` |
| `graph_algorithm_maturity_ceiling` | `L9_MEMORY_GRAPH_MATURITY_CEILING` | `production` |

Never commit the password. It is read from the environment (or the existing
secret owner) and never appears in health output or configuration reprs.

## Least-privilege reader

Neo4j Enterprise (role-based access control), against the Graphiti database
`graphiti`:

```cypher
CREATE USER l9_graph_reader SET PASSWORD $password CHANGE NOT REQUIRED;
CREATE ROLE l9_graph_intelligence;
GRANT ACCESS ON DATABASE graphiti TO l9_graph_intelligence;
GRANT MATCH {*} ON GRAPH graphiti TO l9_graph_intelligence;
GRANT EXECUTE PROCEDURE gds.* ON DBMS TO l9_graph_intelligence;
GRANT EXECUTE FUNCTION gds.* ON DBMS TO l9_graph_intelligence;
GRANT EXECUTE PROCEDURE db.labels, db.relationshipTypes, db.propertyKeys,
      dbms.components ON DBMS TO l9_graph_intelligence;
GRANT ROLE l9_graph_intelligence TO l9_graph_reader;
```

No `WRITE`, `CREATE`, `SET PROPERTY`, `DELETE`, or `MERGE` privilege is granted.
GDS needs `dbms.security.procedures.unrestricted=gds.*` and
`dbms.security.procedures.allowlist=gds.*` on the server.

Neo4j Community has no role-based access control. There the barriers are the
static template registry and read-access sessions (the server rejects writes in
a read transaction), and the deployment must still use a credential distinct
from Graphiti's.

## Binding verification

`health()` proves more than connectivity:

1. authentication and database reachability;
2. Neo4j version/edition (`dbms.components`);
3. required Graphiti constructs (`Entity`, `Episodic`, `MENTIONS`, `RELATES_TO`);
4. schema fingerprint vs `graph_expected_schema_fingerprint`;
5. sampled Episodic `group_id` values use GraphScopeKey v1 (a namespace-keyed
   group means the adapter is bound to a pre-ADR-084 projection);
6. GDS version and the required stream procedures.

Record the fingerprint from the live-qualified database and set
`L9_MEMORY_GRAPH_SCHEMA_FINGERPRINT`; readiness then fails closed if required
constructs disappear or the adapter is pointed at a different database.
