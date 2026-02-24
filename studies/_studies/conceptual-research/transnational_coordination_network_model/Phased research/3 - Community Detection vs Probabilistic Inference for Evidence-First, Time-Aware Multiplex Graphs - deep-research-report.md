# Community Detection vs Probabilistic Inference for Evidence-First, Time-Aware Multiplex Graphs

## Deterministic community detection

Deterministic (algorithmic) community detection methods treat the observed network as the object of optimization and return a partition (or hierarchy) that optimizes an explicit objective defined on that observed graph. In the Power Atlas setting—person-centric, typed multilayer edges, temporally bounded relationships, and evidence/confidence metadata—these methods are usually implemented as **derived, reproducible hypotheses** over a specified graph view (time window × layer selection × weighting rules). Foundational network-science framing for this “optimize an objective on a given graph” perspective appears throughout standard texts and multilayer surveys (see [R1], [R2], [R3]).

### Modularity maximization

**Mathematical formulation.** For an undirected (possibly weighted) graph with adjacency/weight matrix \(A\), degree/strength \(k_i=\sum_j A_{ij}\), and total weight \(2m=\sum_i k_i=\sum_{ij}A_{ij}\), modularity of a partition \(g\) is commonly defined as:

\[
Q \;=\; \frac{1}{2m}\sum_{i,j}\Bigl(A_{ij} - \frac{k_i k_j}{2m}\Bigr)\,\mathbf{1}[g_i=g_j].
\]

The term \(\frac{k_i k_j}{2m}\) is the **configuration-model null** expectation for edge weight between \(i\) and \(j\) under degree preservation, so modularity measures “excess within-community weight beyond the null model” ([R1], [R4], [R5]).

A widely used generalization introduces a **resolution parameter** \(\gamma\):

\[
Q(\gamma) \;=\; \frac{1}{2m}\sum_{i,j}\Bigl(A_{ij} - \gamma\frac{k_i k_j}{2m}\Bigr)\,\mathbf{1}[g_i=g_j],
\]

which trades off community size (larger \(\gamma\) tends to favor smaller communities) ([R6], [R1]).

**Assumptions (implicit).** Modularity assumes:
- A specific null model (often configuration model) is the baseline against which “community structure” is judged ([R1], [R5]).
- “Community” corresponds to **within-group edge density/weight above null**, not necessarily a block-constant generative mechanism ([R1], [R7]).
- The observed graph is complete in the sense that “missing edges” are treated as true non-edges unless explicitly preprocessed.

**Output type.** Standard modularity optimization returns a **hard partition** \(g_i\in\{1,\dots,K\}\). Common heuristics can also return multi-level/hierarchical structure implicitly (via iterative aggregation), but modularity itself is a single-number objective for a single partition ([R5], [R8], [R9]).

**Sensitivity analysis for Power Atlas constraints.**
- **Layer weighting.** If you aggregate multiple edge-types into one weighted graph, modularity’s result can be dominated by layers with higher total weight \(2m\) unless you normalize per layer or explicitly reweight layers before aggregation ([R2], [R10]). In a multiplex setting, modularity on an aggregated graph discards layer identity unless encoded into weights.
- **Missing edges / incomplete evidence.** If evidence collection is incomplete, modularity treats unknown edges as absent, which can spuriously increase apparent separation between groups (fewer “between” edges) or fragment communities due to missing within-group support. Deterministic modularity has no native “missingness model” ([R1], [R7]).
- **Degree heterogeneity.** The configuration null accounts for degrees, but modularity optimization can still behave poorly in extremely heavy-tailed degree regimes, especially when high-degree hubs “pull” many nodes into the same community under some heuristics (a practical rather than purely theoretical issue) ([R1], [R7], [R11]).

**Computational complexity.** Exact modularity maximization is NP-hard (and related decision variants are NP-complete), so real systems use heuristics (e.g., Louvain / Leiden family, spectral relaxations, simulated annealing) with near-linear empirical scaling on sparse graphs but no global optimality guarantee ([R12], [R8], [R9]).

### Resolution limit

**What it is.** Modularity has a well-known **resolution limit**: maximizing \(Q\) can fail to recover small communities even when they are intuitively “real,” because the objective compares within-community edges to a null that depends on global \(2m\). Small dense modules can be merged when doing so increases modularity globally ([R11], [R1]).

**Operational implication in person-centric graphs.** In Power Atlas, important “small communities” might correspond to niche boards, short-lived joint appointments, tight co-authorship cliques, or small task forces. A modularity baseline can systematically **under-segment** these unless you tune \(\gamma\) or perform multi-resolution scanning with explicit provenance of the resolution parameter ([R11], [R6]).

### Degeneracy of high-modularity partitions

**What it is.** The modularity landscape can be highly **degenerate**: there can exist many partitions with modularity values extremely close to the maximum but with substantially different community assignments, especially in large sparse graphs. This means the “best” modularity partition can be unstable and non-unique in a practically meaningful way ([R13], [R1]).

**Operational implication.** If Power Atlas requires confidence scoring and reproducibility, modularity outputs should be treated as a *family of near-optimal hypotheses*, not a single truth. Practically, you can:
- run multiple random seeds / perturbations and report consensus partitions,
- store stability metrics (e.g., variation of information across runs),
- store \(\Delta Q\) gaps and ensemble variability rather than only the top partition ([R13], [R14]).

