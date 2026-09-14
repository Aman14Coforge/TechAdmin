# Requires -Modules ActiveDirectory
[CmdletBinding()]
Param (
    [Parameter(Mandatory=$true)] [string]$UserName,
    [Parameter(Mandatory=$true)] [string]$GroupName
)

Try {
    Remove-ADGroupMember -Identity $GroupName -Members $UserName -Confirm:$false -ErrorAction Stop
    Write-Output "SUCCESS: Removed '$UserName' from group '$GroupName'."
} Catch {
    Write-Error "FAILED: $($_.Exception.Message)"
    exit 1
}