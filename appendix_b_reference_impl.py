import hashlib
import hmac
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def canonicalize_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


class ImmutableModel(BaseModel):
    """Immutable base used by this illustrative realization."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )


class CognitiveRole(str, Enum):
    SIGNAL = "signal"
    CONTEXT = "context"
    STATE = "state"
    MEANING = "meaning"
    MEMORY = "memory"


class ValidationStatus(str, Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    REJECTED = "rejected"


class LifecycleStatus(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    MEMORY_ELIGIBLE = "memory_eligible"
    RESTRICTED = "restricted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    SUPERSEDED = "superseded"
    HISTORICAL = "historical"


class ValidationDecision(str, Enum):
    PASS = "pass"
    FAIL = "fail"


class AuthorizationAlgorithm(str, Enum):
    HMAC_SHA256 = "hmac-sha256"


class LifecycleEventType(str, Enum):
    REJECTED = "rejected"
    RESTRICTED = "restricted"
    WITHDRAWN = "withdrawn"
    SUPERSEDED = "superseded"


class FrozenJSON(ImmutableModel):
    canonical_json: str

    @classmethod
    def from_value(cls, value: Any) -> "FrozenJSON":
        return cls(canonical_json=canonicalize_json(value))

    def to_python(self) -> Any:
        return json.loads(self.canonical_json)

    @field_serializer("canonical_json")
    def serialize_canonical_json(self, value: str) -> Any:
        return json.loads(value)


class ContractVersions(ImmutableModel):
    cu_contract_version: str = "1.0"
    profile_id: str = "generic-cu-reference"
    profile_version: str = "1.0"

    @field_validator(
        "cu_contract_version",
        "profile_id",
        "profile_version",
    )
    @classmethod
    def require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Contract-version fields cannot be empty.")
        return value


class ArtifactBoundary(ImmutableModel):
    subject_ref: str
    cognitive_scope: str
    declared_purpose: Optional[str] = None

    @field_validator("subject_ref", "cognitive_scope")
    @classmethod
    def require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Artifact-boundary fields cannot be empty.")
        return value


class TypedRelation(ImmutableModel):
    """
    Lightweight open relation.

    relation_type is deliberately not a closed enum so domain profiles can
    introduce controlled vocabularies without changing the common CU core.
    """

    relation_type: str
    target_ref: str
    scope: Optional[str] = None

    @field_validator("relation_type", "target_ref")
    @classmethod
    def require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Relation type and target reference are required.")
        return value


class CognitivePayload(ImmutableModel):
    content_type: str
    data: FrozenJSON

    @field_validator("content_type")
    @classmethod
    def require_content_type(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content_type cannot be empty.")
        return value

    @field_validator("data", mode="before")
    @classmethod
    def freeze_data(cls, value: Any) -> FrozenJSON:
        if isinstance(value, FrozenJSON):
            return value
        return FrozenJSON.from_value(value)


class SemanticContext(ImmutableModel):
    system_corpus_ref: str
    domain: str
    subject_id: str
    applicable_concepts: Tuple[str, ...] = ()

    @field_validator("system_corpus_ref", "domain", "subject_id")
    @classmethod
    def require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Semantic-context identifiers cannot be empty.")
        return value


class Traceability(ImmutableModel):
    source_evidence_ids: Tuple[str, ...] = ()
    parent_unit_ids: Tuple[str, ...] = ()
    transformation_refs: Tuple[str, ...] = ()
    producer_id: str
    production_event_id: Optional[str] = None

    @field_validator("producer_id")
    @classmethod
    def require_producer(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("producer_id cannot be empty.")
        return value


class TemporalScope(ImmutableModel):
    valid_from: datetime
    valid_until: Optional[datetime] = None

    @field_validator("valid_from", "valid_until")
    @classmethod
    def normalize_timezone(
        cls,
        value: Optional[datetime],
    ) -> Optional[datetime]:
        if value is None:
            return None

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "Temporal values must include timezone information."
            )

        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_window(self):
        if (
            self.valid_until is not None
            and self.valid_until <= self.valid_from
        ):
            raise ValueError(
                "valid_until must be later than valid_from."
            )
        return self


class ReusePolicy(ImmutableModel):
    permitted_purposes: Tuple[str, ...] = ()
    prohibited_purposes: Tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_purpose_sets(self):
        overlap = set(self.permitted_purposes) & set(
            self.prohibited_purposes
        )
        if overlap:
            raise ValueError(
                "A purpose cannot be both permitted and prohibited."
            )
        return self


class GovernancePolicy(ImmutableModel):
    """
    Governance information carried by this compact reference profile.

    Validation status and lifecycle status are intentionally distinct.
    External attestations and lifecycle events may add evidence without
    mutating the original artifact.
    """

    validation_status: ValidationStatus = ValidationStatus.PENDING
    lifecycle_status: LifecycleStatus = LifecycleStatus.CANDIDATE

    required_authorization_role: Optional[str] = None
    requires_authorization: bool = False
    policy_id: Optional[str] = None
    restrictions: Tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_governance_state(self):
        if (
            self.required_authorization_role is not None
            and not self.requires_authorization
        ):
            raise ValueError(
                "A required authorization role requires "
                "requires_authorization=True."
            )

        if self.lifecycle_status in {
            LifecycleStatus.ACTIVE,
            LifecycleStatus.MEMORY_ELIGIBLE,
        } and self.validation_status != ValidationStatus.VALIDATED:
            raise ValueError(
                "Active or memory-eligible artifacts must be validated."
            )

        if (
            self.lifecycle_status == LifecycleStatus.REJECTED
            and self.validation_status != ValidationStatus.REJECTED
        ):
            raise ValueError(
                "Rejected lifecycle status requires rejected validation."
            )

        if (
            self.validation_status == ValidationStatus.REJECTED
            and self.lifecycle_status
            not in {
                LifecycleStatus.REJECTED,
                LifecycleStatus.HISTORICAL,
            }
        ):
            raise ValueError(
                "Rejected validation cannot remain candidate, active, "
                "memory-eligible, restricted, withdrawn, or superseded."
            )

        return self


class CognitiveUnit(ImmutableModel):
    """
    One immutable Cognitive Unit artifact in this implementation.

    A material revision creates another independently identifiable
    artifact rather than silently overwriting this one.
    """

    unit_id: str = Field(default_factory=lambda: str(uuid4()))
    lineage_id: str = Field(default_factory=lambda: str(uuid4()))

    unit_type: str
    role: CognitiveRole

    revision_number: int = Field(default=1, ge=1)
    revision_of_unit_id: Optional[str] = None

    artifact_boundary: ArtifactBoundary
    contract_versions: ContractVersions = Field(
        default_factory=ContractVersions
    )

    created_at: datetime = Field(default_factory=utc_now)

    cognitive_payload: CognitivePayload
    semantic_context: SemanticContext
    governance_policy: GovernancePolicy
    traceability: Traceability
    temporal_scope: TemporalScope
    reuse_policy: ReusePolicy

    relations: Tuple[TypedRelation, ...] = ()

    @field_validator("unit_type")
    @classmethod
    def require_unit_type(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("unit_type cannot be empty.")
        return value

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "created_at must include timezone information."
            )
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_revision_relationship(self):
        if self.revision_number == 1 and self.revision_of_unit_id is not None:
            raise ValueError(
                "Revision 1 cannot reference a preceding revision."
            )

        if self.revision_number > 1 and self.revision_of_unit_id is None:
            raise ValueError(
                "Revisions greater than 1 must reference the "
                "preceding artifact in this implementation."
            )

        if self.revision_of_unit_id == self.unit_id:
            raise ValueError(
                "A Cognitive Unit cannot revise itself."
            )

        return self

    @model_validator(mode="after")
    def validate_boundary_alignment(self):
        if (
            self.artifact_boundary.subject_ref
            != self.semantic_context.subject_id
        ):
            raise ValueError(
                "Artifact boundary subject and semantic-context subject "
                "must refer to the same subject in this compact profile."
            )

        for relation in self.relations:
            if relation.target_ref == self.unit_id:
                raise ValueError(
                    "A Cognitive Unit cannot contain a self-relation."
                )

        return self

    def canonical_content(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")

    def canonical_json(self) -> str:
        return canonicalize_json(self.canonical_content())

    def compute_content_hash(self) -> str:
        canonical_bytes = self.canonical_json().encode("utf-8")
        return hashlib.sha256(canonical_bytes).hexdigest()

    def is_temporally_applicable(
        self,
        at: Optional[datetime] = None,
    ) -> bool:
        moment = at or utc_now()

        if moment.tzinfo is None or moment.utcoffset() is None:
            raise ValueError(
                "Evaluation time must include timezone information."
            )

        moment = moment.astimezone(timezone.utc)

        if moment < self.temporal_scope.valid_from:
            return False

        if (
            self.temporal_scope.valid_until is not None
            and moment > self.temporal_scope.valid_until
        ):
            return False

        return True


class CUValidationIssue(ImmutableModel):
    code: str
    message: str


class CUValidationResult(ImmutableModel):
    """
    Explicit validation-boundary result.

    This result establishes only conformance to this compact reference
    profile. It does not establish substantive truth or domain validity.
    """

    result_id: str = Field(default_factory=lambda: str(uuid4()))
    unit_id: str
    content_hash: str

    decision: ValidationDecision
    validator_id: str
    validated_at: datetime = Field(default_factory=utc_now)

    issues: Tuple[CUValidationIssue, ...] = ()

    @field_validator("validated_at")
    @classmethod
    def normalize_validated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "validated_at must include timezone information."
            )
        return value.astimezone(timezone.utc)

    @property
    def passed(self) -> bool:
        return self.decision == ValidationDecision.PASS


def validate_cu_envelope(
    unit: CognitiveUnit,
    *,
    validator_id: str = "reference-cu-validator",
    supported_contract_versions: Tuple[str, ...] = ("1.0",),
) -> CUValidationResult:
    """
    Validate the minimum reference envelope before downstream admission.

    Pydantic has already established structural well-formedness. This
    boundary adds profile-level checks that remain explicit and auditable.
    """

    issues = []

    if (
        unit.contract_versions.cu_contract_version
        not in supported_contract_versions
    ):
        issues.append(
            CUValidationIssue(
                code="unsupported_contract_version",
                message=(
                    "The CU contract version is not supported by this "
                    "validation boundary."
                ),
            )
        )

    if (
        unit.governance_policy.lifecycle_status
        in {
            LifecycleStatus.ACTIVE,
            LifecycleStatus.MEMORY_ELIGIBLE,
        }
        and unit.governance_policy.validation_status
        != ValidationStatus.VALIDATED
    ):
        issues.append(
            CUValidationIssue(
                code="active_without_validation",
                message=(
                    "Active or memory-eligible artifacts require "
                    "validated standing."
                ),
            )
        )

    if not unit.semantic_context.system_corpus_ref.strip():
        issues.append(
            CUValidationIssue(
                code="missing_system_corpus_ref",
                message="A System Corpus reference is required.",
            )
        )

    decision = (
        ValidationDecision.PASS
        if not issues
        else ValidationDecision.FAIL
    )

    return CUValidationResult(
        unit_id=unit.unit_id,
        content_hash=unit.compute_content_hash(),
        decision=decision,
        validator_id=validator_id,
        issues=tuple(issues),
    )


class AuthorizationAttestation(ImmutableModel):
    """
    External authorization evidence bound to one exact artifact.

    This does not replace the Cognitive Unit's governance information.
    It is one possible external governance mechanism.
    """

    attestation_id: str = Field(default_factory=lambda: str(uuid4()))

    unit_id: str
    lineage_id: str
    revision_number: int
    content_hash: str

    authorized_by: str
    authorization_role: Optional[str] = None
    authorization_mechanism: str = "explicit"

    authorized_at: datetime = Field(default_factory=utc_now)

    algorithm: AuthorizationAlgorithm = (
        AuthorizationAlgorithm.HMAC_SHA256
    )

    key_id: Optional[str] = None
    signature: str

    @field_validator("authorized_at")
    @classmethod
    def normalize_authorized_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "authorized_at must include timezone information."
            )
        return value.astimezone(timezone.utc)

    def verify(
        self,
        unit: CognitiveUnit,
        secret_key: str,
    ) -> bool:
        if self.algorithm != AuthorizationAlgorithm.HMAC_SHA256:
            return False

        if self.unit_id != unit.unit_id:
            return False

        if self.lineage_id != unit.lineage_id:
            return False

        if self.revision_number != unit.revision_number:
            return False

        required_role = unit.governance_policy.required_authorization_role
        if (
            required_role is not None
            and self.authorization_role != required_role
        ):
            return False

        current_hash = unit.compute_content_hash()

        if not hmac.compare_digest(
            self.content_hash,
            current_hash,
        ):
            return False

        expected_signature = hmac.new(
            secret_key.encode("utf-8"),
            current_hash.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(
            self.signature,
            expected_signature,
        )


class LifecycleEvent(ImmutableModel):
    """Append-only fact associated with a Cognitive Unit."""

    event_id: str = Field(default_factory=lambda: str(uuid4()))

    unit_id: str
    lineage_id: str
    revision_number: int

    event_type: LifecycleEventType
    occurred_at: datetime = Field(default_factory=utc_now)

    actor_id: Optional[str] = None
    actor_role: Optional[str] = None

    related_unit_id: Optional[str] = None
    scope: Optional[str] = None
    reason: Optional[str] = None

    @field_validator("occurred_at")
    @classmethod
    def normalize_occurred_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "occurred_at must include timezone information."
            )
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_event_relationship(self):
        if (
            self.event_type == LifecycleEventType.SUPERSEDED
            and self.related_unit_id is None
        ):
            raise ValueError(
                "A supersession event must identify the related unit."
            )
        return self


def derive_revision(
    previous: CognitiveUnit,
    *,
    unit_type: Optional[str] = None,
    artifact_boundary: Optional[ArtifactBoundary] = None,
    contract_versions: Optional[ContractVersions] = None,
    cognitive_payload: Optional[CognitivePayload] = None,
    semantic_context: Optional[SemanticContext] = None,
    governance_policy: Optional[GovernancePolicy] = None,
    traceability: Optional[Traceability] = None,
    temporal_scope: Optional[TemporalScope] = None,
    reuse_policy: Optional[ReusePolicy] = None,
    relations: Optional[Tuple[TypedRelation, ...]] = None,
) -> CognitiveUnit:
    """Create a revised artifact without modifying the preceding one."""

    return CognitiveUnit(
        unit_id=str(uuid4()),
        lineage_id=previous.lineage_id,

        unit_type=(
            unit_type
            if unit_type is not None
            else previous.unit_type
        ),
        role=previous.role,

        revision_number=previous.revision_number + 1,
        revision_of_unit_id=previous.unit_id,

        artifact_boundary=(
            artifact_boundary
            if artifact_boundary is not None
            else previous.artifact_boundary
        ),
        contract_versions=(
            contract_versions
            if contract_versions is not None
            else previous.contract_versions
        ),

        created_at=utc_now(),

        cognitive_payload=(
            cognitive_payload
            if cognitive_payload is not None
            else previous.cognitive_payload
        ),
        semantic_context=(
            semantic_context
            if semantic_context is not None
            else previous.semantic_context
        ),
        governance_policy=(
            governance_policy
            if governance_policy is not None
            else previous.governance_policy
        ),
        traceability=(
            traceability
            if traceability is not None
            else previous.traceability
        ),
        temporal_scope=(
            temporal_scope
            if temporal_scope is not None
            else previous.temporal_scope
        ),
        reuse_policy=(
            reuse_policy
            if reuse_policy is not None
            else previous.reuse_policy
        ),
        relations=(
            relations
            if relations is not None
            else previous.relations
        ),
    )


def authorize_unit(
    unit: CognitiveUnit,
    *,
    authorized_by: str,
    secret_key: str,
    authorization_role: Optional[str] = None,
    authorization_mechanism: str = "explicit",
    key_id: Optional[str] = None,
) -> AuthorizationAttestation:

    policy = unit.governance_policy

    if (
        policy.required_authorization_role is not None
        and authorization_role != policy.required_authorization_role
    ):
        raise PermissionError(
            "Authorization role does not satisfy the "
            "Cognitive Unit governance policy."
        )

    content_hash = unit.compute_content_hash()

    signature = hmac.new(
        secret_key.encode("utf-8"),
        content_hash.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return AuthorizationAttestation(
        unit_id=unit.unit_id,
        lineage_id=unit.lineage_id,
        revision_number=unit.revision_number,
        content_hash=content_hash,
        authorized_by=authorized_by,
        authorization_role=authorization_role,
        authorization_mechanism=authorization_mechanism,
        key_id=key_id,
        signature=signature,
    )


def is_eligible_for_use(
    unit: CognitiveUnit,
    *,
    purpose: str,
    authorization: Optional[AuthorizationAttestation],
    lifecycle_events: Tuple[LifecycleEvent, ...],
    secret_key: Optional[str] = None,
    at: Optional[datetime] = None,
) -> bool:
    """
    Evaluate future-use eligibility for one purpose.

    Historical retrievability is not affected by this evaluation.
    """

    if not unit.is_temporally_applicable(at):
        return False

    governance = unit.governance_policy

    if governance.validation_status != ValidationStatus.VALIDATED:
        return False

    if governance.lifecycle_status in {
        LifecycleStatus.CANDIDATE,
        LifecycleStatus.RESTRICTED,
        LifecycleStatus.REJECTED,
        LifecycleStatus.WITHDRAWN,
        LifecycleStatus.SUPERSEDED,
    }:
        return False

    if purpose in unit.reuse_policy.prohibited_purposes:
        return False

    if (
        unit.reuse_policy.permitted_purposes
        and purpose not in unit.reuse_policy.permitted_purposes
    ):
        return False

    if governance.requires_authorization:
        if authorization is None or secret_key is None:
            return False

        if not authorization.verify(unit, secret_key):
            return False

    for event in lifecycle_events:
        if event.unit_id != unit.unit_id:
            continue

        if (
            event.lineage_id != unit.lineage_id
            or event.revision_number != unit.revision_number
        ):
            continue

        if event.event_type in {
            LifecycleEventType.REJECTED,
            LifecycleEventType.WITHDRAWN,
        }:
            return False

        if event.event_type == LifecycleEventType.RESTRICTED:
            if event.scope is None or event.scope == purpose:
                return False

        if event.event_type == LifecycleEventType.SUPERSEDED:
            if event.scope is None or event.scope == purpose:
                return False

    return True


if __name__ == "__main__":

    secret_key = "reference-secret"

    unit_v1 = CognitiveUnit(
        unit_type="RecognizedOperationalCondition",
        role=CognitiveRole.STATE,

        artifact_boundary=ArtifactBoundary(
            subject_ref="SUBJECT-001",
            cognitive_scope="recognized operational condition",
            declared_purpose="operational_assessment",
        ),

        contract_versions=ContractVersions(
            cu_contract_version="1.0",
            profile_id="generic-state-profile",
            profile_version="1.0",
        ),

        cognitive_payload=CognitivePayload(
            content_type="recognized_state",
            data={
                "state": "normal",
                "confidence": 0.82,
            },
        ),

        semantic_context=SemanticContext(
            system_corpus_ref="CORPUS-EXAMPLE-001",
            domain="example_domain",
            subject_id="SUBJECT-001",
            applicable_concepts=(
                "recognized_state",
                "state_revision",
            ),
        ),

        governance_policy=GovernancePolicy(
            validation_status=ValidationStatus.VALIDATED,
            lifecycle_status=LifecycleStatus.ACTIVE,
            required_authorization_role="reviewer",
            requires_authorization=True,
            policy_id="POLICY-001",
            restrictions=(),
        ),

        traceability=Traceability(
            source_evidence_ids=(
                "EVIDENCE-001",
                "EVIDENCE-002",
            ),
            parent_unit_ids=(),
            transformation_refs=("TRANSFORMATION-001",),
            producer_id="PRODUCER-001",
            production_event_id="PRODUCTION-001",
        ),

        temporal_scope=TemporalScope(
            valid_from=datetime(
                2026,
                8,
                1,
                tzinfo=timezone.utc,
            ),
            valid_until=None,
        ),

        reuse_policy=ReusePolicy(
            permitted_purposes=(
                "operational_assessment",
                "historical_review",
            ),
            prohibited_purposes=(),
        ),

        relations=(),
    )

    validation_v1 = validate_cu_envelope(unit_v1)
    assert validation_v1.passed

    authorization_v1 = authorize_unit(
        unit_v1,
        authorized_by="AUTHORITY-001",
        authorization_role="reviewer",
        authorization_mechanism="human_review",
        secret_key=secret_key,
        key_id="KEY-001",
    )

    assert authorization_v1.verify(unit_v1, secret_key)

    unit_v2 = derive_revision(
        unit_v1,

        cognitive_payload=CognitivePayload(
            content_type="recognized_state",
            data={
                "state": "degraded",
                "confidence": 0.91,
            },
        ),

        traceability=Traceability(
            source_evidence_ids=(
                "EVIDENCE-001",
                "EVIDENCE-002",
                "EVIDENCE-003",
            ),
            parent_unit_ids=(),
            transformation_refs=("TRANSFORMATION-002",),
            producer_id="PRODUCER-001",
            production_event_id="PRODUCTION-002",
        ),

        relations=(
            TypedRelation(
                relation_type="revises",
                target_ref=unit_v1.unit_id,
                scope="operational_assessment",
            ),
        ),
    )

    validation_v2 = validate_cu_envelope(unit_v2)
    assert validation_v2.passed

    authorization_v2 = authorize_unit(
        unit_v2,
        authorized_by="AUTHORITY-001",
        authorization_role="reviewer",
        authorization_mechanism="human_review",
        secret_key=secret_key,
        key_id="KEY-001",
    )

    supersession_event = LifecycleEvent(
        unit_id=unit_v1.unit_id,
        lineage_id=unit_v1.lineage_id,
        revision_number=unit_v1.revision_number,
        event_type=LifecycleEventType.SUPERSEDED,
        actor_id="AUTHORITY-001",
        actor_role="reviewer",
        related_unit_id=unit_v2.unit_id,
        scope="operational_assessment",
        reason=(
            "A revised artifact became applicable for active "
            "operational assessment."
        ),
    )

    lifecycle_events = (supersession_event,)

    assert unit_v1.unit_id != unit_v2.unit_id
    assert unit_v1.lineage_id == unit_v2.lineage_id
    assert unit_v2.revision_of_unit_id == unit_v1.unit_id

    assert (
        unit_v1.cognitive_payload.data.to_python()["state"]
        == "normal"
    )
    assert (
        unit_v2.cognitive_payload.data.to_python()["state"]
        == "degraded"
    )

    assert unit_v2.relations[0].target_ref == unit_v1.unit_id

    assert authorization_v1.verify(unit_v1, secret_key)
    assert not authorization_v1.verify(unit_v2, secret_key)
    assert authorization_v2.verify(unit_v2, secret_key)

    assert (
        is_eligible_for_use(
            unit_v1,
            purpose="operational_assessment",
            authorization=authorization_v1,
            lifecycle_events=lifecycle_events,
            secret_key=secret_key,
        )
        is False
    )

    assert (
        is_eligible_for_use(
            unit_v1,
            purpose="historical_review",
            authorization=authorization_v1,
            lifecycle_events=lifecycle_events,
            secret_key=secret_key,
        )
        is True
    )

    assert (
        is_eligible_for_use(
            unit_v2,
            purpose="operational_assessment",
            authorization=authorization_v2,
            lifecycle_events=lifecycle_events,
            secret_key=secret_key,
        )
        is True
    )

    candidate_unit = CognitiveUnit(
        unit_type="CandidateInterpretation",
        role=CognitiveRole.MEANING,
        artifact_boundary=ArtifactBoundary(
            subject_ref="SUBJECT-001",
            cognitive_scope="candidate interpretation",
        ),
        cognitive_payload=CognitivePayload(
            content_type="interpretation",
            data={"statement": "candidate"},
        ),
        semantic_context=SemanticContext(
            system_corpus_ref="CORPUS-EXAMPLE-001",
            domain="example_domain",
            subject_id="SUBJECT-001",
        ),
        governance_policy=GovernancePolicy(
            validation_status=ValidationStatus.PENDING,
            lifecycle_status=LifecycleStatus.CANDIDATE,
        ),
        traceability=Traceability(
            producer_id="PRODUCER-002",
        ),
        temporal_scope=TemporalScope(
            valid_from=datetime(
                2026,
                8,
                1,
                tzinfo=timezone.utc,
            ),
        ),
        reuse_policy=ReusePolicy(
            permitted_purposes=("historical_review",),
        ),
    )

    assert validate_cu_envelope(candidate_unit).passed
    assert (
        is_eligible_for_use(
            candidate_unit,
            purpose="historical_review",
            authorization=None,
            lifecycle_events=(),
        )
        is False
    )
