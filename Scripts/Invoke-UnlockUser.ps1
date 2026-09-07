# Requires -Modules ActiveDirectory
[CmdletBinding()]
Param (
    [Parameter(Mandatory=$true)] [string]$UserName
)

Try {
    Unlock-ADAccount -Identity $UserName -ErrorAction Stop
    Write-Output "SUCCESS: Account for '$UserName' has been unlocked."
} Catch {
    Write-Error "FAILED: $($_.Exception.Message)"
    exit 1
}