### Multilayer modularity via supra-adjacency

In multiplex/time-layered networks, the deterministic modularity idea extends by optimizing an objective on a **supra-graph** that includes (i) intralayer edges and (ii) interlayer couplings.

**Mathematical formulation (canonical).** A common multilayer modularity for node \(i\) in layer \(\alpha\) uses:

\[
Q_\text{multi} \;=\; \frac{1}{2\mu}\sum_{i,j}\sum_{\alpha,\beta}
\Bigl[\bigl(A_{ij}^{[\alpha]} - \gamma^{[\alpha]} P_{ij}^{[\alpha]}\bigr)\delta_{\alpha\beta} \;+\; \delta_{ij} C_{i}^{[\alpha\beta]}\Bigr]\,
\mathbf{1}[g_i^{[\alpha]}=g_j^{[\beta]}],
\]

where:
- \(A_{ij}^{[\alpha]}\) is adjacency/weight in layer \(\alpha\),
- \(P_{ij}^{[\alpha]}\) is the chosen null model in that layer (often configuration-model expectation),
- \(\gamma^{[\alpha]}\) is a per-layer resolution,
- \(C_{i}^{[\alpha\beta]}\) is **interlayer coupling** for node \(i\) between layers \(\alpha\) and \(\beta\),
- \(2\mu\) normalizes total supra-edge weight,
- \(\delta_{\alpha\beta}\) and \(\delta_{ij}\) ensure intralayer vs interlayer terms appear in the right places ([R10], [R2]).

A widely used coupling scheme sets \(C_{i}^{[\alpha\beta]}=\omega\) for adjacent time layers (or for corresponding node-copies across multiplex layers), so \(\omega\) controls the bias toward **temporal persistence / cross-layer consistency** in community labels ([R10], [R2]).

**Assumptions.**
- You assume that “same person across layers” is meaningful and should be softly encouraged to share membership (encoded by \(\omega\)).
- You assume a null model per layer (and therefore per-layer degree distribution treatment) ([R10], [R2]).

**Output type.** Typically **hard communities per node-layer** \(g_i^{[\alpha]}\). Depending on solver, you may get hierarchical structure from repeated aggregation, but the base output is still discrete labels ([R10], [R2]).

**Sensitivity.**
- **Layer weighting.** Layer weights can be expressed as rescaling \(A^{[\alpha]}\) (or changing \(2m_\alpha\)), but the key operational factor is that the multilayer objective’s balance is affected by: (i) total intralayer weight per layer, (ii) the coupling mass from \(\omega\), and (iii) \(\gamma^{[\alpha]}\). Unnormalized layers can dominate the solution ([R2], [R10]).
- **Sparse/empty layers.** If a layer is very sparse, the coupling term can dominate and effectively “copy” structure from denser layers, which may be desirable (regularization) or undesirable (layer dominance artifact). This is a core engineering consideration in evidence-first multiplex graphs where some layers are much less observed ([R2], [R10]).
- **Missing edges.** Missing edges within a layer again appear as absent; coupling can mitigate fragmentation across time but can also spread bias across layers if one slice is incomplete ([R2], [R10]).

**Computational complexity.** Optimization is again NP-hard in general; in practice you run modularity heuristics on the supra-graph. The supra-graph has \(nL\) node-copies for \(n\) persons and \(L\) layers/time-slices, so memory and runtime scale with the number of intralayer edges plus interlayer coupling edges (often \(O(nL)\) for adjacent-time coupling) ([R10], [R2]).

### Flow-based clustering via Infomap

Infomap is a deterministic community detection approach that replaces density-based objectives (like modularity) with a **compression principle** for trajectories of a (possibly weighted/directed) random walk.

**Mathematical formulation (map equation).** Given a partition into modules, Infomap defines an objective \(L(M)\) that is the expected per-step description length of a random-walk path using a two-level (module codebook + within-module codebook) encoding:

\[
L(M) \;=\; q_{\curvearrowright} H(\mathcal{Q}) \;+\; \sum_{r=1}^{K} p_{\circlearrowright}^{r} H(\mathcal{P}^{r}),
\]

where \(q_{\curvearrowright}\) is the probability of exiting modules, \(H(\mathcal{Q})\) is entropy of module-exit events, and \(p_{\circlearrowright}^{r} H(\mathcal{P}^{r})\) describes within-module moves plus exits for module \(r\). The algorithm seeks the partition minimizing \(L(M)\), i.e., maximizing compression ([R15]).

**Assumptions.**
- The “meaning” of community is **flow persistence**: modules are sets where a random walker tends to stay for long times.
- The appropriate notion of structure may align better with directed/weighted interactions (e.g., information flow, career transitions) than raw density ([R15], [R1]).

**Output type.** Often a **hard partition**, typically with a strong hierarchical interpretation (Infomap is frequently used in hierarchical mode) ([R15]).

