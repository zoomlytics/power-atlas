# Reading List: Network-Based Analysis of Transnational Coordination Structures

## Purpose of This Reading List
This document organizes foundational and closely related works relevant to the development of a person-centric, multilayer network model for detecting emergent coordination structures beyond formal institutional boundaries. The works are grouped thematically to support conceptual grounding, methodological rigor, and experimental design.

---

# I. Elite Networks & Interlocking Directorates

## Group Relevance
This body of work examines how power and influence emerge from overlapping leadership roles across corporations, governments, and policy organizations. These works provide conceptual precedent for treating individuals (rather than institutions) as primary units of analysis and for understanding how dense elite clusters form persistent coordination structures.

### 1. C. Wright Mills — *The Power Elite* (1956)
- Early articulation of overlapping corporate, political, and military leadership networks.
- Frames power as embedded in relational structure rather than formal office alone.
- Useful as a conceptual ancestor of person-centric meta-board mapping.

### 2. John Scott — *Networks of Power*
- Formalizes elite power analysis using social network methods.
- Provides methodological grounding for analyzing interlocking directorates.
- Bridges classical sociology and quantitative network science.

### 3. G. William Domhoff — *Who Rules America?*
- Longitudinal mapping of corporate boards, policy groups, and foundations.
- Demonstrates reproducible patterns of dense elite clustering.
- Offers empirical strategies for assembling interlock datasets.

---

# II. Multilayer & Multiplex Network Theory

## Group Relevance
These works provide the mathematical and algorithmic foundation for modeling networks with multiple types of edges and interactions. This is essential for constructing a multiplex graph that includes corporate, governmental, financial, academic, and NGO ties simultaneously.

### 4. Stefano Boccaletti et al. — *Multilayer Networks* (2014)
- Formal definitions of multiplex and multilayer graph structures.
- Community detection approaches across layers.
- Foundational for modeling overlapping relational dimensions.

### 5. Mark Newman — *Networks: An Introduction*
- Comprehensive introduction to network metrics and community detection.
- Covers modularity, centrality, and hierarchical structure.
- Serves as core technical reference for algorithm selection.

### 6. Albert-László Barabási — *Network Science*
- Covers scale-free networks and hub formation.
- Explains emergence of hierarchical structure in large systems.
- Relevant to understanding why coordination may collapse into a small number of dense clusters.

---

# III. Block Models & Latent Community Detection

## Group Relevance
These works treat communities as latent probabilistic structures rather than observed categories. This aligns closely with the goal of detecting emergent coordination clusters without imposing legal or institutional boundaries.

### 7. Paul W. Holland et al. — *Stochastic Blockmodels*
- Introduces probabilistic modeling of community structure.
- Treats group membership as latent variable inferred from edge patterns.
- Useful for modeling emergent coordination blocs.

### 8. Stephen E. Fienberg — *Bayesian Analysis of Networks*
- Bayesian approaches to network modeling.
- Supports probabilistic community membership assignments.
- Aligns with soft, overlapping cluster detection and eligibility modeling.

---

# IV. Career Networks & Mobility as Graph Dynamics

## Group Relevance
These works examine how careers and opportunities flow through relational networks. They support the idea of modeling individual trajectories and eligibility as movements through network state space.

### 9. Mark Granovetter — *The Strength of Weak Ties*
- Demonstrates that job mobility flows through network connections.
- Highlights importance of bridging ties.
- Provides foundation for trajectory-based career modeling.

### 10. Mark Granovetter — *Getting a Job*
- Empirical study of labor markets as network-mediated systems.
- Shows resumes act as proxies for relational access.
- Supports the concept of career capital as portable network position.

### 11. Rob Cross et al. — *Networks in the Knowledge Economy*
- Maps informal influence networks within organizations.
- Shows divergence between formal hierarchy and functional influence.
- Demonstrates internal “shadow structures” relevant to basin modeling.

---

# V. Networked Governance & Transnational Coordination

## Group Relevance
These works examine governance beyond traditional state boundaries, framing institutions as networked systems. They provide conceptual grounding for detecting coordination clusters that span multiple legal jurisdictions.

