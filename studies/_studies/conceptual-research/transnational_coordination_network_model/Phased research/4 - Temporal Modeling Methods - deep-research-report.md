# Temporal Modeling Methods for Power Atlas

This report is **methods-only** (Phase 1 extraction) for temporally modeling evolving, person-centric **multiplex** networks with provenance, uncertainty, and reproducibility requirements. It synthesizes the required source anchors—entity["people","Mark Newman","network scientist"]’s entity["book","Networks: An Introduction","newman 2010 networks text"] (entity["organization","Oxford University Press","publisher oxford, uk"]), entity["people","Stefano Boccaletti","network physicist"] et al.’s entity["book","The structure and dynamics of multilayer networks","physics reports 2014 review"], entity["people","Paul W. Holland","statistician social networks"] et al.’s entity["book","Stochastic blockmodels: First steps","social networks 1983 paper"], entity["people","Stephen E. Fienberg","statistician bayesian networks"]’s work on probabilistic graphical modeling and dynamics, entity["people","Mark Granovetter","sociologist"]’s entity["book","The Strength of Weak Ties","american journal of sociology 1973"], and entity["book","The Atlas of Economic Complexity","hausmann hidalgo et al 2014"] (including its iterative bipartite-matrix inference lineage). citeturn2search12turn6view0turn21view0turn0search6turn34view0turn2search1turn2search29

## Formal Representations of Temporal Networks

A temporally evolving multiplex network can be treated as a time-indexed family of graphs
\[
\mathcal{G} = \{G(t): t\in\mathcal{T}\},\quad 
G(t)=\left(V(t),\{E^{[\ell]}(t)\}_{\ell\in\mathcal{L}}\right),
\]
where \(\mathcal{L}\) is a set of interaction layers (e.g., corporate, governmental, NGO), and each layer \(\ell\) has adjacency \(A^{[\ell]}(t)\) (binary or weighted). citeturn21view0turn37search18turn38view0

**Snapshot model (time-slicing).** Choose discrete slice boundaries \(t_1<\dots<t_T\) (or intervals \([t_s,t_{s+1})\)). Define per-slice multiplex snapshots \(G_s := G(t_s)\) or \(G_s := G([t_s,t_{s+1}))\). In adjacency form, store \(\{A^{[\ell]}_s\}_{s=1..T,\ell=1..|\mathcal{L}|}\). This is the dominant representation in temporal-network surveys because it enables re-use of static algorithms, but it introduces a **window-size/placement dependency** (temporal aliasing) and can blur causal ordering within the window. citeturn1search9turn18search2turn16search30turn3search32

**Time-aggregated model with decay weighting.** Construct a *single* weighted multiplex graph for a reference time \(T\) by decaying historical events:
\[
w^{[\ell]}_{ij}(T) \;=\; \sum_{e\in\mathcal{E}^{[\ell]}_{ij}} \kappa(e)\, \exp\!\left(-\frac{T - t(e)}{\tau}\right),
\]
where \(\mathcal{E}^{[\ell]}_{ij}\) is the multiset of edge-events between \(i\) and \(j\) in layer \(\ell\), \(t(e)\) is an event time (or end time), \(\tau\) is a decay constant, and \(\kappa(e)\) is a base weight (possibly incorporating event type strength or evidence confidence). This preserves recency while collapsing time into weights; it is computationally cheap for repeated scoring/ranking, but it **cannot represent time-respecting paths** (ordering constraints) except approximately. citeturn1search9turn18search10turn17search20

**Event-based edge streams (contact sequences / link streams).** Represent the temporal multiplex as an ordered event stream:
\[
\mathcal{S} \;=\; \{(u_k,v_k,\ell_k,t_k,\Delta t_k, x_k)\}_{k=1}^K,
\]
where \(x_k\) stores attributes (source/evidence pointer, confidence, role label, capacity), and \(\Delta t_k\) may encode duration (instantaneous when \(\Delta t_k=0\)). This representation is the most faithful to “time as first-class,” supports time-respecting paths natively, and can be mapped to continuous-time stochastic process models (point processes, hazards). Its costs are higher ingestion volume, more expensive indexing, and more complex algorithms (often requiring specialized reachability or event-time inference). citeturn1search9turn3search32turn17search0turn17search1turn34view0