**Sensitivity.**
- **Layer weighting / multiplex.** In multiplex or temporal networks, flow-based methods can be extended by defining interlayer transition probabilities; operationally, these choices can dominate results because the random-walk dynamics define the objective. This can be powerful for time-aware person graphs but requires careful documentation of transition rules (a provenance requirement) ([R2], [R15]).
- **Missing edges.** Missing edges directly alter transition probabilities and therefore can strongly distort communities.
- **Degree heterogeneity.** Flow compression can behave differently than modularity under heavy-tailed degrees; high-degree nodes can act as “funnels” for flow and may shape modules differently than density objectives ([R15], [R1]).

**Computational complexity.** The objective is non-convex and solved heuristically; empirically it scales well on sparse graphs, but complexity depends on repeated local moves and sometimes multilevel refinements ([R15]).

image_group{"layout":"carousel","aspect_ratio":"16:9","query":["multilayer network schematic supra adjacency matrix community detection","stochastic block model block matrix illustration","Infomap map equation diagram random walk community detection","mixed membership stochastic blockmodel plate diagram"],"num_per_query":1}

## Stochastic block models

SBMs treat communities as **latent variables in a generative model** for the network. Instead of optimizing a descriptive objective on a fixed graph, SBMs posit a probability distribution over graphs parameterized by latent block structure and then infer that structure from data.

Conceptual foundations and early formalization appear in the “first steps” SBM paper (see [R16]) and Bayesian statistical discussions of network modeling (see [R17]). In the Power Atlas architecture, the key shift is that a community assignment becomes a **probabilistic hypothesis about how edges were generated**, enabling posterior uncertainty, model selection, and principled handling of incomplete observations.

### Generative definition and block probability matrix

**Basic SBM (Bernoulli, undirected).**
- Each node \(i\) has a latent block label \(z_i \in \{1,\dots,K\}\).
- A symmetric matrix \(\Theta\in[0,1]^{K\times K}\) defines edge probabilities between blocks.
- For \(i<j\):

\[
A_{ij}\mid z,\Theta \sim \text{Bernoulli}(\theta_{z_i z_j}).
\]

This implies that, conditional on block assignments, edges are independent with probabilities determined only by the pair of blocks ([R16], [R17]).

**What “community” means under SBM.** Under SBM, a “community” is not necessarily “dense”: it is a **block**—a set of nodes that share statistically similar connection patterns to all blocks (including itself). Communities can therefore be assortative (dense within, sparse between), disassortative, core–periphery, or more complex mixing patterns depending on \(\Theta\) ([R16], [R17]).

### Likelihood function

For the Bernoulli SBM:

\[
p(A\mid z,\Theta) \;=\; \prod_{i<j} \theta_{z_i z_j}^{A_{ij}}\bigl(1-\theta_{z_i z_j}\bigr)^{1-A_{ij}}.
\]

Inference can be framed as (i) maximum likelihood over \((z,\Theta)\), (ii) maximum a posteriori (MAP) under priors, or (iii) full Bayesian posterior \(p(z,\Theta\mid A)\) ([R16], [R17]).

### Degree-corrected SBM

**Motivation.** The basic SBM tends to imply relatively homogeneous degrees within a block. Many real networks (especially person-centric social/professional graphs) have heavy-tailed degrees; without correction, SBMs can mistake degree heterogeneity for community structure (e.g., creating blocks based on degree rather than mixing pattern) ([R18], [R17]).

**A common degree-corrected formulation.** One widely used approach introduces node-specific propensity parameters \(\phi_i\) and block affinity parameters \(\Omega\) in a Poisson edge-count model:

\[
A_{ij} \mid z,\phi,\Omega \sim \text{Poisson}(\phi_i \phi_j \,\omega_{z_i z_j}),
\]

with constraints (e.g., normalization within blocks) for identifiability. For simple graphs, this is often used as an approximation or adapted so that probabilities remain in \([0,1]\) ([R18], [R17]).

**Practical meaning.** Degree correction separates:
- “How active/prominent is a person?” (\(\phi_i\))
from
- “How do groups connect?” (\(\omega_{ab}\))  
which is often exactly the separation you want when Power Atlas edges mix career prominence with genuine community structure ([R18], [R17]).

### Model selection criteria

Unlike modularity, SBMs support explicit **model order/complexity selection** for \(K\) and model family.

Common approaches include:
- **BIC-style criteria**: penalize log-likelihood by parameter count, approximating marginal likelihood under regularity assumptions ([R17]).
- **MDL / description length**: choose the model that compresses the adjacency matrix best when accounting for the cost of encoding the model parameters and assignments. MDL has become a central tool in modern SBM practice (including hierarchical/nested formulations) ([R19], [R17]).
- **Bayesian model comparison**: priors over \(K\), marginalization over parameters, posterior predictive checks, and Bayes factors where feasible ([R17], [R19]).

### SBM vs modularity philosophically

- **Modularity** is a *descriptive objective*: it scores a partition by within-group edge surplus relative to a null model on the observed graph ([R1], [R5]).
- **SBM** is a *generative hypothesis*: it posits that edges were sampled according to block-level parameters, and “best communities” are those that make the observed graph most probable (or have highest posterior probability) under that model ([R16], [R17]).

This difference is not only philosophical—it changes what can be stored as evidence: under SBM, you can store posterior uncertainty, predictive distributions over missing edges, and explicit model comparison artifacts, which align naturally with evidence-first architectural constraints ([R17], [R19]).

