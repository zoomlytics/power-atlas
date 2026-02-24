# Multilayer Network Formalism for Power Atlas

## Formal mathematical definition

A mathematically implementable multilayer formalism starts by separating **physical entities** (e.g., persons) from their **layered manifestations** (the same person appearing in different relation-types and/or time slices). Following the multilayer framing in entity["people","Stefano Boccaletti","network science author"] et al.’s *Multilayer Networks* review (2014), a general multilayer network allows (i) potentially different node sets per layer and (ii) explicit interlayer edges between node-layer tuples. In that unified view, “multiplex” networks and “temporal networks” become special cases with constrained interlayer structure. citeturn7view0

### A concrete implementation-ready object model

Let a multilayer network be
\[
M = (V,\; \mathcal{L},\; \mathcal{V}_M,\; E_M,\; w)
\]
where:

- \(V\) is the set of **physical nodes** (e.g., persons).
- \(\mathcal{L}\) is the set of **layers**. For Power Atlas, a practical choice is that each \(l\in\mathcal{L}\) corresponds to a relationship “mode” (financial tie, organizational co-membership, communication, etc.), optionally crossed with a discrete time slice. (This aligns directly with multilayer encodings of temporal and multiplex systems.) citeturn7view0turn8view2turn3search2
- \(\mathcal{V}_M \subseteq V \times \mathcal{L}\) is the set of **node-layer tuples** (state nodes), i.e., \((i,l)\) exists iff physical node \(i\) is present/valid in layer \(l\).
- \(E_M \subseteq \mathcal{V}_M \times \mathcal{V}_M\) is the set of **edges between node-layer tuples** (intralayer or interlayer).
- \(w: E_M \to \mathbb{R}\) assigns **weights** (e.g., confidence-weighted strengths) to edges; unweighted graphs are the special case \(w\in\{0,1\}\). The multilayer adjacency may also be treated as weighted in the underlying modularity derivation. citeturn9view0turn7view0

This object model deliberately includes \(\mathcal{V}_M\) explicitly: it is the bridge that makes “supra-adjacency” and tensorial representations unambiguous, and it matches how multislice community detection defines a combined “multislice strength” of node-slices. citeturn8view3turn7view0

image_group{"layout":"carousel","aspect_ratio":"16:9","query":["multiplex multilayer network diagram layers interlayer coupling","supra adjacency matrix block matrix multilayer network illustration","temporal network multilayer representation layers time slices diagram"],"num_per_query":1}

### Intralayer adjacency matrices \(A^{[l]}\)

For each layer \(l\in\mathcal{L}\), define the intralayer adjacency matrix
\[
A^{[l]} \in \mathbb{R}^{|V^{[l]}|\times |V^{[l]}|},\quad
A^{[l]}_{ij} = \begin{cases}
w\big((i,l),(j,l)\big) & \text{if } \big((i,l),(j,l)\big)\in E_M\\
0 & \text{otherwise}
\end{cases}
\]
where \(V^{[l]}=\{i\in V : (i,l)\in \mathcal{V}_M\}\).

This is exactly the “adjacency matrix of each layer” \(A^{[\alpha]}=(a_{ij}^{\alpha})\) used in Boccaletti’s notation. citeturn7view0

### Interlayer coupling matrices \(C\) (or \(A^{[l,m]}\))

For each ordered pair of layers \((l,m)\), define an interlayer (cross-layer) adjacency / coupling matrix
\[
C^{[l,m]} \in \mathbb{R}^{|V^{[l]}|\times |V^{[m]}|},\quad
C^{[l,m]}_{ij} =
\begin{cases}
w\big((i,l),(j,m)\big) & \text{if } \big((i,l),(j,m)\big)\in E_M\\
0 & \text{otherwise}
\end{cases}
\]
which corresponds to Boccaletti’s “interlayer adjacency matrix” \(A^{[\alpha,\beta]}=(a^{\alpha\beta}_{ij})\). citeturn7view0

For many practical multilayer designs (especially multiplex and temporal), \(C^{[l,m]}\) is usually **sparse and structured**, often restricted to **replica coupling**:
\[
C^{[l,m]}_{ij} = \omega_{l,m}\,\delta_{ij}
\]
meaning physical node \(i\) in layer \(l\) couples only to itself in layer \(m\), with coupling strength \(\omega_{l,m}\). Boccaletti explicitly defines multiplex networks as the special case where interlayer edges are only between counterpart nodes (replicas). citeturn7view0

