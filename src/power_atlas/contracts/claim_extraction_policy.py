from __future__ import annotations

from dataclasses import dataclass

from power_atlas.contracts.prompts import PROMPT_IDS


@dataclass(frozen=True)
class ClaimExtractionOntology:
    claim_label: str = "ExtractedClaim"
    mention_label: str = "EntityMention"
    mentions_relationship: str = "MENTIONS"
    supported_by_relationship: str = "SUPPORTED_BY"
    mentioned_in_relationship: str = "MENTIONED_IN"
    has_participant_relationship: str = "HAS_PARTICIPANT"
    chunk_text_property: str = "text"


@dataclass(frozen=True)
class ClaimExtractionPolicy:
    ontology: ClaimExtractionOntology
    prompt_id: str


POWER_ATLAS_CLAIM_EXTRACTION_ONTOLOGY = ClaimExtractionOntology()
POWER_ATLAS_CLAIM_EXTRACTION_POLICY = ClaimExtractionPolicy(
    ontology=POWER_ATLAS_CLAIM_EXTRACTION_ONTOLOGY,
    prompt_id=PROMPT_IDS["claim_extraction"],
)


def get_default_claim_extraction_policy(
    *,
    prompt_id: str | None = None,
) -> ClaimExtractionPolicy:
    if prompt_id is None:
        return POWER_ATLAS_CLAIM_EXTRACTION_POLICY

    return ClaimExtractionPolicy(
        ontology=POWER_ATLAS_CLAIM_EXTRACTION_POLICY.ontology,
        prompt_id=prompt_id,
    )


__all__ = [
    "ClaimExtractionOntology",
    "ClaimExtractionPolicy",
    "POWER_ATLAS_CLAIM_EXTRACTION_ONTOLOGY",
    "POWER_ATLAS_CLAIM_EXTRACTION_POLICY",
    "get_default_claim_extraction_policy",
]