**Supra-adjacency / time-layer construction (time-unfolded multilayer).** Embed time into a multilayer (or “multislice”) supergraph with node copies \((i,s)\) per time slice \(s\). In block-matrix form, a common construction is
\[
\mathbf{A}^{\text{supra}} =
\begin{bmatrix}
A_1 & C_{12} & 0 & \cdots\\
C_{21} & A_2 & C_{23} & \cdots\\
0 & C_{32} & A_3 & \cdots\\
\vdots & \vdots & \vdots & \ddots
\end{bmatrix},
\]
where \(A_s\) can itself be multiplex (either an aggregated within-slice adjacency or a multiplex-to-single-slice lift), and \(C_{s,s+1}\) are **interslice couplings** (often diagonal: connect \(i\) at \(s\) to \(i\) at \(s+1\) with weight \(\omega\)). This representation is explicitly supported in multilayer frameworks and underlies multislice community modeling and temporal centrality trajectories. citeturn22view1turn20view2turn18search7turn4search26turn37search18

image_group{"layout":"carousel","aspect_ratio":"16:9","query":["time-unfolded temporal network supra-adjacency diagram","multilayer network supra adjacency matrix schematic","multislice network community detection schematic","temporal edge stream diagram network science"],"num_per_query":1}

**Continuous-time dynamic graphs (edge-existence function or point process).** Model edges as a function \(E(t)\) (presence/absence) or as random events with intensity \(\lambda^{[\ell]}_{ij}(t)\). Example: a (possibly self-exciting) temporal point process model for events between \(i\) and \(j\),
\[
\lambda^{[\ell]}_{ij}(t) = \mu^{[\ell]}_{ij} + \sum_{t_k < t} g(t-t_k;\theta),
\]
which supports fine-grained timing, burstiness, and causal event ordering at the cost of stronger modeling assumptions and more complex inference. citeturn17search1turn17search21turn17search0turn34view0

### Memory/computational tradeoffs and multiplex suitability

Snapshot and decay-aggregated representations are **memory-efficient** and easy to scale with standard sparse matrices; however, event streams and supra-adjacency are better aligned with *structural* time questions (time-respecting reachability, persistence, transitions). Temporal-network reviews emphasize that windowing/aggregation can distort measured structure and dynamics; this is a central stability risk in any \(G(t)\) design. citeturn1search9turn18search2turn18search6

Multiplex compatibility differs by representation: event streams naturally encode \(\ell\) as an event attribute; snapshots and supra-adjacency require either per-layer matrices or an explicit multilayer data model (tensor/supra-matrix) as formalized in multilayer foundations. citeturn21view0turn22view1turn37search18

### Compatibility with property-graph storage and entity["organization","Apache AGE","postgresql graph extension"]

A property graph can store temporal multiplex data by modeling:

- **Nodes**: `Person`, `Institution`, etc.  
- **Edges**: typed relationship edges (layer \(\ell\) as label or property), with properties `(valid_from, valid_to, observed_at, weight, confidence, evidence_id)`.

This fits entity["organization","Apache AGE","postgresql graph extension"]’s “graph in PostgreSQL” approach, which supports nodes/edges with properties and querying via openCypher integrated with SQL. The key architectural point is that supra-adjacency and most temporal inference are typically computed in Python, while the database stores (i) raw temporal evidence edges and (ii) derived “views” (snapshots, decayed weights, community assignments) with lineage metadata. citeturn2search6turn2search2turn22view1turn1search9

Known failure modes at this layer include: (a) encoding time only as a string property without indexes; (b) mixing evidence edges and derived edges without provenance separation; (c) attempting to persist massive supra-graphs directly in the DB (explodes edge count and query complexity). citeturn2search6turn2search3turn22view1

