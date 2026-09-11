# Guardrails

Implements the guardrails design document for the **Get User Details** and
**Reset Password** use cases.

## Files

| File | Purpose |
|---|---|
| `schemas.py` | `GuardrailDecision`, `GuardrailViolation`, `ViolationCode` — the vocabulary every check speaks |
| `policy.py` | Every tunable value: allowlists, roles, privileged accounts, limits, user-facing messages |
| `input_guardrails.py` | Checks on the raw query, before the LLM sees it |
| `authorization.py` | Role checks, privileged accounts, rate limiting, confirmation |
| `output_guardrails.py` | Field allowlisting and redaction on the way out |
| `engine.py` | Runs the checks in the order section 4.2 specifies, and writes the audit log |

## Coverage

| Design section | Where |
|---|---|
| 1.1 Query Scope Validation | `ALLOWED_INTENTS`, `check_forbidden_operations` |
| 1.2 Single User Validation | `check_single_user` |
| 1.3 Input Format Validation | `validate_identifier` |
| 1.4 Prompt Injection Protection | `check_prompt_injection` |
| 2.1 Authorization Check | `check_authorization` |
| 2.2 Minimum Data Exposure | `ALLOWED_USER_FIELDS`, `filter_user_record` |
| 2.3 No Bulk Enumeration | `check_bulk_enumeration` |
| 2.4 Output Filtering | `sanitize_response` |
| 3.1 Identity and Authorization | `check_authorization` |
| 3.2 High-Privilege Protection | `check_high_privilege`, `is_privileged_account` |
| 3.3 Password Exposure Prevention | `sanitize_response` |
| 3.4 Confirmation Requirement | `require_confirmation` |
| 3.5 Rate Limiting | `ResetRateLimiter` |
| 4.1 Validation Layer | `GuardrailEngine` |
| 4.2 Tool Execution Flow | `engine.validate_request` ordering |
| Audit logging | `engine.audit` |

## Where it runs

Three points in `Scripts/demo_flow.py`, each marked
`# --- ADDED FOR GUARDRAILS ---`:

```
Step 0   validate_input()      before extraction
Step 2b  validate_request()    after extraction, before routing
Step 6   sanitize()            on the response, before it is returned
```

Input checks run **before** extraction on purpose. A prompt injection that
reaches the extractor has already had its chance to influence the model, and a
pasted password is already in the model's context and in the logs.

## Two design choices

**Blocked requests get a generic message.** The user sees "Requested operation
is currently not supported." The rule that fired, and what it matched, go only
to the audit log. A message naming the rule tells someone probing the system
exactly what to change.

**Output filtering is allowlist-first.** User records are reduced to
`ALLOWED_USER_FIELDS` rather than having known-bad fields stripped, so a field
Microsoft adds to Graph next year is withheld by default instead of leaking
until someone notices. The blocklist then runs as a second pass over everything
else, at any nesting depth.

## Configuration

All optional; the defaults are safe.

```bash
GUARDRAIL_ALLOWED_INTENTS=get_user_details,password_reset
GUARDRAIL_DEFAULT_ROLE=helpdesk          # employee | helpdesk | admin
GUARDRAIL_PRIVILEGED_USERNAMES=administrator,admin,root,breakglass
GUARDRAIL_PRIVILEGED_TITLES=ceo,cto,cfo,president
GUARDRAIL_RESET_LIMIT=3                  # resets per account
GUARDRAIL_RESET_WINDOW=300               # within this many seconds
GUARDRAIL_CONFIRM_INTENTS=password_reset
```

## Known limits

These are real gaps, not oversights. They need work outside this package.

**Authorization trusts its caller.** `check_authorization` takes `requester_id`
and `requester_role` as arguments and believes them. That is correct for a layer
sitting behind authentication and wrong as a standalone boundary. Until
`App/apis/routes.py` authenticates the caller, `GUARDRAIL_DEFAULT_ROLE` is what
actually decides.

**The rate limiter is in-process.** Fine for the demo and for a single Streamlit
session. With multiple API workers each keeps its own counter, so the effective
limit becomes the configured value times the worker count. Move it to Redis or
the database before that matters.

**Injection detection is pattern-based.** It catches the documented phrasings
and common variants. It will not catch a novel phrasing. It is one layer, and
the intent allowlist behind it is what actually limits the damage.
