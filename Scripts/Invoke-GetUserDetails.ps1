#Requires -Modules ActiveDirectory

<#
.SYNOPSIS
    Retrieves Active Directory user, lockout, manager, and group details.

.DESCRIPTION
    Resolves one Active Directory user by user principal name, SAM account
    name, distinguished name, GUID, or SID.

    The script queries the domain PDC emulator for current account-lockout
    information. It returns direct groups, recursively resolved nested parent
    groups, the primary group, and a unique effective group list.

    Users with no direct MemberOf values are handled successfully. Such users
    can still have a primary group, commonly Domain Users.

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


function Get-ObjectPropertyValue {
    [CmdletBinding()]
    param (
        [Parameter(Mandatory = $false)]
        [AllowNull()]
        [object]$InputObject,

        [Parameter(Mandatory = $true)]
        [ValidateNotNullOrEmpty()]
        [string]$PropertyName
    )

    if ($null -eq $InputObject) {
        return $null
    }

    $property = $InputObject.PSObject.Properties[$PropertyName]

    if ($null -eq $property) {
        return $null
    }

    return $property.Value
}


function New-GroupRecord {
    [CmdletBinding()]
    param (
        [Parameter(Mandatory = $true)]
        [object]$Group,

        [Parameter(Mandatory = $true)]
        [ValidateSet("Primary", "Direct", "Nested")]
        [string]$MembershipType,

        [Parameter(Mandatory = $false)]
        [AllowNull()]
        [string]$InheritedFrom,

        [Parameter(Mandatory = $false)]
        [int]$NestingLevel = 0,

        [Parameter(Mandatory = $false)]
        [AllowNull()]
        [string]$ResolutionError
    )

    $groupCategory = Get-ObjectPropertyValue `
        -InputObject $Group `
        -PropertyName "GroupCategory"

    $groupScope = Get-ObjectPropertyValue `
        -InputObject $Group `
        -PropertyName "GroupScope"

    return [PSCustomObject][ordered]@{
        Name = Get-ObjectPropertyValue `
            -InputObject $Group `
            -PropertyName "Name"
        SamAccountName = Get-ObjectPropertyValue `
            -InputObject $Group `
            -PropertyName "SamAccountName"
        DistinguishedName = Get-ObjectPropertyValue `
            -InputObject $Group `
            -PropertyName "DistinguishedName"
        GroupCategory = if ($null -ne $groupCategory) {
            [string]$groupCategory
        }
        else {
            $null
        }
        GroupScope = if ($null -ne $groupScope) {
            [string]$groupScope
        }
        else {
            $null
        }
        Description = Get-ObjectPropertyValue `
            -InputObject $Group `
            -PropertyName "Description"
        MembershipType = $MembershipType
        NestingLevel = $NestingLevel
        InheritedFrom = $InheritedFrom
        ResolutionError = $ResolutionError
    }
}


function Get-DirectGroups {
    [CmdletBinding()]
    param (
        [Parameter(Mandatory = $false)]
        [AllowNull()]
        [AllowEmptyCollection()]
        [object[]]$MemberOf = @(),

        [Parameter(Mandatory = $true)]
        [ValidateNotNullOrEmpty()]
        [string]$Server
    )

    $results = @()

    if ($null -eq $MemberOf -or @($MemberOf).Count -eq 0) {
        return @()
    }

    foreach ($groupDn in @($MemberOf)) {
        if ([string]::IsNullOrWhiteSpace([string]$groupDn)) {
            continue
        }

        try {
            $group = Get-ADGroup `
                -Identity $groupDn `
                -Server $Server `
                -Properties Description, MemberOf `
                -ErrorAction Stop

            $results += $group
        }
        catch {
            $results += [PSCustomObject]@{
                Name = $null
                SamAccountName = $null
                DistinguishedName = [string]$groupDn
                GroupCategory = $null
                GroupScope = $null
                Description = $null
                MemberOf = @()
                ResolutionError = $_.Exception.Message
            }
        }
    }

    return @(
        $results |
        Sort-Object Name, DistinguishedName
    )
}