## Temporal Community Modeling

Let \(\Pi_t\) be a partition (hard clustering) of nodes at time slice \(t\), or \(\pi_i(t)\in\Delta^{K-1}\) be a soft membership vector for node \(i\) over \(K\) groups.

### Persistence metrics and cross-time partition distance

A basic persistence workflow is: detect partition \(\Pi_t\) per slice, then **align communities across slices** by maximizing overlap (e.g., bipartite matching on community–community Jaccard overlap):
\[
\mathrm{Jaccard}(C^a_t, C^b_{t+1}) = \frac{|C^a_t \cap C^b_{t+1}|}{|C^a_t \cup C^b_{t+1}|}.
\]
From the aligned mapping, compute “birth/death/split/merge/continue” events—an approach widely used in temporal community tracking frameworks. citeturn19search24turn19search8turn18search37

Partition-to-partition distances that do **not** require alignment are often preferred for robustness checks. A standard is **Variation of Information (VI)** between partitions \(\Pi_t,\Pi_{t+1}\):
\[
\mathrm{VI}(\Pi_t,\Pi_{t+1}) = H(\Pi_t)+H(\Pi_{t+1}) - 2I(\Pi_t;\Pi_{t+1}),
\]
where \(H\) is entropy of the cluster label distribution and \(I\) is mutual information. VI is a metric on partitions and provides a stable, permutation-invariant measure of change across time slices. citeturn1search2turn1search10

