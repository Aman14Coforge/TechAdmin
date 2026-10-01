from pathlib import Path


def test_script_exists():
    root = Path(__file__).resolve().parents[1]
    assert (root / "Scripts" / "Invoke-GetComputerDetails.ps1").exists()


def test_script_is_read_only():
    root = Path(__file__).resolve().parents[1]
    body = (root / "Scripts" / "Invoke-GetComputerDetails.ps1").read_text(encoding="utf-8")
    forbidden = ("Set-ADComputer", "Remove-ADComputer", "Disable-ADAccount", "Enable-ADAccount", "-Repair")
    for command in forbidden:
        assert command not in body
