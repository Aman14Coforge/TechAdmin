#Requires -Modules ActiveDirectory

<#
.SYNOPSIS
    Retrieves Active Directory user details and current account-lockout status.

.DESCRIPTION
    Resolves one Active Directory user by user principal name, SAM account
    name, distinguished name, GUID, or SID.

    The script queries the domain PDC emulator so that the computed LockedOut
    property is read from the domain controller normally used for the most
    current account-lockout information.

    Only the properties needed by the TechAdmin dashboard are requested.
    The script does not use Get-ADUser -Properties * for normal execution.

.PARAMETER UserIdentifier
    User principal name, SAM account name, distinguished name, GUID, or SID.

.EXAMPLE
    .\Invoke-GetUserDetails.ps1 `
        -UserIdentifier "MigrationTest3@Coforge.com"

.EXAMPLE
    .\Invoke-GetUserDetails.ps1 `
        -UserIdentifier "MigrationTest3"
#>

[CmdletBinding()]
param (
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$UserIdentifier
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function ConvertTo-LdapFilterValue {
    <#
    .SYNOPSIS
        Escapes a value for use inside an LDAP filter.
    #>

    [CmdletBinding()]
    param (
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $escapedValue = $Value.Replace('\', '\5c')
    $escapedValue = $escapedValue.Replace('*', '\2a')
    $escapedValue = $escapedValue.Replace('(', '\28')
    $escapedValue = $escapedValue.Replace(')', '\29')
    $escapedValue = $escapedValue.Replace([string][char]0, '\00')

    return $escapedValue
}

function ConvertFrom-FileTimeValue {
    <#
    .SYNOPSIS
        Converts an Active Directory file-time value to a readable local time.
    #>

    [CmdletBinding()]
    param (
        [Parameter(Mandatory = $false)]
        [AllowNull()]
        [object]$Value
    )

    if ($null -eq $Value) {
        return $null
    }

    try {
        $fileTime = [int64]$Value

        if ($fileTime -le 0) {
            return $null
        }

        return [DateTime]::FromFileTimeUtc($fileTime).ToLocalTime()
    }
    catch {
        return $null
    }
}

function ConvertTo-IsoDateTime {
    <#
    .SYNOPSIS
        Converts a DateTime-compatible value to an ISO-like local string.
    #>

    [CmdletBinding()]
    param (
        [Parameter(Mandatory = $false)]
        [AllowNull()]
        [object]$Value
    )

    if ($null -eq $Value) {
        return $null
    }

    try {
        return ([DateTime]$Value).ToString("yyyy-MM-dd HH:mm:ss")
    }
    catch {
        return [string]$Value
    }
}

try {
    Import-Module ActiveDirectory -ErrorAction Stop

    $executionIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $executionComputer = $env:COMPUTERNAME

    # Query the PDC emulator for the current computed lockout state.
    $domain = Get-ADDomain -ErrorAction Stop
    $pdcEmulator = [string]$domain.PDCEmulator

    if ([string]::IsNullOrWhiteSpace($pdcEmulator)) {
        throw "The domain PDC emulator could not be determined."
    }

    $requestedProperties = @(
        "DisplayName"
        "GivenName"
        "Surname"
        "Enabled"
        "LockedOut"
        "lockoutTime"
        "badPwdCount"
        "badPasswordTime"
        "LastBadPasswordAttempt"
        "PasswordExpired"
        "PasswordLastSet"
        "PasswordNeverExpires"
        "CannotChangePassword"
        "PasswordNotRequired"
        "AccountExpirationDate"
        "LastLogonDate"
        "LastLogonTimestamp"
        "UserPrincipalName"
        "Mail"
        "Department"
        "Title"
        "Office"
        "OfficePhone"
        "MobilePhone"
        "EmployeeID"
        "EmployeeNumber"
        "Description"
        "Manager"
        "whenCreated"
        "whenChanged"
        "CanonicalName"
        "MemberOf"
    )

    $user = $null

    if ($UserIdentifier -like "*@*") {
        $safeIdentifier = ConvertTo-LdapFilterValue -Value $UserIdentifier

        $matchingUsers = @(
            Get-ADUser `
                -LDAPFilter "(userPrincipalName=$safeIdentifier)" `
                -Server $pdcEmulator `
                -Properties $requestedProperties `
                -ResultSetSize 2 `
                -ErrorAction Stop
        )

        if ($matchingUsers.Count -eq 0) {
            throw "The Active Directory user '$UserIdentifier' was not found."
        }

        if ($matchingUsers.Count -gt 1) {
            throw "More than one Active Directory user matched '$UserIdentifier'."
        }

        $user = $matchingUsers[0]
    }
    else {
        $user = Get-ADUser `
            -Identity $UserIdentifier `
            -Server $pdcEmulator `
            -Properties $requestedProperties `
            -ErrorAction Stop
    }

    if ($null -eq $user) {
        throw "The Active Directory user '$UserIdentifier' was not found."
    }

    # Refresh the lockout-related computed properties against the same PDC.
    $lockoutUser = Get-ADUser `
        -Identity $user.DistinguishedName `
        -Server $pdcEmulator `
        -Properties LockedOut, lockoutTime, badPwdCount, badPasswordTime, LastBadPasswordAttempt `
        -ErrorAction Stop

    $isLockedOut = [bool]$lockoutUser.LockedOut
    $lockoutTime = ConvertFrom-FileTimeValue -Value $lockoutUser.lockoutTime
    $lastBadPasswordTime = ConvertFrom-FileTimeValue -Value $lockoutUser.badPasswordTime

    # Optional direct confirmation against the target user's OU only.
    # This avoids a domain-wide Search-ADAccount enumeration.
    $searchBase = $user.DistinguishedName -replace '^CN=(?:\\.|[^,])+,', ''
    $lockedAccountMatch = @(
        Search-ADAccount `
            -LockedOut `
            -UsersOnly `
            -SearchBase $searchBase `
            -Server $pdcEmulator `
            -ErrorAction Stop |
        Where-Object {
            $_.ObjectGUID -eq $user.ObjectGUID
        } |
        Select-Object -First 1
    )

    $searchAdAccountLockedOut = $lockedAccountMatch.Count -gt 0

    # If either supported AD check says locked, report the account as locked.
    $effectiveLockedOut = $isLockedOut -or $searchAdAccountLockedOut

    $groupCount = @($user.MemberOf).Count

    $result = [ordered]@{
        Success = $true
        Name = $user.Name
        DisplayName = $user.DisplayName
        GivenName = $user.GivenName
        Surname = $user.Surname
        SamAccountName = $user.SamAccountName
        UserPrincipalName = $user.UserPrincipalName
        Enabled = [bool]$user.Enabled
        LockedOut = [bool]$effectiveLockedOut
        LockedOutFromGetADUser = [bool]$isLockedOut
        LockedOutFromSearchADAccount = [bool]$searchAdAccountLockedOut
        LockoutStatusSource = "PDC emulator: Get-ADUser plus scoped Search-ADAccount"
        LockoutTime = ConvertTo-IsoDateTime -Value $lockoutTime
        BadPasswordCount = $lockoutUser.badPwdCount
        LastBadPasswordTime = ConvertTo-IsoDateTime -Value $lastBadPasswordTime
        LastBadPasswordAttempt = ConvertTo-IsoDateTime -Value $lockoutUser.LastBadPasswordAttempt
        PasswordExpired = [bool]$user.PasswordExpired
        PasswordLastSet = ConvertTo-IsoDateTime -Value $user.PasswordLastSet
        PasswordNeverExpires = [bool]$user.PasswordNeverExpires
        CannotChangePassword = [bool]$user.CannotChangePassword
        PasswordNotRequired = [bool]$user.PasswordNotRequired
        AccountExpirationDate = ConvertTo-IsoDateTime -Value $user.AccountExpirationDate
        LastLogonDate = ConvertTo-IsoDateTime -Value $user.LastLogonDate
        DistinguishedName = $user.DistinguishedName
        CanonicalName = $user.CanonicalName
        Mail = $user.Mail
        Department = $user.Department
        JobTitle = $user.Title
        Office = $user.Office
        OfficePhone = $user.OfficePhone
        MobilePhone = $user.MobilePhone
        EmployeeID = $user.EmployeeID
        EmployeeNumber = $user.EmployeeNumber
        Description = $user.Description
        Manager = $user.Manager
        DirectGroupMembershipCount = $groupCount
        WhenCreated = ConvertTo-IsoDateTime -Value $user.whenCreated
        WhenChanged = ConvertTo-IsoDateTime -Value $user.whenChanged
        Domain = $domain.DNSRoot
        DomainController = $pdcEmulator
        ExecutionIdentity = $executionIdentity
        ExecutionComputer = $executionComputer
    }

    $result | ConvertTo-Json -Compress -Depth 6
    exit 0
}
catch {
    $failureResult = [ordered]@{
        Success = $false
        UserIdentifier = $UserIdentifier
        ExecutionIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        ExecutionComputer = $env:COMPUTERNAME
        ErrorType = $_.Exception.GetType().FullName
        Error = $_.Exception.Message
        ScriptLineNumber = $_.InvocationInfo.ScriptLineNumber
        PositionMessage = $_.InvocationInfo.PositionMessage
    }

    Write-Error ($failureResult | ConvertTo-Json -Compress -Depth 6)
    exit 1
}
