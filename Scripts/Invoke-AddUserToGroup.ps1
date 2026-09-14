# Requires -Modules ActiveDirectory
[CmdletBinding()]
Param (
    [Parameter(Mandatory=$true)] [string]$UserName,
    [Parameter(Mandatory=$true)] [string]$GroupName
)

Try {
    Add-ADGroupMember -Identity $GroupName -Members $UserName -ErrorAction Stop
    Write-Output "SUCCESS: Added '$UserName' to group '$GroupName'."
} Catch {
    Write-Error "FAILED: $($_.Exception.Message)"
    exit 1
}