function Get-NestedGroups {
    [CmdletBinding()]
    param (
        [Parameter(Mandatory = $false)]
        [AllowNull()]
        [AllowEmptyCollection()]
        [object[]]$DirectGroups = @(),

        [Parameter(Mandatory = $true)]
        [ValidateNotNullOrEmpty()]
        [string]$Server
    )

    $results = @()
    $visited = @{}
    $queue = New-Object System.Collections.Queue

    if ($null -eq $DirectGroups -or @($DirectGroups).Count -eq 0) {
        return @()
    }

    foreach ($directGroup in @($DirectGroups)) {
        if ($null -eq $directGroup) {
            continue
        }

        $directDn = [string](
            Get-ObjectPropertyValue `
                -InputObject $directGroup `
                -PropertyName "DistinguishedName"
        )

        if (-not [string]::IsNullOrWhiteSpace($directDn)) {
            $visited[$directDn.ToLowerInvariant()] = $true
        }

        $directName = [string](
            Get-ObjectPropertyValue `
                -InputObject $directGroup `
                -PropertyName "Name"
        )

        $parentGroups = @(
            Get-ObjectPropertyValue `
                -InputObject $directGroup `
                -PropertyName "MemberOf"
        )

        foreach ($parentDn in $parentGroups) {
            if ([string]::IsNullOrWhiteSpace([string]$parentDn)) {
                continue
            }

            $queue.Enqueue(
                [PSCustomObject]@{
                    DistinguishedName = [string]$parentDn
                    InheritedFrom = $directName
                    Level = 1
                }
            )
        }
    }

    while ($queue.Count -gt 0) {
        $item = $queue.Dequeue()
        $groupDn = [string]$item.DistinguishedName

        if ([string]::IsNullOrWhiteSpace($groupDn)) {
            continue
        }

        $visitedKey = $groupDn.ToLowerInvariant()

        if ($visited.ContainsKey($visitedKey)) {
            continue
        }

        $visited[$visitedKey] = $true

        try {
            $group = Get-ADGroup `
                -Identity $groupDn `
                -Server $Server `
                -Properties Description, MemberOf `
                -ErrorAction Stop

            $results += New-GroupRecord `
                -Group $group `
                -MembershipType "Nested" `
                -InheritedFrom ([string]$item.InheritedFrom) `
                -NestingLevel ([int]$item.Level)

            foreach ($parentDn in @($group.MemberOf)) {
                if ([string]::IsNullOrWhiteSpace([string]$parentDn)) {
                    continue
                }

                $parentKey = ([string]$parentDn).ToLowerInvariant()

                if (-not $visited.ContainsKey($parentKey)) {
                    $queue.Enqueue(
                        [PSCustomObject]@{
                            DistinguishedName = [string]$parentDn
                            InheritedFrom = [string]$group.Name
                            Level = ([int]$item.Level + 1)
                        }
                    )
                }
            }
        }
        catch {
            $placeholder = [PSCustomObject]@{
                Name = $null
                SamAccountName = $null
                DistinguishedName = $groupDn
                GroupCategory = $null
                GroupScope = $null
                Description = $null
            }

            $results += New-GroupRecord `
                -Group $placeholder `
                -MembershipType "Nested" `
                -InheritedFrom ([string]$item.InheritedFrom) `
                -NestingLevel ([int]$item.Level) `
                -ResolutionError $_.Exception.Message
        }
    }

    return @(
        $results |
        Sort-Object NestingLevel, Name, DistinguishedName
    )
}


function Get-PrimaryGroup {
    [CmdletBinding()]
    param (
        [Parameter(Mandatory = $true)]
        [object]$User,

        [Parameter(Mandatory = $true)]
        [ValidateNotNullOrEmpty()]
        [string]$Server
    )

    try {
        if ($null -eq $User.ObjectSID -or $null -eq $User.PrimaryGroupID) {
            return $null
        }

        $sidText = [string]$User.ObjectSID.Value
        $lastDash = $sidText.LastIndexOf('-')

        if ($lastDash -lt 1) {
            return $null
        }

        $domainSid = $sidText.Substring(0, $lastDash)
        $primaryGroupSid = "$domainSid-$($User.PrimaryGroupID)"

        return Get-ADGroup `
            -Identity $primaryGroupSid `
            -Server $Server `
            -Properties Description, MemberOf `
            -ErrorAction Stop
    }
    catch {
        return $null
    }
}


function Get-ManagerDetails {
    [CmdletBinding()]
    param (
        [Parameter(Mandatory = $false)]
        [AllowNull()]
        [object]$ManagerDistinguishedName,

        [Parameter(Mandatory = $true)]
        [ValidateNotNullOrEmpty()]
        [string]$Server
    )

    if (
        $null -eq $ManagerDistinguishedName `
        -or [string]::IsNullOrWhiteSpace(
            [string]$ManagerDistinguishedName
        )
    ) {
        return [PSCustomObject][ordered]@{
            Assigned = $false
            Name = $null
            DisplayName = $null
            SamAccountName = $null
            UserPrincipalName = $null
            Email = $null
            JobTitle = $null
            Department = $null
            DistinguishedName = $null
            Enabled = $null
            ResolutionError = $null
        }
    }

    try {
        $manager = Get-ADUser `
            -Identity $ManagerDistinguishedName `
            -Server $Server `
            -Properties DisplayName, SamAccountName, UserPrincipalName, Mail, Title, Department, Enabled `
            -ErrorAction Stop

        $managerEmail = $manager.Mail

        if ([string]::IsNullOrWhiteSpace([string]$managerEmail)) {
            $managerEmail = $manager.UserPrincipalName
        }

        return [PSCustomObject][ordered]@{
            Assigned = $true
            Name = $manager.Name
            DisplayName = $manager.DisplayName
            SamAccountName = $manager.SamAccountName
            UserPrincipalName = $manager.UserPrincipalName
            Email = $managerEmail
            JobTitle = $manager.Title
            Department = $manager.Department
            DistinguishedName = $manager.DistinguishedName
            Enabled = [bool]$manager.Enabled
            ResolutionError = $null
        }
    }
    catch {
        return [PSCustomObject][ordered]@{
            Assigned = $true
            Name = $null
            DisplayName = $null
            SamAccountName = $null
            UserPrincipalName = $null
            Email = $null
            JobTitle = $null
            Department = $null
            DistinguishedName = [string]$ManagerDistinguishedName
            Enabled = $null
            ResolutionError = $_.Exception.Message
        }
    }
}


try {
    Import-Module ActiveDirectory -ErrorAction Stop

    $executionIdentity = (
        [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    )
    $executionComputer = $env:COMPUTERNAME

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
        "msDS-UserPasswordExpiryTimeComputed"
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
        "PrimaryGroupID"
        "ObjectSID"
    )

    $user = $null

    if ($UserIdentifier -like "*@*") {
        $safeIdentifier = ConvertTo-LdapFilterValue `
            -Value $UserIdentifier

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

    $lockoutUser = Get-ADUser `
        -Identity $user.DistinguishedName `
        -Server $pdcEmulator `
        -Properties LockedOut, lockoutTime, badPwdCount, badPasswordTime, LastBadPasswordAttempt `
        -ErrorAction Stop

    $isLockedOut = [bool]$lockoutUser.LockedOut
    $lockoutTime = ConvertFrom-FileTimeValue `
        -Value $lockoutUser.lockoutTime
    $lastBadPasswordTime = ConvertFrom-FileTimeValue `
        -Value $lockoutUser.badPasswordTime

    $searchBase = (
        $user.DistinguishedName `
        -replace '^CN=(?:\\.|[^,])+,', ''
    )

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
    $effectiveLockedOut = $isLockedOut -or $searchAdAccountLockedOut

    $managerDetails = Get-ManagerDetails `
        -ManagerDistinguishedName $user.Manager `
        -Server $pdcEmulator

    $resolvedManagerName = $null

    if (
        -not [string]::IsNullOrWhiteSpace(
            [string]$managerDetails.DisplayName
        )
    ) {
        $resolvedManagerName = $managerDetails.DisplayName
    }
    elseif (
        -not [string]::IsNullOrWhiteSpace(
            [string]$managerDetails.Name
        )
    ) {
        $resolvedManagerName = $managerDetails.Name
    }

    $directGroupObjects = @(
        Get-DirectGroups `
            -MemberOf @($user.MemberOf) `
            -Server $pdcEmulator
    )

    $directGroups = @()

    foreach ($group in @($directGroupObjects)) {
        if ($null -eq $group) {
            continue
        }

        $resolutionError = Get-ObjectPropertyValue `
            -InputObject $group `
            -PropertyName "ResolutionError"

        $directGroups += New-GroupRecord `
            -Group $group `
            -MembershipType "Direct" `
            -InheritedFrom $null `
            -NestingLevel 0 `
            -ResolutionError $resolutionError
    }

    $nestedGroups = @()

    if (@($directGroupObjects).Count -gt 0) {
        $nestedGroups = @(
            Get-NestedGroups `
                -DirectGroups @($directGroupObjects) `
                -Server $pdcEmulator
        )
    }

    $primaryGroupObject = Get-PrimaryGroup `
        -User $user `
        -Server $pdcEmulator

    $primaryGroups = @()

    if ($null -ne $primaryGroupObject) {
        $primaryGroups += New-GroupRecord `
            -Group $primaryGroupObject `
            -MembershipType "Primary" `
            -InheritedFrom $null `
            -NestingLevel 0
    }

    $effectiveGroupsByKey = @{}

    foreach (
        $group in @($primaryGroups) + @($directGroups) + @($nestedGroups)
    ) {
        if ($null -eq $group) {
            continue
        }

        $key = [string]$group.DistinguishedName

        if ([string]::IsNullOrWhiteSpace($key)) {
            $key = (
                "$($group.MembershipType)::$($group.Name)" +
                "::$($group.InheritedFrom)"
            )
        }

        $normalizedKey = $key.ToLowerInvariant()

        if (-not $effectiveGroupsByKey.ContainsKey($normalizedKey)) {
            $effectiveGroupsByKey[$normalizedKey] = $group
        }
    }

    $effectiveGroups = @(
        $effectiveGroupsByKey.Values |
        Sort-Object Name, DistinguishedName
    )

    $directGroupNames = @(
        $directGroups |
        Where-Object {
            -not [string]::IsNullOrWhiteSpace([string]$_.Name)
        } |
        ForEach-Object {
            $_.Name
        } |
        Sort-Object -Unique
    )

    $nestedGroupNames = @(
        $nestedGroups |
        Where-Object {
            -not [string]::IsNullOrWhiteSpace([string]$_.Name)
        } |
        ForEach-Object {
            $_.Name
        } |
        Sort-Object -Unique
    )

    $effectiveGroupNames = @(
        $effectiveGroups |
        Where-Object {
            -not [string]::IsNullOrWhiteSpace([string]$_.Name)
        } |
        ForEach-Object {
            $_.Name
        } |
        Sort-Object -Unique
    )

    $primaryGroupName = $null

    if ($primaryGroups.Count -gt 0) {
        $primaryGroupName = $primaryGroups[0].Name
    }

    $passwordExpiryDate = $null

    if (-not [bool]$user.PasswordNeverExpires) {
        # Never-expiring values (0 / Int64.MaxValue) convert to $null.
        $passwordExpiryDate = ConvertFrom-FileTimeValue `
            -Value $user.'msDS-UserPasswordExpiryTimeComputed'
    }

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
        LockoutStatusSource = (
            "PDC emulator: Get-ADUser plus scoped Search-ADAccount"
        )
        LockoutTime = ConvertTo-IsoDateTime -Value $lockoutTime
        BadPasswordCount = $lockoutUser.badPwdCount
        LastBadPasswordTime = ConvertTo-IsoDateTime `
            -Value $lastBadPasswordTime
        LastBadPasswordAttempt = ConvertTo-IsoDateTime `
            -Value $lockoutUser.LastBadPasswordAttempt
        PasswordExpired = [bool]$user.PasswordExpired
        PasswordLastSet = ConvertTo-IsoDateTime `
            -Value $user.PasswordLastSet
        PasswordNeverExpires = [bool]$user.PasswordNeverExpires
        PasswordExpiryDate = ConvertTo-IsoDateTime `
            -Value $passwordExpiryDate
        CannotChangePassword = [bool]$user.CannotChangePassword
        PasswordNotRequired = [bool]$user.PasswordNotRequired
        AccountExpirationDate = ConvertTo-IsoDateTime `
            -Value $user.AccountExpirationDate
        LastLogonDate = ConvertTo-IsoDateTime `
            -Value $user.LastLogonDate
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
        ManagerAssigned = [bool]$managerDetails.Assigned
        ManagerName = $resolvedManagerName
        ManagerDisplayName = $managerDetails.DisplayName
        ManagerSamAccountName = $managerDetails.SamAccountName
        ManagerUserPrincipalName = $managerDetails.UserPrincipalName
        ManagerEmail = $managerDetails.Email
        ManagerJobTitle = $managerDetails.JobTitle
        ManagerDepartment = $managerDetails.Department
        ManagerDistinguishedName = $managerDetails.DistinguishedName
        ManagerEnabled = $managerDetails.Enabled
        ManagerResolutionError = $managerDetails.ResolutionError
        PrimaryGroupName = $primaryGroupName
        PrimaryGroups = @($primaryGroups)
        DirectGroupMembershipCount = @($directGroups).Count
        NestedGroupMembershipCount = @($nestedGroups).Count
        EffectiveGroupMembershipCount = @($effectiveGroups).Count
        DirectGroupNames = @($directGroupNames)
        NestedGroupNames = @($nestedGroupNames)
        EffectiveGroupNames = @($effectiveGroupNames)
        DirectGroups = @($directGroups)
        NestedGroups = @($nestedGroups)
        EffectiveGroups = @($effectiveGroups)
        WhenCreated = ConvertTo-IsoDateTime -Value $user.whenCreated
        WhenChanged = ConvertTo-IsoDateTime -Value $user.whenChanged
        Domain = $domain.DNSRoot
        DomainController = $pdcEmulator
        ExecutionIdentity = $executionIdentity
        ExecutionComputer = $executionComputer
    }

    $result |
        ConvertTo-Json `
            -Compress `
            -Depth 12

    exit 0
}
catch {
    $failureResult = [ordered]@{
        Success = $false
        UserIdentifier = $UserIdentifier
        ExecutionIdentity = (
            [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        )
        ExecutionComputer = $env:COMPUTERNAME
        ErrorType = $_.Exception.GetType().FullName
        Error = $_.Exception.Message
        ScriptLineNumber = $_.InvocationInfo.ScriptLineNumber
        PositionMessage = $_.InvocationInfo.PositionMessage
    }

    Write-Error (
        $failureResult |
        ConvertTo-Json `
            -Compress `
            -Depth 12
    )

    exit 1
}