### Supra-adjacency matrix \(\tilde{A}\)

Index node-layer tuples \((i,l)\in \mathcal{V}_M\) with a global index map \(\pi: \mathcal{V}_M \to \{1,\dots,|\mathcal{V}_M|\}\). The supra-adjacency matrix is then
\[
\tilde{A}_{\pi(i,l),\pi(j,m)} = 
\begin{cases}
A^{[l]}_{ij} & l=m\\
C^{[l,m]}_{ij} & l\neq m
\end{cases}
\]
So \(\tilde{A}\) is a block matrix with diagonal blocks \(A^{[l]}\) and off-diagonal blocks \(C^{[l,m]}\).

Boccaletti describes this “flattening/unfolding/matricization” explicitly: a multiplex can be mapped into a monolayer graph with \(N\times M\) nodes whose adjacency (the supra-adjacency) is written as a block matrix, with identity matrices between replica nodes in the simplest multiplex coupling. citeturn7view0

### Tensor representation (rank-4 adjacency tensor)

If you want a representation that remains explicit about “node index vs layer index” without committing early to a block matrix layout, tensor form is the cleanest baseline:

- entity["people","Manlio De Domenico","multilayer networks author"] et al. formalize multilayer adjacency as a rank-4 tensor \(M^{\alpha\tilde{\gamma}}_{\beta\tilde{\delta}}\) built from interlayer adjacency tensors \(C^\alpha_\beta(\tilde{h}\tilde{k})\), and note that flattening/matricization can produce an \(NL\times NL\) matrix representation for computational algorithms. citeturn21view0

A direct correspondence to the supra-adjacency is:
\[
\mathcal{M}_{i l}^{j m} \equiv w\big((i,l),(j,m)\big)
\]
with the understanding that “tensor indices” keep the node vs layer roles explicit. citeturn21view0turn7view0

### Multiplex vs general multilayer vs edge-colored graphs

**Multiplex networks.** A multiplex network is a constrained multilayer system where (i) all layers share the same node set and (ii) the only allowed interlayer edges connect a node to its counterpart (replica) in other layers:
\[
X_1 = \cdots = X_M = X,\quad E_{\alpha\beta}=\{(x,x):x\in X\}.
\]
This is exactly how Boccaletti defines multiplex as a special case of multilayer networks. citeturn7view0

**General multilayer networks.** In the most general case, layers have node sets \(X_\alpha\) that may differ, and interlayer edges \(E_{\alpha\beta}\) may connect arbitrary node pairs across layers (not just replicas). Boccaletti’s formal definition includes both intralayer adjacency \(A^{[\alpha]}\) and interlayer adjacency \(A^{[\alpha,\beta]}\) for arbitrary \(E_{\alpha\beta}\). citeturn7view0

**Edge-colored (edge-labeled) graphs.** Boccaletti notes that an “edge-labeled multigraph” (multidimensional network) can be modeled with triples \((u,v,d)\) where \(d\) is a label (“dimension”), i.e., multiple labeled edge types between the same node pair; and then mapped to multiplex layers by mapping each label to a layer. citeturn7view0  
Architecturally, an edge-colored graph can store relation types efficiently, but it does **not automatically encode** the multilayer semantics of (i) node replication, (ii) explicit interlayer coupling \(C\), or (iii) supra-Laplacians/supra-adjacency spectral constructs. Those require the node-layer tuple expansion and coupling edges (even if built on the fly). citeturn7view0turn21view0

**Implementation tradeoff summary (Power Atlas relevant).** If your downstream algorithms require model-consistent notions like “coupling the same person across relation-modes and time slices,” then you need a multilayer formalism (node-layer tuples + \(C\)), even if you store base data in an edge-colored property graph and *materialize* the supra representation only for analytics. The flattening step is useful computationally but changes the object (a single physical node becomes multiple node-layer tuples), so results must be interpreted back through the quotient map from tuples to physical nodes. citeturn7view0turn21view0