### When SBM collapses to modularity-like results

There are formal connections between modularity and likelihood-based inference in particular SBMs (and related Potts-model formulations): under certain assumptions (notably assortative structure, specific parameter tying/constraints, and particular priors or null models), optimizing modularity can be shown to correspond to maximizing (approximate) likelihood or posterior objectives of an SBM-like model ([R6], [R7], [R20]).

Engineering implication: modularity partitions can serve as useful **initializations** for SBM inference or as a fast baseline, but they do not generally provide the calibrated uncertainty and model selection that SBM frameworks enable ([R7], [R17], [R19]).

### Where SBMs perform better

SBMs (especially degree-corrected and MDL-selected variants) are often stronger when:
- **Degree distributions are heterogeneous** (common in person-centric graphs with hubs) ([R18], [R19]).
- Structure is **not purely assortative** (e.g., core–periphery between elite institutions and broader membership; bipartite-like mixing across sectors) ([R16], [R17]).
- You require **principled uncertainty and model comparison** rather than a single optimized partition ([R17], [R19]).

## Mixed-membership and Bayesian SBMs

Mixed-membership SBMs (MMSB) and Bayesian SBMs extend block modeling to allow **overlap** (soft membership) and to represent uncertainty explicitly through posterior distributions.

### Mixed-membership formulation

A canonical MMSB posits that each node \(i\) has a membership vector \(\pi_i \in \Delta^{K-1}\) (a point on the \(K\)-simplex). For each pair \((i,j)\), the model samples latent “roles” for the interaction:

\[
z_{i\rightarrow j} \sim \text{Categorical}(\pi_i), \quad
z_{j\rightarrow i} \sim \text{Categorical}(\pi_j),
\]
\[
A_{ij} \mid z_{i\rightarrow j}, z_{j\rightarrow i}, B \sim \text{Bernoulli}(B_{z_{i\rightarrow j},\,z_{j\rightarrow i}}),
\]

where \(B\) is a block interaction matrix ([R21]).

This supports **overlapping communities** because a person can participate in multiple roles with different probabilities.

### Posterior inference methods

Because exact posterior inference is typically intractable at realistic scales, common approaches include:
- **Variational inference** (mean-field / coordinate ascent, sometimes stochastic variational inference for scale) ([R21], [R17]).
- **Gibbs sampling / MCMC** for smaller graphs or for validation runs (often used to assess variational bias) ([R17], [R21]).
- **Collapsed variants** where some parameters are integrated out to improve mixing in sampling-based inference (model dependent) ([R17]).

For Power Atlas, the inference method is not a mere implementation detail: it determines which uncertainty artifacts you can store (e.g., ELBO traces for variational methods vs. effective sample size and \(\hat{R}\) for MCMC) ([R17]).

### Uncertainty representation

In MMSB / Bayesian SBMs, uncertainty emerges at multiple levels ([R17], [R21]):

- **Node-level uncertainty:** posterior (or variational) distribution over \(\pi_i\) or its point estimate plus covariance/concentration.
- **Edge-level uncertainty:** posterior predictive distribution \(p(A_{ij}=1 \mid \text{data})\).
- **Block-structure uncertainty:** uncertainty over \(B\) (and sometimes over \(K\) under nonparametric extensions).

A compact and operationally useful node-level metric is the **membership entropy**:

\[
H(\pi_i) \;=\; -\sum_{k=1}^{K} \pi_{ik}\log \pi_{ik},
\]

which is low when a node is confidently assigned to one role and high when membership is diffuse ([R21], [R17]).

### Alignment with probabilistic structural hypotheses

Soft membership directly encodes the idea “this person participates in multiple structural roles,” which is common in real person-centric networks (e.g., an academic who is also a government advisor and a corporate board member). Rather than forcing a hard partition, MMSB produces a distributional representation aligned with hypothesis-driven modeling and evidence uncertainty ([R21], [R17]).

### Storage implications for Power Atlas

Storing mixed membership is fundamentally different from storing a partition:

- A hard partition stores one label per node: \(O(n)\).
- An MMSB stores a length-\(K\) vector per node: \(O(nK)\), plus block interaction parameters \(O(K^2)\) and inference diagnostics.

Practically, you often compress:
- store top-\(r\) memberships per node (sparse representation) with residual mass,
- store entropy and a calibrated “confidence” summary,
- store full vectors only for nodes above an “importance” threshold or within focused subgraphs.

These design choices should be explicit parts of the derived-entity schema because they affect interpretability and reproducibility ([R17], [R21]).

### Persisting posterior uncertainty in a graph system

A principled persistence strategy is to store:
- A **point summary** (e.g., posterior mean or MAP) of \(\pi_i\),
- A **derived uncertainty statistic** (entropy; credible interval widths; concentration parameters),
- **Model-level diagnostics** (convergence, ELBO or sampling diagnostics),
- The **posterior predictive checks** summary on held-out edges where feasible.

This aligns with Bayesian network analysis practice emphasizing posterior predictive validation and uncertainty reporting ([R17]).

## Deterministic vs probabilistic direct comparison

