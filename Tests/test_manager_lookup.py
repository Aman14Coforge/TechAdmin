from App.tools.identity.hybrid_identity import _manager_from_script


def test_manager_from_script_reads_manager_fields_when_present():
    user = {
        "Manager": "CN=Jane Doe,OU=Leadership,DC=contoso,DC=com",
        "ManagerName": "Jane Doe",
        "ManagerEmail": "jane.doe@contoso.com",
    }

    assert _manager_from_script(user) == ("Jane Doe", "jane.doe@contoso.com")


def test_manager_from_script_falls_back_to_cn_from_manager_dn():
    user = {
        "Manager": "CN=John Smith,OU=Leadership,DC=contoso,DC=com",
    }

    assert _manager_from_script(user) == ("John Smith", "Not Available")
