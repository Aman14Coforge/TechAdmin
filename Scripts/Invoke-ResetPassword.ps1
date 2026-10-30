#Requires -Modules ActiveDirectory

[CmdletBinding()]
param (
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$UserName
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

try {
    Import-Module ActiveDirectory -ErrorAction Stop

    $newPassword = [string]$env:TECHADMIN_NEW_PASSWORD

    if (:IsNullOrWhiteSpace($newPassword)) {
        throw "TECHADMIN_NEW_PASSWORD is missing from the secure process environment."
    }

    $user = Get-ADUser `
        -Identity $UserName `
        -Properties DisplayName, UserPrincipalName, Mail, Manager `
        -ErrorAction Stop

    $securePassword = ConvertTo-SecureString `
        $newPassword `
        -AsPlainText `
        -Force

    Set-ADAccountPassword `
        -Identity $user.DistinguishedName `
        -NewPassword $securePassword `
        -Reset:$true `
        -ErrorAction Stop

    Set-ADUser `
        -Identity $user.DistinguishedName `
        -ChangePasswordAtLogon $true `
        -ErrorAction Stop

    $managerName = $null
    $managerEmail = $null

    if (
        $null -ne $user.Manager `
        -and -not :IsNullOrWhiteSpace(
            [string]$user.Manager
        )
    ) {
        try {
            $manager = Get-ADUser `
                -Identity $user.Manager `
                -Properties DisplayName, UserPrincipalName, Mail `
                -ErrorAction Stop

            $managerName = $manager.DisplayName

            if (
                -not :IsNullOrWhiteSpace(
                    [string]$manager.Mail
                )
            ) {
                $managerEmail = $manager.Mail
            }
            else {
                $managerEmail = $manager.UserPrincipalName
            }
        }
        catch {
            $managerName = $null
            $managerEmail = $null
        }
    }

    $result = [ordered]@{
        Success = $true
        UserName = $user.SamAccountName
        DisplayName = $user.DisplayName
        UserPrincipalName = $user.UserPrincipalName
        Mail = $user.Mail
        ManagerName = $managerName
        ManagerEmail = $managerEmail
        ChangePasswordAtLogon = $true
        Message = (
            "Password reset completed successfully. " +
            "The user must change the temporary password at next logon."
        )
    }

    $result |
        ConvertTo-Json `
            -Compress `
            -Depth 6

    exit 0
}
catch {
    $failure = [ordered]@{
        Success = $false
        UserName = $UserName
        ErrorType = $_.Exception.GetType().FullName
        Error = $_.Exception.Message
        ScriptLineNumber = $_.InvocationInfo.ScriptLineNumber
    }

    Write-Error (
        $failure |
            ConvertTo-Json `
                -Compress `
                -Depth 6
    )

    exit 1
}
finally {
    Remove-Item `
        Env:TECHADMIN_NEW_PASSWORD `
        -ErrorAction SilentlyContinue
}