## Community detection in multilayer networks

Community detection in multilayer settings is best treated as: (i) a **quality function** defined on partitions of node-layer tuples, plus (ii) a **heuristic optimizer** whose outputs are typically non-unique and parameter-sensitive. The Power Atlas architectural implication is that **community outputs are derived artifacts**, not canonical ground truth, and must carry parameter and provenance lineage.

### Baseline: single-layer modularity and its spectral form

In a single layer, modularity compares observed within-community connectivity to that expected under a null model (often the configuration model). In entity["people","Mark Newman","network scientist"]’s formulation, for adjacency \(A_{ij}\), degrees \(k_i\), and total edges \(m\), modularity can be expressed as the sum over within-group pairs of \(A_{ij} - \frac{k_i k_j}{2m}\), and leads to the modularity matrix \(B_{ij} = A_{ij} - \frac{k_i k_j}{2m}\), enabling spectral community detection methods. citeturn9view0

A standard compact form is:
\[
Q = \frac{1}{2m}\sum_{ij}\left(A_{ij}-\frac{k_i k_j}{2m}\right)\delta(g_i,g_j),
\]
with weighted/multi-edge generalizations handled by allowing \(A_{ij}\) to take non-binary values. citeturn9view0

### Multilayer modularity \(Q_{\text{multi}}\) via the multislice framework

The most widely implemented modularity generalization for multilayer systems is the **multislice modularity** of entity["people","Peter J. Mucha","applied mathematician"] et al. (Science, 2010). They construct a “multislice network” of node-slices (node-layer tuples) with intralayer adjacency \(A_{ij}^s\) and interslice couplings \(C_{jrs}\) connecting a node \(j\) to itself across slices \(r,s\). citeturn8view2turn8view1

One canonical form they derive is:
\[
Q_{\text{multislice}}=\frac{1}{2\mu}\sum_{i j r s}\left[\left(A^{s}_{ij}-\gamma_s \frac{k^{s}_i k^{s}_j}{2m_s}\right)\delta_{sr} + \delta_{ij}\,C_{jrs}\right]\delta(g_{is},g_{jr}),
\]
where:
- \(g_{is}\) is the community label of node \(i\) in slice \(s\);
- \(m_s\) is total weight in slice \(s\);
- \(\gamma_s\) is a **resolution parameter** per slice (controlling typical community size);
- \(C_{jrs}\) is the **interslice coupling** (often simplified to a constant); and
- \(2\mu\) is the total strength over all node-slices (intra + interslice). citeturn8view2turn8view3

This framework directly supports Power Atlas needs because it treats:
- **multiplex link types** as categorical slices with all-to-all coupling between a node and itself across slices, and
- **temporal networks** as ordered slices with coupling between neighboring time slices, exactly as described in Mucha’s own schematics. citeturn8view1turn8view2turn7view0

### Role of interlayer coupling \(\omega\)

In practice, many implementations specialize \(C_{jrs}\) to binary or constant weights:
\[
C_{jrs} =
\begin{cases}
\omega & \text{if node } j \text{ is coupled between slices } r \leftrightarrow s\\
0 & \text{otherwise}
\end{cases}
\]
Mucha et al. explicitly interpret this coupling parameter (they denote it \(\Omega\) / \(\Sigma\) in the paper’s text) as controlling “the extent of inter-slice correspondence of communities,” and note that at \(\Omega=0\) (no coupling) there is no benefit from extending communities across slices (so each slice partitions independently). citeturn8view2

Architecturally, \(\omega\) is not a “mere hyperparameter”: it defines the *implicit prior* over whether a person’s community assignment should be stable across layers/time relative to intralayer evidence. This perspective is formalized in later work connecting modularity to inference models. citeturn14search8turn14search2

### Optimization methods and practical solvers

Modularity maximization is computationally hard in general, so most usable methods are heuristics (greedy, multilevel, stochastic). Newman emphasizes heuristic approaches and develops spectral methods using the modularity matrix. citeturn9view0turn11view1

For multislice modularity specifically, a common practical solver family is the generalized Louvain method (multilevel node moving + aggregation) implemented in the open-source **GenLouvain** codebase. citeturn19search0  
For large-scale production workflows, related multilevel modularity optimizers such as Louvain/Leiden are widely available in graph analytics ecosystems (though many are single-layer by default). citeturn16search9turn16search1