**Stability testing strategy.** In temporal settings, use VI (or related information measures) in two roles: (i) *adjacent-slice drift* \(\mathrm{VI}(\Pi_t,\Pi_{t+1})\); and (ii) *run-to-run variability* \(\mathrm{VI}(\Pi_t^{(r)},\Pi_t^{(r')})\) over random seeds or bootstrap/perturbation variants, then summarize as a distribution per \(t\). This directly operationalizes “community persistence vs instability” as a measurable property, without interpreting content. citeturn1search2turn18search1turn18search0

### Multislice modularity and community persistence via coupling

Multislice community detection treats time slices as layers coupled by interslice edges. A canonical modularity form (for slice indices \(r,s\)) includes an interslice coupling \(\omega\) that penalizes rapid community label switching across time-copies of the same node:
\[
Q_{\text{multislice}} = \frac{1}{2\mu}\sum_{i j r s}
\left[
\left(A_{ij}^{(s)}-\gamma_s \frac{k_i^{(s)}k_j^{(s)}}{2m_s}\right)\delta_{sr}
+ \delta_{ij}\,C_{jrs}
\right]\delta\!\left(g_{is},g_{jr}\right),
\]
where \(C_{jrs}\) encodes interslice coupling for node \(j\), \(\gamma_s\) is a resolution parameter, and \(g_{is}\) is the community label of node \(i\) in slice \(s\). This provides an explicit persistence mechanism: higher coupling encourages temporally smooth communities; lower coupling allows rapid change. citeturn20view2turn18search7

**Known degeneracy issues.** Modularity-based methods exhibit (a) “resolution limit” phenomena and (b) extreme degeneracy (many near-optimal but structurally different solutions), which complicates longitudinal comparisons unless you use consensus/ensemble stabilization. citeturn18search0turn18search4turn18search37

**Sensitivity to window size.** Snapshot choice impacts edge density and apparent community structure; empirical studies of aggregation emphasize that different window sizes can yield qualitatively different network statistics. In temporal community pipelines, this makes “window sensitivity sweeps” mandatory (see Validation section). citeturn18search2turn1search9turn18search6

### Dynamic SBM and state-space block models

A temporal extension of entity["book","Stochastic blockmodels: First steps","social networks 1983 paper"] treats community labels as latent and time-dependent. In a discrete-time dynamic SBM, one common form is:

- latent group \(Z_i(t)\in\{1,\dots,K\}\),
- Markov evolution \(P(Z_i(t+1)=b\mid Z_i(t)=a) = \Phi_{ab}\),
- conditional edge distribution
\[
Y_{ij}(t)\mid Z_i(t)=a,Z_j(t)=b \sim \mathcal{F}\left(\theta_{ab}(t)\right),
\]
where \(\mathcal{F}\) can be Bernoulli (binary edges) or a weighted family (including zero-inflation for sparsity).

This “SBM + independent Markov chains on memberships” is explicitly developed in dynamic SBM work to address label switching and to provide interpretable group trajectories across time. citeturn0search6turn24view0turn1search7

A *state-space* variant instead places temporal dynamics on the block connectivity parameters \(\theta_{ab}(t)\) via a latent linear dynamical system (e.g., on logits), permitting smooth evolution of connection probabilities; inference may use filtering/smoothing approximations. citeturn15search2turn15search14turn24view0

**Hard vs soft membership evolution.**
- Hard (SBM): \(Z_i(t)\) is a single class; transitions are driven by \(\Phi\).
- Soft (mixed membership): each node has \(\pi_i(t)\in\Delta^{K-1}\) and edges are generated from role-pair draws; dynamic mixed-membership models often add a state-space or Markov evolution on \(\pi_i(t)\) to capture gradual role change. citeturn15search27turn15search15turn17search18turn28view0

**Dynamic SBM failure modes (methods-focused).** The literature flags several recurring issues:
- **Label switching / identifiability:** without temporal constraints, group labels can permute across time and make “group identity” ill-defined; dynamic SBM formulations explicitly discuss this and propose constraints/criteria to establish identifiability. citeturn24view0turn15search2  
- **Overfitting vs underfitting:** choosing \(K\) and temporal smoothness requires model selection or priors; Bayesian SBM treatments emphasize priors/hierarchies to mitigate overfitting and support model comparison. citeturn15search0turn15search8turn18search34  
- **Degeneracy in modularity-based comparators:** if you use modularity as a baseline, near-degenerate solutions can mimic “temporal change” purely via optimization noise. citeturn18search0turn18search1

## Trajectory Modeling as State Transitions

Trajectory modeling treats each person-node as moving through a **state space** defined by (i) community assignments, (ii) roles/centrality signatures, and (iii) layer participation.

### State definitions

Define three complementary representations for node \(i\) at time \(t\):

1) **Community state**  
Hard: \(Z_i(t)\in\{1,\dots,K\}\).  
Soft: \(\pi_i(t)\in\Delta^{K-1}\). citeturn24view0turn15search27

2) **Role/centrality vector**  
Let \(c_i(t)\in\mathbb{R}^p\) be a feature vector of centralities (degree, betweenness-like approximations, eigenvector/PageRank variants) computed per slice, possibly per layer. Temporal centrality frameworks treat \(\{c_i(t)\}_{t}\) as a trajectory and can be built naturally on supra-adjacency constructions (“supracentrality”) that couple node copies across time. citeturn4search26turn22view1

3) **Layer participation vector**  
Let \(d_i^{[\ell]}(t)\) be within-layer degree/strength. Then define \(p_i(t) = (d_i^{[1]}(t),\dots,d_i^{[|\mathcal{L}|]}(t))\), possibly normalized to a simplex to represent a “layer-mix profile.” Multilayer formalisms explicitly separate intra-layer structure from inter-layer coupling, motivating this as a first-class feature family. citeturn22view1turn21view0turn37search18

### Markov transition models

A baseline trajectory model is a first-order Markov chain on discrete states \(S\):

\[
\Pr(X_{t+1}=s'\mid X_t=s)=P_{ss'},\quad X_t\in S,
\]
where \(S\) can be the community labels, a discretized role space, or a joint product space \(S = \{1..K\}\times \mathcal{R}\times \mathcal{P}\) (community × role-bin × layer-profile-bin). Dynamic SBM work explicitly uses Markov evolution on memberships; graphical-model treatments emphasize that time provides ordering and supports state-space/HMM-style modeling choices. citeturn24view0turn34view0turn32view0

For non-stationary dynamics, use time-inhomogeneous transitions \(P(t)\):
\[
\Pr(X_{t+1}=s'\mid X_t=s)=P_{ss'}(t),
\]
and measure drift by \(\|P(t+1)-P(t)\|\) or via predictive likelihood comparisons. citeturn34view0turn17search18

### Higher-order path models and memory

Temporal networks often violate a first-order assumption: where a walk goes next may depend on where it came from. Higher-order models encode this by expanding the state to include the previous node (second order) or longer histories:
\[
\Pr(v_{n+1}=x \mid v_n=y, v_{n-1}=z)=P_{(z,y)\to(y,x)}.
\]
Second-order and variable-order models are explicitly developed for pathway data and can change community detection, ranking, and diffusion estimates relative to first-order aggregation. citeturn16search0turn16search4turn16search24turn18search34

### Reachability in time-respecting paths

A time-respecting (causal) path imposes increasing time along edges. Formally, a path \((v_0\to v_1\to\dots\to v_m)\) is time-respecting if there exist times \(t_1\le t_2\le\dots\le t_m\) such that edge \((v_{r-1},v_r)\) is active at \(t_r\) (or within allowed waiting-time constraints). Temporal-network references treat reachability as fundamentally different from static reachability under aggregation. citeturn1search9turn16search22turn16search14

**Multi-step reachability computation.** In discrete time, define per-slice adjacency \(A_t\) (or a transmission matrix \(T_t\)). Then the existence/probability of a length-\(k\) time-respecting walk can be computed via time-ordered products:
\[
M_{t\to t+k} = T_t\,T_{t+1}\cdots T_{t+k-1}.
\]
Matrix-based temporal reachability and “accessibility graph” constructions formalize this approach for time-respecting path existence under constraints. citeturn16search6turn16search3turn1search9

**Stationarity assumptions (explicit).** If you collapse to a single \(P\) (time-homogeneous Markov chain), you assume transition stationarity over the analysis horizon; if \(P(t)\) varies, you instead assume piecewise stationarity or treat \(P(t)\) as a stochastic process to be filtered/smoothed. These choices determine whether long-horizon reachability is computed by \(P^k\) or by \(\prod_t P(t)\). citeturn34view0turn17search18turn15search2

## Eligibility as Probabilistic Reachability

Define **Eligibility** as a *methods-level operator*:
\[
\mathrm{Elig}(i\!\to\!\mathcal{T};k) \;=\; \Pr\!\left(\exists\, t'\le t+k \text{ such that } X_i(t')\in\mathcal{T}\;\middle|\;X_i(t)=s_0\right),
\]
where \(X_i(t)\) is a chosen state representation (community, role-bin, joint state), \(\mathcal{T}\subseteq S\) is a target state set, and \(k\) is a step horizon (or replace \(k\) with a time horizon \(\Delta t\)). This is explicitly *reachability-as-probability*, with no substantive interpretation of what \(\mathcal{T}\) “means.” citeturn16search14turn16search22turn1search9