### 12. Anne-Marie Slaughter — *The Networked State*
- Argues that modern governance operates via transnational professional networks.
- Conceptual bridge between nation-states and relational coordination.
- Supports empirical exploration of supra-national network clusters.

### 13. Mark Mazower — *Governing the World*
- Historical account of global governance evolution.
- Shows emergence of supranational coordination mechanisms.
- Contextualizes long-term structural layering above nation-states.

---

# VI. Hidden Structure & Capability Inference

## Group Relevance
These works show how latent capabilities and structural groupings can be inferred from relational data without relying on formal classifications.

### 14. Ricardo Hausmann et al. — *The Atlas of Economic Complexity*
- Infers productive capabilities of countries from trade network structure.
- Demonstrates how hidden structure emerges from relational patterns.
- Provides methodological inspiration for detecting coordination blocs from person-level data.

---

# Suggested Reading Order
1. Newman — foundational network methods
2. Boccaletti — multilayer extensions
3. Holland / Fienberg — probabilistic community modeling
4. Barabási — hierarchical structure & hubs
5. Granovetter — mobility and relational opportunity
6. Scott / Domhoff — elite network mapping
7. Slaughter / Mazower — transnational governance context
8. Hausmann — inference of latent structure from relational data

---

# How These Works Integrate Into Our Study

Together, these materials support:
- Person-centric node modeling
- Multilayer edge construction
- Overlapping community detection
- Recursive compression into meta-structures
- Trajectory-based career state modeling
- Empirical inference of coordination clusters independent of legal boundaries

This reading set forms the theoretical and methodological backbone for the proposed experimental design.

---

# Literature Gap Statement

While the above works collectively address elite networks, multilayer graph theory, latent community detection, career mobility, and transnational governance, no existing framework integrates all of the following into a single operational system:

- Planetary-scale person-centric multiplex networks
- Overlapping probabilistic community detection across many relational layers
- Recursive compression of detected communities into higher-order coordination units
- Explicit modeling of individual trajectories as continuous paths through network-state space
- Eligibility defined as probabilistic reachability of future states

The proposed study fills this gap by unifying these components into an end-to-end empirical pipeline for detecting emergent transnational coordination structures without relying on predefined institutional categories.

---

# Methodological Extraction Notes (By Entry)

### C. Wright Mills — *The Power Elite*
**Key Methods/Concepts:** Qualitative interlock mapping, elite overlap analysis
**Extraction Notes:** Use as conceptual grounding; operationalize by constructing bipartite graphs (people–institutions) and projecting to people–people networks.

### John Scott — *Networks of Power*
**Key Methods/Concepts:** Social network analysis of elites, block modeling
**Extraction Notes:** Apply centrality metrics and block models to detect elite clusters.

### G. William Domhoff — *Who Rules America?*
**Key Methods/Concepts:** Interlocking directorate datasets, longitudinal comparison
**Extraction Notes:** Build time-indexed interlock matrices; analyze cluster persistence.

### Stefano Boccaletti et al. — *Multilayer Networks*
**Key Methods/Concepts:** Supra-adjacency matrices, multilayer modularity
**Extraction Notes:** Represent layers using supra-adjacency tensors; apply multilayer community detection.

### Mark Newman — *Networks: An Introduction*
**Key Methods/Concepts:** Modularity maximization, centrality measures
**Extraction Notes:** Baseline algorithms for community detection and node feature vectors.

### Albert-László Barabási — *Network Science*
**Key Methods/Concepts:** Preferential attachment, scale-free degree distributions
**Extraction Notes:** Test for power-law degree distributions; anticipate hub formation.

### Paul W. Holland et al. — *Stochastic Blockmodels*
**Key Methods/Concepts:** Probabilistic block models
**Extraction Notes:** Fit SBMs to infer latent communities and edge probabilities.

### Stephen E. Fienberg — *Bayesian Analysis of Networks*
**Key Methods/Concepts:** Bayesian SBMs, posterior inference
**Extraction Notes:** Estimate community membership probabilities and uncertainty.

