import pytest

from App.services.patch.semantic import PatchSemanticInterpreter


@pytest.mark.parametrize(
    "query",
    [
        "Get user details for CFG-LT-2231",
        "Get details for CFG-LT-2231",
        "Reset password for CFG-LT-2231",
        "Unlock account for CFG-LT-2231",
        "Grant access to CFG-LT-2231 in the Security group",
        "Revoke access for CFG-LT-2231 from the Security group",
        "Investigate failed logins for CFG-LT-2231",
        "Why is CFG-LT-2231 locked out?",
        "Why is CFG-LT-2231's account locked?",
    ],
)
def test_identity_requests_do_not_redirect_to_security_agent(query):
    assert not PatchSemanticInterpreter.matches(query)


@pytest.mark.parametrize(
    "query",
    [
        "Show non-compliant devices",
        "Generate a patch report for CFG-LT-2231",
        "Find devices missing KB5002912",
    ],
)
def test_patch_requests_still_redirect_to_security_agent(query):
    assert PatchSemanticInterpreter.matches(query)