### Markov chain formalization: absorbing-state construction

For a time-homogeneous chain on finite \(S\), convert target states \(\mathcal{T}\) into absorbing states. With transition matrix ordered as
\[
P=\begin{bmatrix}
Q & R\\
0 & I
\end{bmatrix},
\]
where \(Q\) is transient-to-transient and \(R\) is transient-to-absorbing, the **fundamental matrix** is
\[
N = (I-Q)^{-1} = \sum_{n=0}^{\infty} Q^n.
\]
Absorption probabilities are given by \(B = NR\). These are standard results for absorbing Markov chains and provide a closed-form for eventual reachability to \(\mathcal{T}\) under stationarity. citeturn16search33turn16search9turn16search13

For a **finite-horizon \(k\)**, compute \(k\)-step reachability by truncation:
\[
\Pr(\text{hit }\mathcal{T}\text{ by }k) = 1 - \Pr(\text{remain transient for }k)
\]
with \(\Pr(\text{remain transient for }k)\) derived from \(Q^k\) (or from recursion). citeturn16search33turn16search14

### Monte Carlo simulation alternatives

When the state space is large, transitions are time-inhomogeneous, or the graph is event-based, estimate eligibility by simulating \(M\) trajectories under the stochastic transition model and computing the empirical hit rate. Monte Carlo is also the natural choice when confidence/uncertainty is modeled hierarchically and you need to propagate distributional uncertainty through the reachability operator. citeturn17search20turn17search18turn16search14