### Resolution limit, degeneracy, and stability in multilayer context

**Resolution limit.** A core limitation of modularity is the resolution limit: modularity optimization can fail to resolve communities below a scale that depends on total network size/total edges and inter-community connectivity, even when smaller modules exist unambiguously. citeturn11view1  
Multilayer modularity introduces additional parameters (\(\gamma_s\), \(\omega\)), which means “resolution” becomes a *2D (or higher) parameter space problem* rather than a single-scale issue. This is one reason systematic parameter exploration is unavoidable for research-grade results. citeturn8view2turn13view1

**Degeneracy and solution multiplicity.** entity["people","Benjamin H. Good","network science researcher"], entity["people","Yves-Alexandre de Montjoye","data scientist"], and entity["people","Aaron Clauset","computer scientist"] show that modularity landscapes can exhibit “extreme degeneracies,” often admitting an exponential number of distinct high-scoring partitions and lacking a clear global maximum; different heuristics can disagree substantially. citeturn12view0  
This phenomenon carries over to multilayer settings because multislice modularity is still an additive objective optimized by heuristics, now with even larger parameter and state spaces. citeturn13view1turn12view0turn8view2

**Stability tools.** Two practical responses have emerged in the literature:
- Post-processing and pruning across parameter sweeps (e.g., the CHAMP algorithm of entity["people","William H. Weir","network scientist"] et al.) to identify which partitions are “somewhere optimal” in parameter space. citeturn14search3  
- Explicit recognition that multilayer modularity requires selecting resolution and coupling parameters and that heuristic runs can yield different near-optimal outputs even at fixed parameters; parameter-space mapping and pruning frameworks treat this as a first-class problem. citeturn13view1

### Aggregated graph vs true multilayer optimization

Boccaletti describes the “flattening/matricization” process and stresses that the behaviors of the original multiplex \(M\) and the flattened monolayer \(\tilde{M}\) are related but different because a single node becomes multiple node-layer nodes in the flattened object. citeturn7view0  
More broadly, flow-based work on multilayer representations notes that aggregating pathways across multiple sources/layers into a single network can distort topology and the dynamics implied by the representation—even before optimization. citeturn15view1

For Power Atlas, this motivates a clear methodological separation:
- **Aggregated approach:** collapse layers into one adjacency and run single-layer methods (simpler, but loses layer semantics).
- **True multilayer approach:** keep layers separate and use multislice modularity (or another multilayer method) so that coupling and layer-specific evidence are expressed explicitly. citeturn7view0turn8view2

## Architectural translation for Power Atlas

Power Atlas (entity["organization","Power Atlas","architecture-first research initiative"]) is evidence-first, requires provenance per relationship, is time-aware, and must score confidence and track derived lineage. Those constraints strongly favor an architecture where the multilayer structure is a **derived analytical view** over a provenance-native edge store, rather than the fundamental storage primitive.

### Encoding multilayer structure in a provenance-required graph

A practical architecture is a “two-tier” model:

**Tier A: Evidence/claims graph (canonical storage).**  
Store *atomic relationship claims* as first-class records (or nodes/edges) containing:

- endpoints (person IDs),
- relation type → layer label \(l\),
- time scope (valid interval \([t_{\min}, t_{\max}]\) or event time),
- provenance pointers (sources, excerpts, extraction method),
- confidence score \(p\in[0,1]\) and optionally uncertainty model,
- versioning metadata (schema version, extraction pipeline version).

This is exactly the kind of lineage and attribution structure captured in the W3C PROV family (entities, activities, agents, derivations), which is designed for representing and interchanging provenance and supports assessments of reliability/trustworthiness. citeturn3search0turn3search1

**Tier B: Analysis graphs (materialized-on-demand multilayer).**  
For a selected time window, layer set, and weighting scheme, compile a multilayer network \(M\) by:
- selecting claims whose time scopes intersect the analysis window,
- mapping each claim into an intralayer edge weight \(A^{[l]}_{ij}\),
- optionally defining interlayer couplings \(C^{[l,m]}\) via chosen \(\omega\)-rules,
- producing \(\tilde{A}\) (supra adjacency) or an equivalent sparse operator.

