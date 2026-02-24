# 📘 Knowledge Graph Loading & Inspection Guide
*(Ace Knowledge Graph + GPT)*

This document describes a lightweight, reproducible workflow for loading node/edge datasets into Ace Knowledge Graph using GPT and inspecting them interactively to identify hubs, clusters, and key actors.

---

## 1. Goal

Transform two seed datasets:

- `nodes.csv`
- `edges.csv`

into an interactive, non-hierarchical knowledge graph that supports:

- Hub discovery
- Ego-network inspection
- Cluster identification
- Progressive expansion

---

## 2. Prerequisites

ChatGPT with:

- File upload enabled
- Ace Knowledge Graph connector authenticated

Two CSV files:

### nodes.csv (minimum)

| column | meaning |
|------|--------|
| id | stable unique identifier |
| label | display name |
| type | person / org / event / concept / document / etc. |
| description (optional) | short explanation |
| aliases (optional) | alternative names |

### edges.csv (minimum)

| column | meaning |
|------|--------|
| source | node id |
| target | node id |
| type | relationship verb |
| description (optional) | extra context |

---

## 3. Core Principles

- Load small → medium → large
- Always normalize IDs
- Prefer subgraphs over full-network first
- Treat visualization as an exploration lens, not final truth

---

## 4. High-Level Workflow

1. Upload datasets
2. Normalize IDs & schema
3. Verify connector with tiny graph
4. Generate hub-focused view
5. Generate ego networks
6. Merge clusters
7. Attempt cleaned full network

---

## 5. Data Normalization Rules

- Convert IDs to kebab-case
  - `PER_MICHAEL_FARMER` → `michael-farmer`
- Ensure:
  - No spaces
  - No punctuation
  - Unique IDs

### Map node types into Ace categories

| raw type | ace type |
|---------|----------|
| person | skill |
| org / company | project |
| event | concept |
| document | concept |
| concept | concept |

---

## 6. Inspection Techniques

### A. Hub Scanning

Look for:
- Dense node centers
- Many edges radiating outward

### B. Ego Networks

Pick one node → display its immediate neighbors.

### C. Bridges

Nodes connecting two otherwise separate clusters.

### D. Cluster Recognition

Groups of nodes densely connected internally.

---

## 7. Interpretation Heuristics

- High-degree node → structural hub
- Bridge node → strategic connector
- Event node with many edges → narrative anchor
- Person node with multi-domain edges → power broker

---

## 8. Common Failure Modes

| Problem | Fix |
|-------|-----|
| Graph does not render | Reduce size |
| Layout too dense | Use ego networks |
| Edges unreadable | Remove metadata |
| Nodes duplicated | Normalize IDs |

---

## 9. Exploration Order (Recommended)

1. Hubs + neighbors
2. Ego network of top hub
3. Ego network of second hub
4. Merge two ego networks
5. Cleaned full network

---

## 10. Success Criteria

You should be able to answer:

- Who are the biggest hubs?
- Which clusters exist?
- Who connects clusters?
- Where does X sit in the network?

---

# 🧰 Template Prompt Pack

Copy/paste prompts below in sequence.

### 1. Declare Datasets

I have attached node and edge datasets to be used as the basis of a knowledge graph.

### 2. Normalize & Prepare

Normalize node IDs to kebab-case, map node types into Ace categories, and prepare the data for Ace Knowledge Graph visualization.

### 3. Verify Connector (Tiny Graph)

Generate a small sample knowledge graph with 3–5 nodes to verify the Ace Knowledge Graph connector is working.

### 4. Hub Discovery

Identify the top hubs by degree in edges.csv and generate a graph showing only those hubs.

### 5. Hubs + 1-Hop Neighbors

Generate a graph showing all hubs and every node directly connected to them.

### 6. Ego Network (Single Node)

Generate an ego-network centered on [NODE NAME], showing only that node and its immediate neighbors.

**Example:**

Generate an ego-network centered on Michael Farmer.

### 7. Merge Two Ego Networks

Generate a combined graph containing the ego-networks of [NODE A] and [NODE B].

### 8. Cleaned Full Network

Generate a cleaned full-network visualization with all nodes and edges, using minimal metadata and stable IDs.

### 9. Troubleshooting Reload