### Bayesian updating options

A Bayesian approach treats transition parameters as random variables, updated as new (time-stamped) evidence arrives. Two common patterns:

- **Dirichlet–multinomial** updating for discrete \(P_{ss'}\) (counts of transitions), enabling posterior predictive eligibility intervals.
- **Dynamic Bayesian networks / state-space models** where hidden states evolve over time and observations arrive with uncertainty; time ordering is explicit and inference uses filtering/smoothing (exact or approximate). citeturn17search18turn17search2turn34view0turn17search26

entity["people","Stephen E. Fienberg","statistician bayesian networks"]’s graphical-model framing explicitly distinguishes discrete-time transition models from continuous-time stochastic process models for event data, which maps directly onto a choice between (i) DBN/HMM-style eligibility and (ii) hazard/intensity-based eligibility over event streams. citeturn34view0turn17search0turn17search1

### Where uncertainty propagates and how confidence integrates

In an evidence-first system, uncertainty enters at least three points:

1) **Edge/event uncertainty**: each event has confidence \(c_e\) and provenance; treat this as (a) a weight in constructing \(T_t\) or (b) a probabilistic observation model for edge existence. citeturn2search3turn34view0turn17search20  
2) **Community/state uncertainty**: community labels are latent (SBM) or soft (mixed-membership); eligibility should integrate over \(p(Z\mid\text{data})\) rather than conditioning on a single MAP partition when feasible. citeturn15search27turn15search0turn24view0  
3) **Model uncertainty**: \(K\), window size, coupling strength \(\omega\), and decay \(\tau\) affect estimates; treat outputs as “hypothesis distributions” tied to run configurations rather than fixed facts. citeturn20view2turn18search2turn15search0

Known failure modes include: (a) collapsing confidence into a single deterministic weight without tracking distributional effects; (b) mixing posterior uncertainty with optimization degeneracy (e.g., modularity degeneracy) without separating the two; and (c) assuming stationarity when transitions drift. citeturn18search0turn34view0turn1search9

## Temporal Weighting & Decay

Temporal weighting defines how evidence contributes to edges and derived structures over time.

### Exponential decay weighting

A standard recency model uses
\[
w_e(T)=w_{0,e}\exp\!\left(-\frac{T-t_e}{\tau}\right),
\quad
w_{ij}^{[\ell]}(T)=\sum_{e\in\mathcal{E}^{[\ell]}_{ij}} w_e(T).
\]
This is appropriate when relevance is assumed to decline continuously with age and when you need a smooth, differentiable weighting function. It is also compatible with streaming updates (update weights incrementally). citeturn18search10turn1search9

**Failure mode:** overly small \(\tau\) can create volatile networks dominated by noise bursts; overly large \(\tau\) over-smooths and erases temporal transitions. Temporal-network surveys emphasize that aggregation choices can strongly affect observed structure, making \(\tau\)-sweeps part of stability testing. citeturn1search9turn18search2

### Sliding-window aggregation

Define a window \([T-\Delta, T]\) and aggregate events within it:
\[
w_{ij}^{[\ell]}(T;\Delta)=\sum_{e: t_e\in[T-\Delta,T]} w_{0,e}.
\]
This is appropriate when you want interpretability (“active in last \(\Delta\)”) and bounded memory, and when your downstream algorithms assume snapshots. Empirical studies show that window size/placement changes network density and clustering patterns, so \(\Delta\) is a sensitivity-critical hyperparameter. citeturn18search2turn1search9turn16search30

**Failure mode:** boundary artifacts—events just outside the window drop to zero influence, often producing discontinuities in time-series of network measures. citeturn18search2turn1search9