| Feature | Modularity | Multilayer modularity | SBM | Mixed-membership SBM |
|---|---|---|---|---|
| Hard vs soft membership | Hard partition \(g_i\) ([R5]) | Hard per node-layer \(g_i^{[\alpha]}\) ([R10]) | Usually hard \(z_i\) in basic SBM; can be posterior over \(z\) in Bayesian variants ([R16], [R17]) | Soft \(\pi_i\) (overlap by design) ([R21]) |
| Handles overlap | Not natively; overlap needs post-processing or alternative formulations ([R1]) | Not natively; can track layer-dependent labels but still discrete ([R10]) | Not in basic SBM; extensions exist ([R16], [R17]) | Yes (core motivation) ([R21]) |
| Degree correction | Indirect via null model; not a generative separation of degree vs structure ([R1], [R7]) | Same limitation per layer; coupling adds another knob ([R10]) | Degree-corrected variants explicitly model node propensities ([R18]) | Mixed-membership can be combined with degree correction in extended formulations; not inherent to basic MMSB ([R17]) |
| Uncertainty output | None intrinsic; uncertainty must be estimated via perturbation / ensembles ([R13]) | Same; plus sensitivity to \(\omega\) and layer scaling ([R10]) | Bayesian SBMs yield posteriors; even ML SBMs allow likelihood-based uncertainty approximations ([R17]) | Rich posterior uncertainty over \(\pi_i\), \(B\), predictions ([R21], [R17]) |
| Assumes generative model | No (descriptive objective) ([R1], [R5]) | No (descriptive objective on supra-graph) ([R10]) | Yes (explicit data-generating process) ([R16]) | Yes (explicit generative process with latent roles) ([R21]) |
| Parameter sensitivity | Sensitive to \(\gamma\), null model choice, heuristic choices, random seeds ([R6], [R13]) | Sensitive to \(\gamma^{[\alpha]}\), \(\omega\), layer scaling, coupling structure ([R10], [R2]) | Sensitive to \(K\), priors/regularization, degree-correction choice, inference settings ([R17], [R19]) | Sensitive to \(K\), priors (Dirichlet concentration), inference approximations; higher overfitting risk without regularization ([R21], [R17]) |
| Interpretability | High: “dense within vs null” is intuitive; but can hide non-assortative patterns ([R1]) | Medium–high: adds “temporal/layer consistency” knob but harder to reason about globally ([R10], [R2]) | High when framed as block-to-block mixing matrix \(\Theta\); supports non-assortative structures ([R16], [R17]) | High for overlap/roles; but vectors per node can be harder to communicate without summarization ([R21]) |
| Computational cost | NP-hard; heuristics scale well on sparse graphs ([R12], [R8]) | NP-hard; supra-graph blows up size by \(L\) layers, cost scales with intra+inter edges ([R10]) | Inference can be expensive; scalable variants exist, but cost depends on \(K\), method (VI/MCMC), and model selection ([R17], [R19]) | Typically more expensive than hard SBM because of per-edge latent roles; large-scale inference often requires variational/stochastic methods ([R21]) |
| Stability under perturbation | Can be unstable due to degeneracy; needs ensemble stability reporting ([R13]) | Additional instability via \(\omega\), sparse layers; can “lock in” across time ([R10], [R2]) | Has a detectability phase transition; otherwise can be stable when signal is above threshold and model is well selected ([R22], [R19]) | Can be stable but prone to overfitting without priors/model selection; uncertainty helps reveal instability ([R21], [R17]) |

## Failure modes and pathologies

### Resolution limit in modularity

As noted earlier, modularity can merge small but meaningful communities because the objective is global and depends on \(2m\). This is not a small corner case; it can be structurally inevitable for certain graph families (resolution-limit phenomenon) ([R11], [R1]). For Power Atlas, this argues for either multi-resolution sweeps with explicit provenance (\(\gamma\) grid) or complementing modularity with generative inference that can represent small blocks when supported by the data ([R19], [R17]).

### Degeneracy of modularity landscapes

Many near-optimal partitions can exist, and different heuristic runs can produce materially different assignments with similar modularity scores. This can yield false confidence if you store only one partition without stability metadata ([R13], [R14]). In evidence-first systems, *degeneracy should become stored uncertainty*, not an untracked implementation artifact.

### Detectability threshold in SBMs

SBMs exhibit a **detectability threshold**: below a certain signal-to-noise regime (roughly, community structure too weak relative to randomness at a given sparsity), no algorithm—even the Bayes-optimal one—can recover communities better than chance. This is a statistical identifiability limit rather than an optimization failure ([R22], [R23]). Operationally:
- A failure to recover structure may reflect that the data does not support structure at the chosen time window / layer selection.
- MDL/Bayesian model selection can sometimes select small \(K\) (including \(K=1\)) when the signal is below threshold, which is a *feature* for evidence-first modeling if interpreted correctly ([R19], [R17]).

### Overfitting in mixed-membership models

MMSB models are flexible; without adequate regularization/priors and model selection, they can:
- allocate spurious roles,
- fit noise by dispersing memberships,
- produce “explanations” that do not generalize (poor posterior predictive performance).  
This is the classic bias–variance tradeoff amplified by latent-variable flexibility, and it is addressed via priors (e.g., Dirichlet concentration), held-out likelihood, and MDL/Bayesian model comparison where applicable ([R21], [R17], [R19]).