Reload a smaller subset graph (hubs + neighbors) to confirm the viewer is functioning.

### 10. Analytical Question Prompts

- Which nodes appear to be the most central hubs in this network?
- Which nodes act as bridges between clusters?
- Describe where [NODE] sits structurally in the network.

---

# 🎨 Visual Legend Standard (Colors, Sizes, Shapes)

This legend establishes a consistent visual language for interpreting graphs.

## Node Color → Entity Type

| Color | Type | Meaning |
|-----|-----|--------|
| 🔵 Blue | Person (skill) | Individual actors |
| 🟢 Green | Organization / Company (project) | Institutions, firms, groups |
| 🟣 Purple | Event | Incidents, scandals, milestones |
| 🟠 Orange | Concept / Ideology | Abstract ideas, movements |
| 🟡 Yellow | Document | Reports, declarations, books |
| ⚪ Gray | Unknown / Other | Temporary or uncategorized |

**Rule:** Color always encodes what something *is*, never importance.

## Node Size → Connectivity

| Size | Interpretation |
|-----|---------------|
| Small | Peripheral (degree = 1–2) |
| Medium | Moderately connected |
| Large | Hub |
| Extra Large | Super-hub |

**Rule:** Size represents degree centrality only.

## Node Border → Special Role

| Border Style | Meaning |
|-------------|--------|
| Thick outline | Bridge node (high betweenness) |
| Dashed outline | Inferred node |
| Double outline | Focus / selected node |

## Edge Style → Relationship Strength

| Style | Meaning |
|------|--------|
| Solid | Strong factual relationship |
| Dashed | Loose association |
| Dotted | Inferred / probabilistic |

## Edge Color → Relationship Category

| Color | Category |
|------|----------|
| Black | Structural (FOUNDED, CEO_OF, SUBSIDIARY_OF) |
| Green | Financial (FUNDED, INVESTED_IN, DONATED_TO) |
| Blue | Political (MEMBER_OF, TREASURER_OF) |
| Purple | Ideological / Influence |
| Orange | Event involvement |

### Legend Principle

- Color = what
- Size = how important
- Border = special role
- Edge color = type of relationship

Never overload one visual channel with multiple meanings.

---

# 🧱 Schema Template for Future Datasets

Use this template whenever adding new data sources.

## nodes.csv

id,label,type,description,aliases,source,confidence

### Field Definitions

| Field | Description |
|-----|-------------|
| id | Stable unique ID |
| label | Display name |
| type | person / org / event / concept / document |
| description | Short explanation |
| aliases | Pipe-separated alt names |
| source | Origin of data |
| confidence | high / medium / low |

## edges.csv

id,source,target,type,description,source_doc,confidence,start_date,end_date

### Field Definitions

| Field | Description |
|-----|-------------|
| id | Unique edge ID |
| source | Source node id |
| target | Target node id |
| type | Relationship verb |
| description | Human-readable explanation |
| source_doc | Evidence reference |
| confidence | high / medium / low |
| start_date | Optional |
| end_date | Optional |

### Relationship Verb Guidelines

Use verbs, not nouns.

**Good:**
- FOUNDED
- FUNDED
- CEO_OF
- MEMBER_OF
- SUBSIDIARY_OF
- INFLUENCED

**Avoid:**
- RELATED_TO
- ASSOCIATED_WITH

### ID Convention

- PER_*
- ORG_*
- EVT_*
- DOC_*
- CON_*

Then normalize to kebab-case for graph.

---

# ✅ Workflow Checklist

Use this as a quick operational checklist.

## Data Preparation

- nodes.csv present
- edges.csv present
- IDs unique
- Source/target IDs valid

## Normalization

- IDs converted to kebab-case
- Node types mapped
- Duplicates merged

## Connector Verification

- Tiny test graph renders

## Exploration

- Hub-only graph
- Hubs + neighbors
- Ego network of key node
- Combined ego networks

## Interpretation

- Identify hubs
- Identify bridges
- Identify clusters

## Expansion

- Add new dataset
- Normalize
- Validate
- Re-run hub scan

## Documentation

- Update schema
- Record assumptions
- Save screenshots

---

# 🧭 Operating Philosophy

Start small.
Validate.
Expand gradually.

A knowledge graph becomes useful through progressive refinement, not one massive load.