### Mark Granovetter — *The Strength of Weak Ties*
**Key Methods/Concepts:** Tie strength, bridging ties
**Extraction Notes:** Weight edges by frequency/duration; identify brokers.

### Mark Granovetter — *Getting a Job*
**Key Methods/Concepts:** Network-mediated job mobility
**Extraction Notes:** Validate career transitions against network proximity.

### Rob Cross et al. — *Networks in the Knowledge Economy*
**Key Methods/Concepts:** Organizational network analysis (ONA)
**Extraction Notes:** Map informal influence layers within firms.

### Anne-Marie Slaughter — *The Networked State*
**Key Methods/Concepts:** Transgovernmental networks
**Extraction Notes:** Add governmental professional ties as layers.

### Mark Mazower — *Governing the World*
**Key Methods/Concepts:** Historical institutional evolution
**Extraction Notes:** Use as contextual validation, not algorithmic input.

### Ricardo Hausmann et al. — *The Atlas of Economic Complexity*
**Key Methods/Concepts:** Network-based latent capability inference
**Extraction Notes:** Adapt fitness–complexity or related iterative scoring to people–community graphs.



---

# Methods-to-Pipeline Mapping Table

This table maps extracted methods to specific stages of the proposed experimental pipeline.

| Pipeline Stage | Objective | Methods / Algorithms | Source Anchors | Implementation Notes |
|---------------|------------|----------------------|----------------|----------------------|
| 1. Data Assembly (ETL) | Construct person-centric multiplex dataset | Bipartite projection (people–institution to people–people) | Mills, Domhoff | Build bipartite graph B(P,I); project via A = B B^T with weighting controls |
| 2. Layer Construction | Define relational layers | Supra-adjacency matrices | Boccaletti | Construct supra-adjacency matrix A_multi combining intra- and inter-layer edges |
| 3. Baseline Metrics | Characterize node positions | Degree, betweenness, eigenvector centrality | Newman | Compute centrality vector C_i = (k_i, b_i, e_i, ...) per layer and aggregated |
| 4. Structural Pattern Detection | Detect latent communities | Multilayer modularity, Infomap | Newman, Boccaletti | Optimize multilayer modularity Q_multi; allow overlap where applicable |
| 5. Probabilistic Community Modeling | Infer soft memberships | Stochastic Block Models (SBM), Bayesian SBM | Holland, Fienberg | Estimate P(z_i = k | A); allow mixed-membership where appropriate |
| 6. Hierarchical Compression | Create meta-nodes | Community aggregation, graph renormalization | Barabási | Collapse detected communities into super-nodes; define inter-community edge weights |
| 7. Trajectory Modeling | Track state evolution over time | Temporal networks, state transition modeling | Granovetter, Newman | Represent G(t); estimate transition probabilities P(s_t+1 | s_t) |
| 8. Eligibility Estimation | Estimate reachable future states | Markov models, reachability analysis | Holland, Fienberg | Construct transition matrix T; compute multi-step reachability probabilities |
| 9. Influence & Brokerage Analysis | Identify cross-cluster bridges | Betweenness, structural holes metrics | Granovetter, Cross | Identify brokers via high betweenness or constraint scores |
| 10. Latent Capability Scoring | Infer coordination capacity of communities | Iterative fitness–complexity algorithms | Hausmann | Adapt iterative scoring F_c(n+1) = sum_i A_ci Q_i(n) (normalized) |
| 11. Stability and Validation | Test robustness | Perturbation tests, bootstrapped community detection | Newman | Re-run detection under noise; compute variation of information (VI) |

---

# Pipeline Flow Summary

1. Construct multiplex person-centric graph
2. Compute baseline structural metrics
3. Detect overlapping communities
4. Estimate probabilistic memberships
5. Compress communities into higher-order graph
6. Model temporal trajectories and eligibility
7. Score coordination capacity
8. Validate structural stability

This mapping operationalizes the reading list into a coherent experimental architecture.