### Sensitivity to sparse multiplex layers

In multilayer modularity, sparse layers can be dominated by coupling \(\omega\) and inherit structure from denser layers, potentially masking genuine layer-specific patterns. Conversely, setting \(\omega\) too low can fragment temporal identity and create “flickering communities” that are hard to interpret in time-aware systems. These are not bugs; they are consequences of how supra-graph objectives trade off intra- vs interlayer evidence ([R10], [R2]).

### Layer dominance effects

Layer dominance occurs when:
- one layer has far higher edge weight mass,
- aggregation creates a single “effective layer,”
- or a coupling/normalization choice makes one layer’s topology disproportionately influential.  
This can undermine the purpose of multiplex modeling—preserving typed relational evidence—unless layer weighting and normalization rules are explicit, versioned, and tested via sensitivity experiments ([R2], [R10]).

## Integration into Power Atlas

Power Atlas enforces evidence-first modeling, time-aware relationships, confidence scoring, and strict provenance for derived entities. The key integration principle is:

**Community outputs must be stored as *hypotheses over a specific graph view*, not as intrinsic properties of persons.**

A “graph view” should itself be a versioned artifact (time window, layers, weighting/thresholding, and evidence filters), and community detection/inference should yield a derived hypothesis entity that references that view.

### Derived entity schema for deterministic community hypotheses

Below is a schema sketch designed to satisfy: reproducibility, parameter tracking, snapshot versioning, and auditability. (Field names are illustrative; adapt to your graph store conventions.)

```json
{
  "type": "community_hypothesis_deterministic",
  "hypothesis_id": "uuid",
  "created_at": "timestamp",
  "graph_view": {
    "time_window": {"start": "t0", "end": "t1"},
    "layers_included": ["corporate", "ngo", "academic", "government"],
    "layer_weights": {"corporate": 1.0, "ngo": 0.7, "academic": 0.9, "government": 1.0},
    "edge_weight_definition": "duration+frequency+recency",
    "evidence_filter_policy": {
      "min_source_count": 1,
      "min_confidence": 0.4,
      "source_types": ["filing", "publication", "news", "registry"]
    },
    "dataset_hash": "sha256(...)",
    "node_set_hash": "sha256(...)",
    "edge_set_hash": "sha256(...)"
  },
  "algorithm": {
    "family": "modularity_maximization | infomap | other",
    "implementation": "library_name",
    "implementation_version": "x.y.z",
    "random_seed": 12345
  },
  "parameters": {
    "null_model": "configuration",
    "resolution_gamma": 1.0,
    "multilayer": {
      "enabled": true,
      "interlayer_coupling_omega": 0.5,
      "coupling_topology": "adjacent_time | multiplex_identity"
    },
    "stopping_criteria": {"max_iter": 1000, "tolerance": 1e-6}
  },
  "outputs": {
    "membership_type": "hard",
    "community_assignments": {
      "node_id_1": "comm_12",
      "node_id_2": "comm_12",
      "node_id_3": "comm_07"
    },
    "objective_value": {"name": "Q | map_equation_L", "value": 0.4231},
    "community_summary": {
      "num_communities": 23,
      "size_distribution": {"min": 3, "median": 18, "max": 240}
    }
  },
  "uncertainty_and_stability": {
    "repeat_runs": 20,
    "stability_metric": "variation_of_information",
    "stability_summary": {"mean": 0.18, "p95": 0.31},
    "degeneracy_flag": true
  },
  "provenance": {
    "run_environment": {"hardware": "cpu", "os": "linux", "container_digest": "sha256(...)"},
    "notes": "human readable",
    "derivation_chain": ["graph_view_id", "preprocessing_step_ids"]
  }
}
```

This directly addresses modularity degeneracy and heuristic randomness by making stability a first-class stored artifact ([R13], [R14]) and aligns with multilayer coupling sensitivity by storing \(\omega\), coupling topology, and per-layer weights ([R10], [R2]).

### Derived entity schema for probabilistic community hypotheses

Probabilistic outputs must store not only point assignments but also posterior uncertainty and diagnostics.

