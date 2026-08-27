from __future__ import annotations

import re

from App.schemas.models import (
    ExtractedFields,
    Intent,
    LLMExtraction,
    ValidationResult,
)


IDENTITY_FIELDS: tuple[str, ...] = (
    "username",
    "email",
    "employee_id",
)


MANDATORY_FIELDS_BY_INTENT: dict[
    Intent,
    tuple[str, ...],
] = {
    Intent.PASSWORD_RESET: IDENTITY_FIELDS,
    Intent.ACCOUNT_UNLOCK: IDENTITY_FIELDS,
    Intent.GRANT_ACCESS: (
        "username",
        "email",
        "employee_id",
        "group_name",
    ),
    Intent.REVOKE_ACCESS: (
        "username",
        "email",
        "employee_id",
        "group_name",
    ),
    Intent.FAILED_LOGIN_INVESTIGATION:
        IDENTITY_FIELDS,
}


EMAIL_PATTERN = re.compile(
    r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
)


def _has_literal_evidence(
    user_query: str,
    value: str | None,
) -> bool:
    """
    A missing value is handled by mandatory-field validation.

    A populated LLM value is accepted only when the literal value
    appears in the source request.
    """

    if value is None:
        return True

    return (
        value.casefold()
        in user_query.casefold()
    )


def derive_username_from_email(
    email: str | None,
) -> str | None:
    """
    Derives the account username from the local part of an explicitly
    provided email address.

    Example:

        Shreesanyog.Rath@Coforge.com
        -> Shreesanyog.Rath

    This is deterministic normalization, not LLM inference.
    """

    if email is None:
        return None

    normalized_email = email.strip()

    if not EMAIL_PATTERN.fullmatch(
        normalized_email,
    ):
        return None

    local_part, _, _ = normalized_email.partition(
        "@"
    )

    normalized_username = local_part.strip()

    if not normalized_username:
        return None

    return normalized_username


def _apply_evidence_guard(
    user_query: str,
    extraction: LLMExtraction,
) -> tuple[
    dict[str, str | None],
    list[str],
]:
    extracted_data: dict[str, str | None] = {
        "username": extraction.username,
        "email": extraction.email,
        "employee_id": extraction.employee_id,
        "group_name": extraction.group_name,
        "time_window": extraction.time_window,
    }

    rejected_fields: list[str] = []

    for field_name, value in extracted_data.items():
        if not _has_literal_evidence(
            user_query,
            value,
        ):
            extracted_data[field_name] = None
            rejected_fields.append(
                field_name,
            )

    return extracted_data, rejected_fields


def _apply_deterministic_derivations(
    extracted_data: dict[
        str,
        str | None,
    ],
) -> tuple[
    dict[str, str | None],
    list[str],
]:
    derived_fields: list[str] = []

    if (
        extracted_data.get("username") is None
        and extracted_data.get("email")
    ):
        derived_username = derive_username_from_email(
            extracted_data["email"],
        )

        if derived_username:
            extracted_data["username"] = (
                derived_username
            )

            extracted_data["username_source"] = (
                "derived_from_email"
            )

            derived_fields.append(
                "username",
            )

    if extracted_data.get("username"):
        extracted_data.setdefault(
            "username_source",
            "explicit",
        )

    return extracted_data, derived_fields


def _mandatory_fields_for_intent(
    intent: Intent,
) -> tuple[str, ...]:
    return MANDATORY_FIELDS_BY_INTENT.get(
        intent,
        tuple(),
    )


def validate(
    user_query: str,
    extraction: LLMExtraction,
) -> tuple[
    ExtractedFields,
    ValidationResult,
]:
    """
    Validation sequence:

    1. Reject unsupported LLM attributes.
    2. Derive username from explicit email when possible.
    3. Check mandatory fields for the intent.
    4. Return a Pydantic validation decision.
    """

    (
        extracted_data,
        rejected_fields,
    ) = _apply_evidence_guard(
        user_query,
        extraction,
    )

    (
        extracted_data,
        derived_fields,
    ) = _apply_deterministic_derivations(
        extracted_data,
    )

    fields = ExtractedFields.model_validate(
        extracted_data,
    )

    if extraction.intent is Intent.UNKNOWN:
        return fields, ValidationResult(
            is_valid=False,
            missing_fields=[],
            rejected_fields=rejected_fields,
            derived_fields=derived_fields,
            reason=(
                "The request does not match a supported "
                "Identity and Access Management intent."
            ),
        )

    mandatory_fields = (
        _mandatory_fields_for_intent(
            extraction.intent,
        )
    )

    if not mandatory_fields:
        return fields, ValidationResult(
            is_valid=False,
            missing_fields=[],
            rejected_fields=rejected_fields,
            derived_fields=derived_fields,
            reason=(
                "No validation policy is configured "
                f"for intent "
                f"'{extraction.intent.value}'."
            ),
        )

    missing_fields = [
        field_name
        for field_name in mandatory_fields
        if getattr(
            fields,
            field_name,
        )
        is None
    ]

    if missing_fields:
        return fields, ValidationResult(
            is_valid=False,
            missing_fields=missing_fields,
            rejected_fields=rejected_fields,
            derived_fields=derived_fields,
            reason=(
                "Additional information is required "
                "before the Identity Agent can call "
                "the selected tool."
            ),
        )

    return fields, ValidationResult(
        is_valid=True,
        missing_fields=[],
        rejected_fields=rejected_fields,
        derived_fields=derived_fields,
        reason=None,
    )