This is consistent with the multislice definition: intralayer adjacency \(A^s\) + structured interslice coupling \(C_{jrs}\). citeturn8view2turn7view0

### Storage choices: separate matrices, layer-tagged edges, or explicit supra-structure

**Separate adjacency matrices per layer.**  
Pros: direct input to linear algebra / modularity solvers; easy per-layer normalization.  
Cons: matrices are derived; need heavy provenance mapping from each \(A^{[l]}_{ij}\) back to the claim/evidence set; and time-scoped edges require repeated rematerialization. This strategy fits best as a *cached artifact*, not the canonical store. citeturn7view0turn3search0

**Single graph with layer tags.**  
Pros: matches evidence-first storage; each claim edge can carry provenance, confidence, and time intervals; avoids materializing large \(NL\times NL\) structures until needed.  
Cons: multilayer algorithms still require a compilation step into multislice/supra form; otherwise you silently revert to an edge-colored (not truly multilayer) analysis. citeturn7view0turn8view2

**Explicit supra-structure stored persistently.**  
Pros: algorithm-ready; makes coupling explicit.  
Cons: expensive, often redundant, and difficult to keep provenance coherent under updates; also potentially misleading because supra-structure is parameterized (depends on \(\omega\), time slicing choices, and confidence/weight mappings). Boccaletti explicitly treats supra adjacency as an imposed flattening that changes the object by node replication. citeturn7view0turn21view0

**Recommendation for Power Atlas:** store **layer-tagged, time-scoped, provenance-rich claims** as canonical data, and generate **layered adjacency + supra operators** as *versioned derived artifacts* for each analytic run. This matches “architectural clarity before productization,” because it separates what is observed (claims + evidence) from what is inferred/derived (communities, centralities, structural features). citeturn3search0turn8view2turn12view0

### Time-aware edges as layers vs as time-interval attributes

Boccaletti shows that a temporal network \((G(t))_{t=1}^T\) can be represented as a multilayer network with each time as a layer slice and (often) coupling only between consecutive slices via replica links. citeturn7view0  
Mucha’s multislice framework was explicitly designed to cover time-dependent networks and allows coupling designs appropriate for ordered slices (neighbor coupling) versus categorical slices (all-to-all coupling). citeturn8view1turn8view2

For Power Atlas, this yields two coherent implementation patterns:

- **Temporal-as-attributes (continuous time):** keep \([t_{\min}, t_{\max}]\) on claim edges; discretize into slices only when running temporal multilayer analytics. This aligns with evidence-first storage and avoids committing prematurely to a time resolution. citeturn3search2turn7view0
- **Temporal-as-slices (discrete time):** choose a slice granularity (e.g., years, quarters) and treat each \((\text{relation-type}, \text{time-slice})\) as a distinct layer in \(\mathcal{L}\), enabling multislice modularity directly—at the cost of discretization assumptions. citeturn7view0turn8view2

### Confidence scoring as edge weights (and why provenance still matters)

Because modularity objectives and spectral methods accept weighted adjacencies, a straightforward prototype mapping is:
\[
A^{[l]}_{ij} = \sum_{e \in \text{claims}(i,j,l)} f(e),
\]
where \(f(e)\) maps an evidence-bearing claim into a nonnegative weight (e.g., \(f(e)=p_e\), or a calibrated function of confidence and evidence count). Weighted modularity is compatible with Newman's formulation allowing \(A_{ij}\) to take values beyond 0/1 (e.g., multi-edges or weights). citeturn9view0turn8view2

However, Good–de Montjoye–Clauset’s degeneracy result implies that even with high-quality weighting, *community partitions are not uniquely determined by the data*; therefore, Power Atlas must treat “community outputs” as **derived hypotheses** with full source/parameter lineage. citeturn12view0turn3search0

### Versioning layer configurations and tracking \(\omega\) in lineage

Multilayer outputs depend on configuration choices:
- which layers exist and how claims map to them,
- time discretization scheme,
- intralayer weighting rules,
- interlayer coupling matrix \(\omega\) (possibly different for time-coupling vs relation-type coupling),
- resolution parameters \(\gamma_s\).