### Event-count normalization (rate and exposure corrections)

When activity volume varies over time, normalize by exposure:
\[
\tilde w_{ij}^{[\ell]}(t) = \frac{w_{ij}^{[\ell]}(t)}{\sum_{u<v} w_{uv}^{[\ell]}(t)+\epsilon}
\quad\text{or}\quad
\tilde w_{ij}^{[\ell]}(t)=\frac{\#\text{events}(i,j,\ell,t)}{\Delta t}.
\]
This reduces spurious “structural change” caused purely by global activity surges. In temporal event modeling, similar normalization appears as baseline intensity vs excitation (separating overall rate from interaction-specific dynamics). citeturn17search1turn17search21turn1search9

**Failure mode:** normalization can hide real regime shifts if global volume changes are themselves structurally meaningful to the modeling objective; the methodological safeguard is to store both raw and normalized series as parallel derived layers with clear lineage. citeturn2search3turn2search7turn17search20

### Recency bias tradeoffs

Recency bias improves responsiveness but can harm persistence estimation (communities appear short-lived). Temporal-network methodology emphasizes that you must choose weighting consistent with the temporal resolution of hypotheses and then validate sensitivity to this choice. citeturn1search9turn18search2turn20view2

## Architecture & Provenance Implications

Power Atlas requires evidence-first, time-aware modeling with confidence scoring and derived entities treated as hypotheses. Methodologically, this implies an explicit separation of **observed evidence** from **derived artifacts**, coupled by provenance graphs.

### Versioning snapshots and temporal views

Treat each temporal view (raw event stream, windowed snapshots, decayed aggregation, supra-graph materialization) as a versioned dataset:
- **Evidence layer**: immutable event records \((u,v,\ell,t,\Delta t,x)\) with source pointers.
- **View layer**: deterministic functions \(f_{\theta}\) producing derived edges or snapshots: \(G^{(\text{window},\Delta)}\), \(G^{(\text{decay},\tau)}\), etc.
- **Model layer**: derived entities (communities, trajectories, eligibility scores) stored as hypotheses with explicit run metadata.

This aligns with provenance standards that model entities, activities, and agents. citeturn2search3turn2search7turn2search31turn34view0

### Tracking algorithm runs and reproducibility

Use a run record \(R\) containing:
- input dataset/version identifiers (hashes of evidence query + parameters),
- algorithm identifier + version (e.g., git commit, container digest),
- parameter set \(\theta\) (window \(\Delta\), decay \(\tau\), coupling \(\omega\), \(K\), priors),
- random seeds and determinism flags,
- outputs (entity IDs created/updated) and summary diagnostics.

This mirrors workflow provenance extensions (plans linked to executions) built on top of the core provenance data model. citeturn2search3turn2search23turn2search39

### Storing temporal lineage in a graph database pipeline

In a PostgreSQL + entity["organization","Apache AGE","postgresql graph extension"] pipeline, a practical split is:

- Store **high-volume event data** in relational tables (partitioned by time) with indexes on \((u,v,\ell,t)\).
- Store **entity identities and relationships** as AGE nodes/edges, where each AGE edge points (by `evidence_id` or `evidence_query_id`) back to the relational evidence table.
- Store **derived artifacts** (community assignment per node per slice; eligibility scores per node per horizon) either as:
  - AGE node/edge properties with `(valid_from, valid_to, run_id, confidence)`; or
  - separate derived nodes (e.g., `CommunityHypothesis`) linked to member nodes with time-scoped edges, always keyed by `run_id`.

AGE’s documentation emphasizes graph database functionality on PostgreSQL and openCypher querying, making it suitable as a *serving* layer for temporal slices and lineage queries, while heavy temporal inference remains in Python. citeturn2search6turn2search2turn2search14turn2search3

**Known architectural failure modes (methods-only).**
- Conflating evidence with derived hypotheses in the same edge types without run IDs breaks reproducibility. citeturn2search3turn2search7  
- Recomputing snapshots/communities without storing parameterization prevents later stability audits; provenance standards exist to prevent this. citeturn2search3turn2search31  
- Attempting to represent the full supra-adjacency time-unfolded network as persistent AGE edges can create an artificial edge explosion; the recommended pattern is “compute supra in Python, store only outputs + lineage.” citeturn22view1turn2search6turn20view2

## Validation & Stability Framework

Temporal modeling requires explicit robustness checks because many outputs are sensitive to discretization, coupling, and optimization degeneracy.

### Edge perturbation tests

Perturb edges/events and measure stability of derived outputs:
- **Jackknife over events**: drop a random fraction \(p\) of events; recompute derived outputs; measure distances (VI for partitions; distributional shifts for eligibility probabilities).
- **Confidence-weight perturbation**: sample edge weights from confidence-calibrated distributions (e.g., \(w_e\sim \text{Beta}(\alpha_e,\beta_e)\) mapped to [0,1]) and propagate through the pipeline.

Modularity methods are especially sensitive due to near-degenerate solution landscapes; therefore stability must be assessed over perturbations and seeds, not assumed. citeturn18search0turn18search4turn18search1

### Window sensitivity tests

Systematically sweep time-slicing parameters:
- window length \(\Delta\),
- window stride (overlap vs non-overlap),
- placement (phase shift),
- decay constant \(\tau\) where applicable.

Empirical work shows that aggregation window size and placement can materially change observed structure; temporal-network methodology treats these as first-class hyperparameters requiring sensitivity profiling. citeturn18search2turn18search6turn1search9

### Layer-weight and coupling variation

For multiplex + time, sweep:
- per-layer weights \(\alpha_\ell\) in a combined objective,
- interslice coupling \(\omega\) in multislice modularity or supra-centrality,
- resolution \(\gamma\) where modularity-like objectives are used.

The multislice modularity framework explicitly introduces coupling as a parameter controlling temporal smoothness; varying it is a direct test of whether “persistence” is algorithmically imposed or data-supported. citeturn20view2turn18search7turn4search26

### Community stability thresholds

Define explicit thresholds that gate whether a derived community object is “stable enough to store” (as a hypothesis):
- **Within-slice stability:** median pairwise VI (or NMI) across reruns below a threshold.
- **Across-time continuity:** fraction of nodes retained from \(t\) to \(t+1\) above a threshold for a minimum duration.
- **Consensus clustering**: compute an ensemble of partitions and derive a consensus partition to reduce variance from stochastic algorithms; consensus clustering is proposed explicitly to enhance stability and is suitable for monitoring evolving structure over time. citeturn18search1turn18search5turn1search2

### Degeneracy detection

Detect and flag known degeneracies and identifiability risks:

- **Modularity degeneracy:** if many distinct partitions achieve near-identical objective values, report a degeneracy score (e.g., variance of VI among top-\(M\) solutions) and prefer consensus/ensemble methods over single outputs. citeturn18search0turn18search4turn18search1  
- **Dynamic SBM label-switching / identifiability:** require either (a) an explicit temporal constraint (Markov evolution on \(Z_i(t)\)) or (b) post-hoc alignment plus identifiability checks; dynamic SBM work discusses label-switching control and identifiability conditions as core methodological issues. citeturn24view0turn15search2turn1search7  
- **Model order sensitivity (higher-order paths):** compare first-order vs second-/variable-order models using likelihood/model selection; higher-order modeling work emphasizes that ignoring memory can change inferred structure and dynamics. citeturn16search0turn16search24turn18search34

### Practical robustness checklist for a Python + graph DB pipeline

A minimal audit artifact set per run should include: (i) window/decay/coupling parameters; (ii) seed set and number of reruns; (iii) VI/NMI stability summaries; (iv) degeneracy indicators; (v) provenance links from outputs to evidence and to run configs (using W3C PROV-style “entity–activity–agent” records). This makes temporal modeling reproducible and confidence-aware without embedding substantive interpretations into the modeling layer. citeturn2search3turn2search7turn18search0turn1search2turn34view0