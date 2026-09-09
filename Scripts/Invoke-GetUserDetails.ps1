# Requires -Modules ActiveDirectory
[CmdletBinding()]
param([Parameter(Mandatory=$true)][ValidateNotNullOrEmpty()][string]$UserIdentifier)
$ErrorActionPreference="Stop"
try {
    Import-Module ActiveDirectory -ErrorAction Stop
    if ($UserIdentifier -like "*@*") {
        $escaped=$UserIdentifier.Replace("'","''")
        $User=Get-ADUser -Filter "UserPrincipalName -eq '$escaped'" -Properties Enabled,LockedOut,UserPrincipalName,Mail,Department -ErrorAction Stop
    } else {
        $User=Get-ADUser -Identity $UserIdentifier -Properties Enabled,LockedOut,UserPrincipalName,Mail,Department -ErrorAction Stop
    }
    if ($null -eq $User) { throw "User was not found." }
    $result=[ordered]@{Name=$User.Name;SamAccountName=$User.SamAccountName;UserPrincipalName=$User.UserPrincipalName;Enabled=$User.Enabled;LockedOut=$User.LockedOut;DistinguishedName=$User.DistinguishedName;Mail=$User.Mail;Department=$User.Department}
    $result | ConvertTo-Json -Compress
    exit 0
} catch { Write-Error "FAILED: Could not retrieve '$UserIdentifier'. $($_.Exception.Message)"; exit 1 }
