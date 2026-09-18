from App.db.login_authorization import extract_display_name


def test_extract_display_name_uses_email_when_name_missing():
    claims = {"email": "user@coforge.com"}
    assert extract_display_name(claims) == "user@coforge.com"


def test_extract_display_name_uses_upn_when_name_missing():
    claims = {"userPrincipalName": "user@coforge.com"}
    assert extract_display_name(claims) == "user@coforge.com"


def test_extract_display_name_uses_nonempty_email_array_value():
    claims = {"emails": ["user@coforge.com"]}
    assert extract_display_name(claims) == "user@coforge.com"


def test_extract_display_name_ignores_boolean_claim_noise():
    claims = {"auth_time": 123456, "isAuthenticated": False, "name": False}
    assert extract_display_name(claims) == ""