```json
{
  "type": "community_hypothesis_probabilistic",
  "hypothesis_id": "uuid",
  "created_at": "timestamp",
  "graph_view": { "... same structure as deterministic ...": true },

  "model": {
    "family": "sbm | degree_corrected_sbm | mmsb | bayesian_sbm",
    "likelihood": "bernoulli | poisson | weighted_variant",
    "priors": {
      "block_matrix_prior": "beta(...) | gamma(...)",
      "membership_prior": "categorical_dirichlet(alpha=...)",
      "k_prior": "fixed | nonparametric | mdlsweep"
    }
  },

  "inference": {
    "method": "variational | mcmc | em",
    "settings": {"max_iter": 2000, "tolerance": 1e-6, "num_chains": 4},
    "convergence_diagnostics": {
      "variational": {"elbo_final": -1.23e6, "elbo_trace_hash": "sha256(...)"},
      "mcmc": {"rhat_max": 1.02, "ess_min": 500}
    }
  },

  "model_selection": {
    "chosen_k": 18,
    "criteria": {
      "mdl": 123456.7,
      "bic": 120034.2,
      "heldout_loglik": -4500.1
    },
    "selection_protocol": "grid_over_k | nested | bayes_search",
    "protocol_hash": "sha256(...)"
  },

  "outputs": {
    "membership_type": "soft | hard",
    "map_partition": {"node_id_1": "block_3", "node_id_2": "block_7"},
    "membership_distributions": {
      "node_id_1": [{"block": 3, "p": 0.62}, {"block": 7, "p": 0.21}, {"block": 2, "p": 0.10}],
      "node_id_2": [{"block": 7, "p": 0.55}, {"block": 3, "p": 0.29}]
    },
    "uncertainty_metrics": {
      "node_entropy_summary": {"mean": 0.48, "p95": 0.92},
      "block_matrix_credible_intervals_hash": "sha256(...)"
    },
    "posterior_predictive": {
      "edge_probability_view_id": "optional_view",
      "ppc_summary": {"heldout_auc": 0.81, "calibration_ece": 0.06}
    }
  },

  "provenance": { "...": true }
}
```

The rationale for these fields follows standard Bayesian network analysis practice: posterior distributions, predictive checks, and diagnostics are the core evidence objects, not just the MAP assignment ([R17], [R21]).

### Recommended week 3 engineering experiments

These experiments are explicitly designed to be reproducible and to surface the known pathologies (degeneracy, resolution, detectability, layer dominance).

**Experiment set: deterministic modularity vs SBM on the same multiplex slice**  
Goal: Compare descriptive vs generative partitions on the same evidence-filtered person-centric view.

Protocol:
- Fix a graph view: select a 6–12 month window; choose 2–4 layers; define edge weighting (duration/frequency/recency) and evidence filters; compute dataset hash.
- Run deterministic baseline: (i) aggregated modularity (with documented normalization), (ii) multilayer modularity if layers are preserved.
- Fit SBM variants: basic SBM and degree-corrected SBM; choose \(K\) via MDL or BIC; store model selection traces.
- Compare partitions with variation of information (VI) and/or normalized mutual information; compare predictive performance via held-out edges for SBM variants.
Why this matters: It directly tests whether modularity is mostly capturing assortative density or whether a block mixing matrix yields a different—and more explanatory—structure ([R5], [R16], [R18], [R19], [R14]).

**Experiment set: sweep interlayer coupling \(\omega\) in multilayer modularity**  
Goal: Quantify layer/time coupling sensitivity and identify regimes (fragmented vs locked-in).

Protocol:
- Fix a multilayer graph view (same nodes across time slices or layers).
- Sweep \(\omega\) over a logarithmic grid (e.g., 0, 0.01, 0.05, 0.1, 0.5, 1, 2, 5).
- For each \(\omega\), run multiple seeds; store \(Q_\text{multi}\), community counts, and stability (VI across seeds).
- Evaluate temporal smoothness: compute VI between adjacent time-layer partitions as a function of \(\omega\).
Why this matters: \(\omega\) is a structural prior on persistence; you want to choose it intentionally rather than implicitly ([R10], [R2]).

**Experiment set: perturb edges 5–10% and measure stability**  
Goal: Convert evidence incompleteness into explicit uncertainty estimates for both deterministic and probabilistic methods.

Protocol:
- For a fixed graph view, generate perturbations:
  - randomly drop 5–10% of edges (simulate missing evidence),
  - or randomly rewire 5–10% edges preserving degree distribution (stress structural sensitivity).
- For each perturbed graph, rerun algorithms (multiple seeds).
- Report stability using VI (and optionally consensus clustering for deterministic methods).
Why this matters: VI is a standard metric for partition distance and helps quantify heuristic degeneracy vs genuine robustness ([R14], [R13]). For probabilistic models, compare posterior predictive calibration and block assignment variability across perturbations ([R17]).

## Recommendations

### Baseline method for Power Atlas

Use a **two-tier baseline**:

1) **Deterministic baseline:** modularity-based community detection (including multilayer modularity when layer identity is central) because it is fast, widely understood, and useful for exploratory slicing and UI scaffolding—*but only if you store stability and parameter provenance as first-class artifacts* ([R5], [R10], [R13]).  

2) **Probabilistic baseline:** degree-corrected SBM with principled model selection (MDL/Bayesian), because it better matches person-centric degree heterogeneity and naturally yields uncertainty objects consistent with evidence-first modeling ([R18], [R19], [R17]).

### When probabilistic modeling should be preferred

Prefer SBM/Bayesian approaches when:
- You need **uncertainty** as a stored product (not an afterthought).
- You expect **non-assortative structure** (core–periphery, bipartite-like sector mixing).
- The graph has strong **degree heterogeneity** and you want to separate prominence from structural role.
- You want **model dismissal** as a valid outcome (e.g., “no detectable structure in this time window”), consistent with detectability thresholds and evidence-first discipline ([R22], [R19], [R17]).

### Hard partitions vs membership distributions

Store both, but treat them differently:

- **Hard partition** (deterministic or MAP) is a compact index for downstream engineering (search, faceting, caching, snapshot comparisons).
- **Membership distributions** (for probabilistic models) are the evidence-aligned representation; they enable UI/analytics that reflect ambiguity, overlap, and uncertainty.  