Later work extending Newman’s community detection theory links modularity parameters to inference assumptions; in multilayer settings, parameter selection is itself a modeling step. citeturn14search8turn14search2turn13view1

**Power Atlas requirement:** treat each analysis run as a PROV “Activity” producing a derived “Entity”:
- inputs: dataset snapshot/hash, layer schema version hash, coupling matrix \(\omega\), resolution vector \(\gamma\), optimizer + random seeds;
- outputs: partition(s), quality score(s), stability metrics, plus traceability from partition assignments back to included claims. citeturn3search0turn13view1

### Preventing one layer from dominating community detection

Layer dominance is a predictable failure mode when one layer has much larger total weight (denser edges, higher confidence) than others, because additive objectives will be driven by the largest contributions unless normalized or explicitly reweighted. The parameter-space nature of multilayer modularity and the need to balance intralayer vs interlayer terms is emphasized in multislice modularity and in subsequent parameter-selection work. citeturn8view2turn13view1turn14search2

Architecturally coherent mitigation strategies include:

- **Per-layer normalization:** rescale each \(A^{[l]}\) so that \(\sum_{ij}A^{[l]}_{ij}\) is comparable across layers (or matches a target weighting policy).
- **Layer weights:** incorporate explicit layer weights (effectively \(A^{[l]}\leftarrow \lambda_l A^{[l]}\)) and record \(\lambda_l\) in lineage.
- **Layer-specific resolutions \(\gamma_s\):** the multislice formula already allows different \(\gamma_s\) per slice, offering a direct knob to adjust effective scale per layer/time slice. citeturn8view2turn13view1turn14search2

## Sensitivity and validation considerations

A research-first system needs validation that is **procedural and reproducible**, not interpretive. The empirical lesson from modularity-based community detection is that outputs can vary substantially across parameters and across stochastic optimization runs, and this is amplified in multilayer settings. citeturn12view0turn13view1turn8view2

### Layer imbalance and edge-density heterogeneity

When layers differ in density or weight scale, three issues arise:

- **Objective imbalance:** additive modularity terms overweight dense layers unless normalized/weighted. citeturn8view2turn13view1  
- **Coupling distortion:** if \(\omega\) is too large relative to typical intralayer edge weights, communities can be forced to align across layers/time even when intralayer evidence is weak; if too small, layers behave independently and cross-layer structure is lost. Mucha explicitly interprets the coupling parameter as controlling cross-slice correspondence and shows behavior at \(\Omega=0\). citeturn8view2  
- **Resolution interactions:** resolution limits exist in single-layer modularity; multilayer introduces \(\gamma\) and \(\omega\) so “scale” becomes multi-parameter, requiring systematic sweeps rather than single-point estimates. citeturn11view1turn13view1

### Sparse layers and disconnectedness

Sparse layers (few edges) can yield:
- unstable or trivial partitions within that layer,
- sensitivity to small data changes,
- amplified influence of coupling edges (because coupling becomes a larger fraction of total multislice strength \(2\mu\)). citeturn8view3turn8view2

This argues for recording per-layer summary statistics (edge count, total weight, connected components, fraction of isolated node-layer tuples) as part of each run’s metadata and for not assuming that every layer contributes equally informative structure. citeturn13view1turn12view0

### Missing data and uncertain edges

For Power Atlas, missingness and uncertainty are structural facts: evidence coverage is uneven across time and relation types.

Relevant failure modes are well documented in network measurement work:
- entity["people","Gregory Kossinets","sociologist"] analyzes mechanisms of missing data in social networks (boundary specification, non-response, censoring) and shows that missingness can substantially bias structural statistics. citeturn20search1turn20search8  
- Work on probabilistic networks discusses approaches like thresholding edge probabilities into deterministic graphs, treating probabilities as weights, or Monte Carlo sampling to approximate expected modularity—each with different biases and computational costs. citeturn20search3turn20search10

For a research-first multilayer system, the key architectural implication is: **do not collapse uncertainty into a single deterministic graph without recording the transformation** (e.g., threshold \(\tau\), probability-to-weight mapping). citeturn20search3turn3search0

### Parameter sweep strategy and stability metrics

Because modularity landscapes are degenerate and multilayer methodologies require parameter choices, validation must include systematic exploration:

- entity["people","Ryan A. Gibson","network scientist"] & Mucha emphasize that modularity-based methods require selecting resolution and (in multilayer) coupling parameters, and that heuristic algorithms yield different near-optimal results even at the same parameters. citeturn13view1  
- CHAMP post-processing identifies partitions that are optimal in some domain of parameter space, which is useful for summarizing sweeps without cherry-picking a single configuration. citeturn14search3turn13view1

For stability comparison between partitions, a standard metric is **Variation of Information (VI)**, introduced by entity["people","Marina Meilă","statistician"] as an information-theoretic distance between clusterings. citeturn3search3turn3search11

A research-grade validation protocol therefore includes:
- repeated runs over random seeds (to expose heuristic variance),
- sweeps over \((\gamma,\omega)\) (to expose parameter sensitivity),
- VI (or related) distances across runs (to quantify stability),
- perturbation/bootstrapping over edges (to quantify sensitivity to sampling and missingness). citeturn12view0turn13view1turn3search3turn20search5

### Recommended validation protocol for Power Atlas

A minimal protocol consistent with “evidence-first, confidence-scored, provenance-required” is:

1. **Define the analysis view**: time window \([t_0,t_1]\), layers \(\mathcal{L}'\), claim-to-weight map \(f\), coupling design \(C\), and normalization/weights \(\{\lambda_l\}\). citeturn8view2turn7view0  
2. **Run parameter sweeps**: grid or adaptive sweep in \(\gamma\) (per layer or shared) and \(\omega\) (or \(\omega\)-matrix), with \(R\) repeated runs per point. citeturn13view1turn8view2  
3. **Post-process**: identify robust partitions across parameter domains (e.g., CHAMP-style admissibility) and quantify within-domain stability (VI distribution). citeturn14search3turn3search3turn13view1  
4. **Perturbation tests**: resample or perturb edges within confidence bounds (or drop a fraction of low-confidence edges) and rerun a subset of the sweep to estimate robustness to missing/uncertain data. citeturn20search1turn20search3turn20search5  
5. **Log everything** with run-level provenance so that any published structural claim can be traced to the exact parameter regime and evidence snapshot. citeturn3search0turn13view1

## Implementation guidance for a prototype

This section translates the above into a prototype engineering plan that is faithful to the multilayer mathematics and to Power Atlas’s provenance requirements.

### Constructing the supra-adjacency (sparse, block-structured)

Given:
- physical nodes \(V\) (persons),
- slices \(s \in \{1,\dots,S\}\) (each slice corresponds to one layer label or one (layer, time) pair),
- intralayer adjacencies \(A^{s}\),
- coupling scheme \(C_{jrs}\) (often replica-only),

build a sparse supra-adjacency \(\tilde{A}\in\mathbb{R}^{(N S)\times(N S)}\):

1. **Index mapping**: define \(\pi(i,s)= i + N(s-1)\) (for dense node presence) or a sparse mapping if node sets differ by slice. This matches the node-slice indexing used in multislice modularity. citeturn8view3turn7view0  
2. **Diagonal blocks**: for each slice \(s\), place \(A^{s}\) into block \((s,s)\). citeturn7view0turn8view2  
3. **Off-diagonal blocks (coupling)**:
   - For multiplex categorical coupling: connect \((i,s)\) to \((i,r)\) for all \(r\neq s\) with weight \(\omega_{\text{type}}\).
   - For temporal coupling: connect \((i,t)\) to \((i,t\!+\!1)\) with weight \(\omega_{\text{time}}\), matching the temporal multilayer mapping described by Boccaletti and the ordered-slice coupling described by Mucha. citeturn7view0turn8view1turn8view2  
4. **Store the coupling design as data** (not just code): persist \(\omega\) (or \(\omega_{rs}\)) and coupling topology (which slice pairs are coupled). This is required for reproducibility and for interpreting outputs. citeturn8view2turn3search0turn13view1

### Running multilayer modularity optimization

A minimal, literature-aligned pipeline is:

- Use the multislice modularity quality function (Mucha et al.) with chosen null model per slice (often configuration-model-based in modularity formulations). citeturn8view2turn9view0  
- Optimize with a community detection heuristic that accepts a modularity matrix / operator. For example:
  - GenLouvain provides a widely used multislice modularity optimizer implementation pathway. citeturn19search0  
  - Alternative families (for cross-checking) include inference-based SBMs (which Newman relates to modularity in monolayer settings and which are extended to multilayer modularity parameter selection by Pamfil et al.). citeturn14search8turn14search2turn19search3  
  - Flow-based multilayer community detection (Infomap/map equation) provides a distinct objective useful for triangulation, and it natively models “state nodes” vs “physical nodes.” citeturn15view1turn19search1turn19search5

Because heuristic outputs can vary run-to-run (degeneracy, stochasticity), always run multiple seeds per parameter point and treat the output as a *set of partitions* rather than a single partition. citeturn12view0turn13view1

### Logging run metadata as first-class provenance

For each community detection run (and more generally any derived-structure computation), log:

- **Dataset snapshot identifier** (e.g., SHA-256 over canonicalized claim set for the time window).
- **Time window** \([t_0,t_1]\) and discretization scheme if slicing.
- **Layer schema version** (hash of layer definitions + claim-to-layer mapping rules).
- **Intralayer weighting policy** (how confidence and evidence are transformed into edge weights).
- **Layer weights / normalization** vector \(\lambda\).
- **Coupling specification**: coupling topology + \(\omega\) (or \(\omega_{rs}\)).
- **Resolution parameters**: \(\gamma\) (shared or per-slice).
- **Optimizer identity** (algorithm, version), random seed(s), termination criteria.
- **Outputs**: partition ID, modularity value(s), stability metrics (e.g., VI vs other runs), output hash.

This level of metadata is directly aligned with the PROV view of derived entities and is necessary to avoid “parameter amnesia” in multilayer modularity where outcomes depend on \((\gamma,\omega)\). citeturn3search0turn13view1turn8view2

### Technology suggestions consistent with the architecture-first approach

A workable split is “transactional provenance graph” + “analytical matrix/graph compute.”

- **Provenance + claim storage (graph / knowledge graph layer):**
  - A property graph database such as entity["company","Neo4j","property graph database"] supports nodes/relationships with properties, which is a natural fit for relationship claims carrying time bounds, confidence, and provenance pointers. citeturn16search0turn16search4turn16search12  
  - An RDF store using named graphs (e.g., entity["organization","Apache Jena","rdf framework"] datasets) can represent provenance partitions (different sources as named graphs) and aligns naturally with W3C PROV-O integration; named graphs are explicitly part of RDF datasets. citeturn16search2turn16search10turn3search1  
  - Distributed property-graph engines such as entity["organization","JanusGraph","distributed graph database"] target scaling to very large graphs, though multilayer analytics will still typically require exporting to an analytics engine for supra-matrix construction. citeturn16search7turn16search3  

- **Analytics / computation layer:**
  - Sparse matrix tooling (to build \(\tilde{A}\) efficiently) and modularity solvers such as GenLouvain (reference implementation) for multislice modularity. citeturn19search0turn7view0turn8view2  
  - Inference-based alternatives (SBM tooling) for cross-validation and for cases where modularity’s resolution/degeneracy issues are problematic, consistent with Newman’s equivalence framing and multilayer extensions. citeturn14search8turn14search2turn19search3  
  - Infomap/map-equation tooling for multilayer “state node / physical node” community detection as an objective-function cross-check. citeturn19search1turn15view1turn19search5  

### Prototype checklist aligned to Power Atlas constraints

A prototype that is mathematically coherent and architecturally auditable should be able to produce, for any run, a “derivation bundle”:

- exact slice definitions (layer × time),
- the mapping from evidence claims → weighted edges,
- the supra-adjacency operator definition (\(\tilde{A}\) or an equivalent modularity matrix),
- the parameters \((\gamma,\omega)\),
- the optimizer configuration (seeded),
- the partition output plus stability statistics,
- and pointers back to the source evidence for every edge contributing to each slice.

This checklist is a direct engineering translation of: (i) supra-adjacency/multislice formalism, (ii) modularity’s parameter dependence and degeneracy, and (iii) provenance-first design via PROV. citeturn7view0turn8view2turn12view0turn3search0