If MVP constraints force a choice, store:
- MAP block per node,
- top-\(r\) membership weights per node,
- node entropy as an uncertainty scalar,
- and model selection + diagnostics artifacts ([R21], [R17], [R19]).

### Visual uncertainty representation

A minimal, interpretable uncertainty UI can be built from:
- **Opacity or saturation** proportional to (1 − normalized entropy) at node-level.
- **Multi-color glyph / stacked bar** for top-\(r\) memberships on demand (details-on-hover).
- **Edge uncertainty overlays** using posterior predictive \(p(A_{ij}=1\mid \text{data})\) as a confidence band rather than binary edges when viewing “inferred ties” ([R17], [R21]).

### Minimal viable prototype to build first

Build a reproducible “community hypothesis pipeline” before optimizing for any single algorithm:

- **Graph view compiler**: deterministically constructs the adjacency (or supra-adjacency) from evidence with explicit time window, layer selection, weighting, and filters; emits dataset/node/edge hashes.
- **Algorithm runner**: runs (i) modularity (single-layer) + multilayer modularity sweep over \(\omega\), and (ii) degree-corrected SBM with MDL/BIC selection.
- **Hypothesis store**: persists derived entities with parameters, software versions, random seeds, and uncertainty/stability artifacts.
- **Comparator**: computes VI and other stability metrics across runs, perturbations, and time windows.

This sequence directly operationalizes the core methodological distinction: deterministic optimization yields *a partition*, whereas probabilistic inference yields *a posterior over structural hypotheses* ([R5], [R17], [R19], [R14]).

## References

[R1] entity["book","Networks: An Introduction","newman 2010"]. entity["people","Mark Newman","network scientist"]. entity["organization","Oxford University Press","publisher oxford, uk"], 2010.

[R2] “The Structure and Dynamics of Multilayer Networks.” entity["people","Stefano Boccaletti","physics complex networks"] et al. entity["organization","Physics Reports","journal"], 2014.

[R3] entity["book","Network Science","barabasi 2016"]. entity["people","Albert-Laszlo Barabasi","network scientist"]. entity["organization","Cambridge University Press","publisher cambridge, uk"], 2016.

[R4] “Community structure in social and biological networks.” entity["people","Michelle Girvan","network scientist"] and Mark Newman, 2002.

[R5] “Finding and evaluating community structure in networks.” Mark Newman and Michelle Girvan, 2004.

[R6] “Statistical mechanics of community detection.” entity["people","Jorg Reichardt","complex systems researcher"] and entity["people","Stefan Bornholdt","physicist complex systems"], 2006.

[R7] “Equivalence between modularity optimization and maximum likelihood methods for community detection.” Mark Newman, 2016.

[R8] “Fast unfolding of communities in large networks.” entity["people","Vincent Blondel","computer scientist"] et al., 2008.

[R9] “From Louvain to Leiden: guaranteeing well-connected communities.” entity["people","Vincent Traag","network scientist"] et al., 2019.

[R10] “Community structure in time-dependent, multiscale, and multiplex networks.” entity["people","Peter Mucha","mathematician networks"] et al., 2010.

[R11] “Resolution limit in community detection.” entity["people","Santo Fortunato","network scientist"] and entity["people","Marc Barthelemy","complex systems scientist"], 2007.

[R12] “On modularity clustering.” entity["people","Ulrik Brandes","computer scientist"] et al., 2008.

[R13] “Performance of modularity maximization in practical contexts.” entity["people","Brian Good","network scientist"] et al., 2010.

[R14] “Comparing clusterings—an information based distance.” entity["people","Marina Meila","statistician machine learning"], 2007.

[R15] “Maps of random walks on complex networks reveal community structure.” entity["people","Martin Rosvall","physicist network science"] and entity["people","Carl Bergstrom","evolutionary biologist"], 2008.

[R16] “Stochastic Blockmodels: First Steps.” entity["people","Paul W Holland","statistician"], entity["people","Kathryn B Laskey","statistician"], and entity["people","Samuel Leinhardt","sociologist"]. entity["organization","Social Networks","journal"], 1983.

[R17] “Bayesian analysis of networks” and related work on Bayesian network modeling. entity["people","Stephen E Fienberg","statistician"], various publications.

[R18] “Stochastic blockmodels and community structure in networks.” entity["people","Brian Karrer","network scientist"] and Mark Newman, 2011.

[R19] Minimum description length and Bayesian model selection approaches for SBMs (including nested SBMs). entity["people","Tiago Peixoto","physicist network inference"], 2014–2017 (representative works).

[R20] Potts-model / likelihood connections to community detection objectives in statistical physics formulations (representative works), mid-2000s.

[R21] “Mixed Membership Stochastic Blockmodels.” entity["people","Edoardo Airoldi","statistician"], entity["people","David Blei","machine learning researcher"], Stephen Fienberg, and entity["people","Eric Xing","machine learning researcher"], 2008.

[R22] Detectability thresholds in SBMs and phase transitions in inference (representative results). entity["people","Aurelien Decelle","physicist"] et al., 2011.

[R23] Complementary theoretical results on SBM detectability and limits of inference (representative results), 2010s.