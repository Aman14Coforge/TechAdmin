[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$ComputerIdentifier,

    [Parameter(Mandatory = $false)]
    [string]$Server,

    [Parameter(Mandatory = $false)]
    [string]$SearchBase,

    [Parameter(Mandatory = $false)]
    [ValidateSet("true", "false", "1", "0", "yes", "no", "on", "off")]
    [string]$IncludeLiveData = "true",

    [Parameter(Mandatory = $false)]
    [ValidateRange(2, 120)]
    [int]$LiveDataTimeoutSeconds = 15
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$collectLiveData = $IncludeLiveData.Trim().ToLowerInvariant() -in @(
    "true", "1", "yes", "on"
)

function Convert-ToDisplayDate {
    param([AllowNull()][object]$Value)

    if ($null -eq $Value) {
        return $null
    }

    if ($Value -is [datetime]) {
        return $Value.ToString("yyyy-MM-dd HH:mm:ss")
    }

    return [string]$Value
}

function Convert-FileTimeToDate {
    param([AllowNull()][object]$Value)

    if ($null -eq $Value) {
        return $null
    }

    try {
        $number = [int64]$Value
        if ($number -le 0) {
            return $null
        }
        return [datetime]::FromFileTimeUtc($number).ToLocalTime()
    }
    catch {
        return $null
    }
}

function Convert-GroupRecord {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Group
    )

    return [ordered]@{
        Name              = $Group.Name
        SamAccountName    = $Group.SamAccountName
        DistinguishedName = $Group.DistinguishedName
        GroupCategory     = if ($null -ne $Group.GroupCategory) {
            [string]$Group.GroupCategory
        }
        else {
            $null
        }
        GroupScope        = if ($null -ne $Group.GroupScope) {
            [string]$Group.GroupScope
        }
        else {
            $null
        }
        Description       = $Group.Description
        MembershipType    = "DirectOrPrimary"
    }
}

function Resolve-ADComputerObject {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Identifier,

        [Parameter(Mandatory = $true)]
        [string[]]$Properties,

        [AllowNull()]
        [string]$DirectoryServer,

        [AllowNull()]
        [string]$DirectorySearchBase
    )

    $candidate = $Identifier.Trim()
    $common = @{
        Properties  = $Properties
        ErrorAction = "Stop"
    }

    if ($DirectoryServer) {
        $common["Server"] = $DirectoryServer
    }

    try {
        return Get-ADComputer -Identity $candidate @common
    }
    catch [Microsoft.ActiveDirectory.Management.ADIdentityNotFoundException] {
        # Continue with exact Name, SAM-account, and DNS-hostname matching.
    }

    $shortName = $candidate
    if ($shortName.EndsWith('$')) {
        $shortName = $shortName.Substring(0, $shortName.Length - 1)
    }

    if ($shortName.Contains('.')) {
        $shortName = $shortName.Split('.')[0]
    }

    $escapedShort = $shortName.Replace("'", "''")
    $escapedCandidate = $candidate.Replace("'", "''")

    $search = @{
        Filter = (
            "Name -eq '$escapedShort' -or " +
            "SamAccountName -eq '$escapedShort`$' -or " +
            "DNSHostName -eq '$escapedCandidate'"
        )
        Properties    = $Properties
        ResultSetSize = 2
        ErrorAction   = "Stop"
    }

    if ($DirectoryServer) {
        $search["Server"] = $DirectoryServer
    }

    if ($DirectorySearchBase) {
        $search["SearchBase"] = $DirectorySearchBase
    }

    $matches = @(Get-ADComputer @search)

    if ($matches.Count -eq 0) {
        throw "Computer '$Identifier' was not found in Active Directory."
    }

    if ($matches.Count -gt 1) {
        throw "Computer identifier '$Identifier' matched multiple Active Directory objects."
    }

    return $matches[0]
}

function Resolve-ManagedByObject {
    param(
        [AllowNull()]
        [string]$DistinguishedName,

        [AllowNull()]
        [string]$DirectoryServer
    )

    if (-not $DistinguishedName) {
        return [ordered]@{
            Assigned         = $false
            DistinguishedName = $null
            ObjectClass      = $null
            Name             = $null
            DisplayName      = $null
            SamAccountName   = $null
            UserPrincipalName = $null
            Email            = $null
            Department       = $null
            JobTitle         = $null
            Enabled          = $null
            ResolutionError  = $null
        }
    }

    try {
        $arguments = @{
            Identity    = $DistinguishedName
            Properties  = @(
                "displayName", "mail", "userPrincipalName", "objectClass",
                "sAMAccountName", "department", "title"
            )
            ErrorAction = "Stop"
        }

        if ($DirectoryServer) {
            $arguments["Server"] = $DirectoryServer
        }

        $directoryObject = Get-ADObject @arguments
        $enabled = $null

        if ($directoryObject.ObjectClass -eq "user") {
            try {
                $userArguments = @{
                    Identity    = $DistinguishedName
                    Properties  = @(
                        "displayName", "mail", "userPrincipalName",
                        "sAMAccountName", "department", "title", "Enabled"
                    )
                    ErrorAction = "Stop"
                }

                if ($DirectoryServer) {
                    $userArguments["Server"] = $DirectoryServer
                }

                $user = Get-ADUser @userArguments
                $directoryObject = $user
                $enabled = [bool]$user.Enabled
            }
            catch {
                # The base AD object is still useful when Get-ADUser fails.
            }
        }

        return [ordered]@{
            Assigned          = $true
            DistinguishedName = $DistinguishedName
            ObjectClass       = [string]$directoryObject.ObjectClass
            Name              = $directoryObject.Name
            DisplayName       = $directoryObject.DisplayName
            SamAccountName    = $directoryObject.SamAccountName
            UserPrincipalName = $directoryObject.UserPrincipalName
            Email             = $directoryObject.Mail
            Department        = $directoryObject.Department
            JobTitle          = $directoryObject.Title
            Enabled           = $enabled
            ResolutionError   = $null
        }
    }
    catch {
        return [ordered]@{
            Assigned          = $true
            DistinguishedName = $DistinguishedName
            ObjectClass       = $null
            Name              = $null
            DisplayName       = $null
            SamAccountName    = $null
            UserPrincipalName = $null
            Email             = $null
            Department        = $null
            JobTitle          = $null
            Enabled           = $null
            ResolutionError   = $_.Exception.Message
        }
    }
}

function Resolve-DnsInformation {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Names
    )

    $addresses = New-Object System.Collections.Generic.List[object]
    $aliases = New-Object System.Collections.Generic.List[string]
    $errors = New-Object System.Collections.Generic.List[string]

    foreach ($name in ($Names | Where-Object { $_ } | Select-Object -Unique)) {
        try {
            if (Get-Command Resolve-DnsName -ErrorAction SilentlyContinue) {
                $records = @(
                    Resolve-DnsName -Name $name -Type A_AAAA -DnsOnly -ErrorAction Stop
                )

                foreach ($record in $records) {
                    if ($record.IPAddress) {
                        $addresses.Add([ordered]@{
                            Address = [string]$record.IPAddress
                            Family  = if ([string]$record.IPAddress -match ':') {
                                "IPv6"
                            }
                            else {
                                "IPv4"
                            }
                            QueryName = $name
                            Source    = "DNS"
                        })
                    }

                    if ($record.NameHost) {
                        $aliases.Add([string]$record.NameHost)
                    }
                }
            }
            else {
                $entries = [System.Net.Dns]::GetHostAddresses($name)
                foreach ($entry in $entries) {
                    $addresses.Add([ordered]@{
                        Address   = $entry.IPAddressToString
                        Family    = [string]$entry.AddressFamily
                        QueryName = $name
                        Source    = "DNS"
                    })
                }
            }
        }
        catch {
            $errors.Add("$name`: $($_.Exception.Message)")
        }
    }

    $uniqueAddresses = @(
        $addresses |
            Group-Object Address |
            ForEach-Object { $_.Group[0] }
    )

    return [ordered]@{
        QueryNames = @($Names | Where-Object { $_ } | Select-Object -Unique)
        Addresses  = $uniqueAddresses
        IPv4Addresses = @(
            $uniqueAddresses |
                Where-Object { $_.Family -eq "IPv4" } |
                ForEach-Object { $_.Address }
        )
        IPv6Addresses = @(
            $uniqueAddresses |
                Where-Object { $_.Family -eq "IPv6" } |
                ForEach-Object { $_.Address }
        )
        Aliases = @($aliases | Select-Object -Unique)
        Errors  = @($errors)
        Note    = (
            "DNS addresses are name-resolution results. They may be stale, " +
            "may represent another interface, VPN, or registration, and are " +
            "not guaranteed to match the endpoint's current ipconfig output."
        )
    }
}

function Get-LiveComputerData {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Target,

        [Parameter(Mandatory = $true)]
        [int]$TimeoutSeconds
    )

    $result = [ordered]@{
        Requested              = $true
        Attempted              = $true
        ReachableByIcmp        = $null
        CimConnected           = $false
        ComputerSystem         = $null
        OperatingSystem        = $null
        Bios                   = $null
        Hardware               = $null
        NetworkAdapters        = @()
        ActiveIPv4Addresses    = @()
        ActiveIPv6Addresses    = @()
        DefaultGateways        = @()
        DnsServers             = @()
        LoggedOnUser           = $null
        LoggedOnUserDirectory  = $null
        CollectionErrors       = @()
        Note                   = (
            "Live data is collected remotely through CIM/WMI. Values reflect " +
            "the endpoint only when remote management, firewall, permissions, " +
            "and endpoint availability permit collection."
        )
    }

    try {
        $result.ReachableByIcmp = Test-Connection -ComputerName $Target -Count 1 -Quiet -ErrorAction SilentlyContinue
    }
    catch {
        $result.ReachableByIcmp = $null
    }

    $session = $null

    try {
        $sessionOption = New-CimSessionOption -Protocol Dcom
        $session = New-CimSession -ComputerName $Target -SessionOption $sessionOption -OperationTimeoutSec $TimeoutSeconds -ErrorAction Stop
        $result.CimConnected = $true

        $computerSystem = Get-CimInstance -CimSession $session -ClassName Win32_ComputerSystem -ErrorAction Stop
        $operatingSystem = Get-CimInstance -CimSession $session -ClassName Win32_OperatingSystem -ErrorAction Stop
        $bios = Get-CimInstance -CimSession $session -ClassName Win32_BIOS -ErrorAction Stop
        $processors = @(Get-CimInstance -CimSession $session -ClassName Win32_Processor -ErrorAction Stop)
        $networkConfigurations = @(
            Get-CimInstance -CimSession $session -ClassName Win32_NetworkAdapterConfiguration -Filter "IPEnabled=True" -ErrorAction Stop
        )

        $result.ComputerSystem = [ordered]@{
            Name             = $computerSystem.Name
            Domain           = $computerSystem.Domain
            DomainRole       = $computerSystem.DomainRole
            Manufacturer     = $computerSystem.Manufacturer
            Model            = $computerSystem.Model
            SystemType       = $computerSystem.SystemType
            TotalMemoryBytes = [int64]$computerSystem.TotalPhysicalMemory
            TotalMemoryGB    = [math]::Round(([double]$computerSystem.TotalPhysicalMemory / 1GB), 2)
            LoggedOnUser     = $computerSystem.UserName
        }

        $result.LoggedOnUser = $computerSystem.UserName

        $result.OperatingSystem = [ordered]@{
            Caption              = $operatingSystem.Caption
            Version              = $operatingSystem.Version
            BuildNumber          = $operatingSystem.BuildNumber
            Architecture         = $operatingSystem.OSArchitecture
            InstallDate          = Convert-ToDisplayDate $operatingSystem.InstallDate
            LastBootTime         = Convert-ToDisplayDate $operatingSystem.LastBootUpTime
            LocalDateTime        = Convert-ToDisplayDate $operatingSystem.LocalDateTime
            SerialNumber         = $operatingSystem.SerialNumber
            WindowsDirectory     = $operatingSystem.WindowsDirectory
            SystemDrive          = $operatingSystem.SystemDrive
            FreePhysicalMemoryKB = $operatingSystem.FreePhysicalMemory
        }

        $result.Bios = [ordered]@{
            Manufacturer      = $bios.Manufacturer
            Name              = $bios.Name
            Version           = $bios.SMBIOSBIOSVersion
            SerialNumber      = $bios.SerialNumber
            ReleaseDate       = Convert-ToDisplayDate $bios.ReleaseDate
        }

        $result.Hardware = [ordered]@{
            ProcessorCount = $processors.Count
            Processors     = @(
                $processors | ForEach-Object {
                    [ordered]@{
                        Name                      = $_.Name
                        Manufacturer              = $_.Manufacturer
                        NumberOfCores             = $_.NumberOfCores
                        NumberOfLogicalProcessors = $_.NumberOfLogicalProcessors
                        MaxClockSpeedMHz          = $_.MaxClockSpeed
                    }
                }
            )
        }

        $adapterRows = New-Object System.Collections.Generic.List[object]
        $ipv4 = New-Object System.Collections.Generic.List[string]
        $ipv6 = New-Object System.Collections.Generic.List[string]
        $gateways = New-Object System.Collections.Generic.List[string]
        $dnsServers = New-Object System.Collections.Generic.List[string]

        foreach ($adapter in $networkConfigurations) {
            $adapterIPv4 = @($adapter.IPAddress | Where-Object { $_ -and $_ -notmatch ':' })
            $adapterIPv6 = @(
                $adapter.IPAddress |
                    Where-Object {
                        $_ -and
                        $_ -match ':' -and
                        $_ -notmatch '^fe80:'
                    }
            )

            foreach ($address in $adapterIPv4) {
                $ipv4.Add([string]$address)
            }

            foreach ($address in $adapterIPv6) {
                $ipv6.Add([string]$address)
            }

            foreach ($gateway in @($adapter.DefaultIPGateway | Where-Object { $_ })) {
                $gateways.Add([string]$gateway)
            }

            foreach ($dnsServer in @($adapter.DNSServerSearchOrder | Where-Object { $_ })) {
                $dnsServers.Add([string]$dnsServer)
            }

            $adapterRows.Add([ordered]@{
                Description       = $adapter.Description
                MACAddress        = $adapter.MACAddress
                DHCPEnabled       = [bool]$adapter.DHCPEnabled
                DHCPServer        = $adapter.DHCPServer
                IPv4Addresses     = $adapterIPv4
                IPv6Addresses     = $adapterIPv6
                IPSubnets         = @($adapter.IPSubnet | Where-Object { $_ })
                DefaultGateways   = @($adapter.DefaultIPGateway | Where-Object { $_ })
                DnsServers        = @($adapter.DNSServerSearchOrder | Where-Object { $_ })
                DnsDomain         = $adapter.DNSDomain
                DnsHostName       = $adapter.DNSHostName
                WinsPrimaryServer = $adapter.WINSPrimaryServer
            })
        }

        $result.NetworkAdapters = @($adapterRows)
        $result.ActiveIPv4Addresses = @($ipv4 | Select-Object -Unique)
        $result.ActiveIPv6Addresses = @($ipv6 | Select-Object -Unique)
        $result.DefaultGateways = @($gateways | Select-Object -Unique)
        $result.DnsServers = @($dnsServers | Select-Object -Unique)
    }
    catch {
        $result.CollectionErrors = @($result.CollectionErrors) + @(
            "$($_.Exception.GetType().Name): $($_.Exception.Message)"
        )
    }
    finally {
        if ($null -ne $session) {
            Remove-CimSession -CimSession $session -ErrorAction SilentlyContinue
        }
    }

    return $result
}

try {
    Import-Module ActiveDirectory -ErrorAction Stop

    $properties = @(
        "Name",
        "SamAccountName",
        "DNSHostName",
        "Enabled",
        "Description",
        "DisplayName",
        "OperatingSystem",
        "OperatingSystemVersion",
        "OperatingSystemServicePack",
        "IPv4Address",
        "IPv6Address",
        "Location",
        "ManagedBy",
        "MemberOf",
        "LastLogonDate",
        "lastLogonTimestamp",
        "lastLogon",
        "logonCount",
        "PasswordLastSet",
        "pwdLastSet",
        "whenCreated",
        "whenChanged",
        "DistinguishedName",
        "CanonicalName",
        "ObjectGUID",
        "SID",
        "PrimaryGroupID",
        "ServicePrincipalName",
        "msDS-SupportedEncryptionTypes",
        "TrustedForDelegation",
        "TrustedToAuthForDelegation",
        "AccountExpirationDate",
        "userAccountControl",
        "msDS-HostServiceAccount",
        "msDS-AdditionalDnsHostName"
    )

    $computer = Resolve-ADComputerObject `
        -Identifier $ComputerIdentifier `
        -Properties $properties `
        -DirectoryServer $Server `
        -DirectorySearchBase $SearchBase

    $managedBy = Resolve-ManagedByObject `
        -DistinguishedName $computer.ManagedBy `
        -DirectoryServer $Server

    $groups = @()
    $groupResolutionError = $null

    try {
        $membershipArguments = @{
            Identity    = $computer.DistinguishedName
            ErrorAction = "Stop"
        }

        if ($Server) {
            $membershipArguments["Server"] = $Server
        }

        $groups = @(
            Get-ADPrincipalGroupMembership @membershipArguments |
                Sort-Object Name |
                ForEach-Object {
                    Convert-GroupRecord -Group $_
                }
        )
    }
    catch {
        $groupResolutionError = $_.Exception.Message
    }

    $domain = $null
    $domainController = $null
    $domainResolutionError = $null

    try {
        $domainArguments = @{ ErrorAction = "Stop" }
        if ($Server) {
            $domainArguments["Server"] = $Server
        }

        $domainObject = Get-ADDomain @domainArguments
        $domain = $domainObject.DNSRoot
        $domainController = if ($Server) {
            $Server
        }
        else {
            $domainObject.PDCEmulator
        }
    }
    catch {
        $domainResolutionError = $_.Exception.Message
    }

    $shortName = [string]$computer.Name
    $dnsHostName = [string]$computer.DNSHostName

    if (-not $dnsHostName -and $shortName -and $domain) {
        $dnsHostName = "$shortName.$domain"
    }

    $dnsInformation = Resolve-DnsInformation -Names @(
        $dnsHostName,
        $shortName
    )

    $liveData = [ordered]@{
        Requested             = $collectLiveData
        Attempted             = $false
        ReachableByIcmp       = $null
        CimConnected          = $false
        ComputerSystem        = $null
        OperatingSystem       = $null
        Bios                  = $null
        Hardware              = $null
        NetworkAdapters       = @()
        ActiveIPv4Addresses   = @()
        ActiveIPv6Addresses   = @()
        DefaultGateways       = @()
        DnsServers            = @()
        LoggedOnUser          = $null
        LoggedOnUserDirectory = $null
        CollectionErrors      = @()
        Note                  = (
            "Live collection was not requested. Set -IncludeLiveData true to " +
            "attempt remote CIM/WMI collection from the endpoint."
        )
    }

    if ($collectLiveData) {
        $liveTarget = if ($dnsHostName) {
            $dnsHostName
        }
        else {
            $shortName
        }

        $liveData = Get-LiveComputerData `
            -Target $liveTarget `
            -TimeoutSeconds $LiveDataTimeoutSeconds

        if ($liveData.LoggedOnUser) {
            $loggedOnIdentity = [string]$liveData.LoggedOnUser
            $loggedOnSam = if ($loggedOnIdentity.Contains('\')) {
                $loggedOnIdentity.Split('\')[-1]
            }
            elseif ($loggedOnIdentity.Contains('@')) {
                $loggedOnIdentity.Split('@')[0]
            }
            else {
                $loggedOnIdentity
            }

            try {
                $loggedOnArguments = @{
                    Identity    = $loggedOnSam
                    Properties  = @(
                        "displayName", "mail", "userPrincipalName",
                        "department", "title", "Enabled"
                    )
                    ErrorAction = "Stop"
                }

                if ($Server) {
                    $loggedOnArguments["Server"] = $Server
                }

                $loggedOnUser = Get-ADUser @loggedOnArguments
                $liveData.LoggedOnUserDirectory = [ordered]@{
                    DisplayName       = $loggedOnUser.DisplayName
                    SamAccountName    = $loggedOnUser.SamAccountName
                    UserPrincipalName = $loggedOnUser.UserPrincipalName
                    Email             = $loggedOnUser.Mail
                    Department        = $loggedOnUser.Department
                    JobTitle          = $loggedOnUser.Title
                    Enabled           = [bool]$loggedOnUser.Enabled
                }
            }
            catch {
                $liveData.CollectionErrors = @($liveData.CollectionErrors) + @(
                    "Logged-on user directory resolution: $($_.Exception.Message)"
                )
            }
        }
    }

    $adLastLogonTimestamp = Convert-FileTimeToDate $computer.lastLogonTimestamp
    $adLastLogon = Convert-FileTimeToDate $computer.lastLogon
    $adPwdLastSet = Convert-FileTimeToDate $computer.pwdLastSet

    $servicePrincipalNames = @(
        $computer.ServicePrincipalName |
            Where-Object { $_ } |
            Sort-Object -Unique
    )

    $additionalDnsNames = @(
        $computer.'msDS-AdditionalDnsHostName' |
            Where-Object { $_ } |
            Sort-Object -Unique
    )

    $hostServiceAccounts = @(
        $computer.'msDS-HostServiceAccount' |
            Where-Object { $_ } |
            Sort-Object -Unique
    )

    $result = [ordered]@{
        Success = $true

        Query = [ordered]@{
            RequestedIdentifier = $ComputerIdentifier
            ResolvedName        = $computer.Name
            DataCollectionTime  = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
            LiveDataRequested   = $collectLiveData
        }

        DirectoryIdentity = [ordered]@{
            Name              = $computer.Name
            DisplayName       = $computer.DisplayName
            SamAccountName    = $computer.SamAccountName
            DNSHostName       = $dnsHostName
            AdditionalDnsNames = $additionalDnsNames
            Enabled           = [bool]$computer.Enabled
            Description       = $computer.Description
            Location          = $computer.Location
            DistinguishedName = $computer.DistinguishedName
            CanonicalName     = $computer.CanonicalName
            ObjectGUID        = if ($computer.ObjectGUID) {
                [string]$computer.ObjectGUID
            }
            else {
                $null
            }
            SID               = if ($computer.SID) {
                [string]$computer.SID
            }
            else {
                $null
            }
            PrimaryGroupID    = $computer.PrimaryGroupID
            Domain            = $domain
            DomainController  = $domainController
        }

        DirectoryOperatingSystem = [ordered]@{
            OperatingSystem            = $computer.OperatingSystem
            OperatingSystemVersion     = $computer.OperatingSystemVersion
            OperatingSystemServicePack = $computer.OperatingSystemServicePack
            Source                     = "Active Directory computer attributes"
            Note                       = (
                "These values are written to the AD computer object and may " +
                "not reflect the endpoint's current installed build until AD " +
                "is updated by the responsible management process."
            )
        }

        DirectoryActivity = [ordered]@{
            LastLogonDate            = Convert-ToDisplayDate $computer.LastLogonDate
            LastLogonTimestamp       = Convert-ToDisplayDate $adLastLogonTimestamp
            LastLogonOnQueriedDC     = Convert-ToDisplayDate $adLastLogon
            LogonCountOnQueriedDC    = $computer.LogonCount
            PasswordLastSet          = Convert-ToDisplayDate $computer.PasswordLastSet
            PasswordLastSetFromRaw   = Convert-ToDisplayDate $adPwdLastSet
            AccountExpirationDate    = Convert-ToDisplayDate $computer.AccountExpirationDate
            WhenCreated              = Convert-ToDisplayDate $computer.WhenCreated
            WhenChanged              = Convert-ToDisplayDate $computer.WhenChanged
            UserAccountControl       = $computer.UserAccountControl
            Note                     = (
                "LastLogonDate/lastLogonTimestamp are replicated or calculated " +
                "directory values and are not a real-time endpoint-presence check."
            )
        }

        OwnershipAndUsage = [ordered]@{
            ManagedBy = $managedBy
            CurrentLoggedOnUser = $liveData.LoggedOnUser
            CurrentLoggedOnUserDirectory = $liveData.LoggedOnUserDirectory
            Note = (
                "ManagedBy is the owner/manager explicitly configured on the " +
                "AD computer object. CurrentLoggedOnUser is returned only when " +
                "live remote CIM collection succeeds. Neither value should be " +
                "treated as the permanent asset owner unless confirmed by the " +
                "authoritative asset-management system."
            )
        }

        DirectoryNetwork = [ordered]@{
            ADIPv4Address = if ($computer.IPv4Address) {
                [string]$computer.IPv4Address
            }
            else {
                $null
            }
            ADIPv6Address = if ($computer.IPv6Address) {
                [string]$computer.IPv6Address
            }
            else {
                $null
            }
            DnsResolution = $dnsInformation
            Note = (
                "AD IPv4Address and IPv6Address are not authoritative live " +
                "ipconfig values. Use LiveEndpoint.NetworkAdapters when live " +
                "collection succeeds."
            )
        }

        LiveEndpoint = $liveData

        SecurityAndDelegation = [ordered]@{
            TrustedForDelegation       = [bool]$computer.TrustedForDelegation
            TrustedToAuthForDelegation = [bool]$computer.TrustedToAuthForDelegation
            SupportedEncryptionTypes   = $computer.'msDS-SupportedEncryptionTypes'
            ServicePrincipalNameCount  = $servicePrincipalNames.Count
            ServicePrincipalNames      = $servicePrincipalNames
            HostServiceAccounts        = $hostServiceAccounts
        }

        GroupMemberships = [ordered]@{
            Count           = $groups.Count
            Groups          = $groups
            ResolutionError = $groupResolutionError
        }

        CollectionContext = [ordered]@{
            DataSource            = "Active Directory PowerShell plus optional remote CIM"
            ExecutionIdentity     = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
            ExecutionComputer     = $env:COMPUTERNAME
            DirectoryServer       = $domainController
            DomainResolutionError = $domainResolutionError
            SecureChannelTested   = $false
            SecureChannelNote     = (
                "Not tested. Test-ComputerSecureChannel evaluates the computer " +
                "where the command runs unless the test is executed on the " +
                "target through an approved remote-management workflow."
            )
        }
    }

    $result | ConvertTo-Json -Depth 15 -Compress
    exit 0
}
catch {
    [ordered]@{
        Success            = $false
        ComputerIdentifier = $ComputerIdentifier
        Error              = $_.Exception.Message
        ErrorType          = $_.Exception.GetType().FullName
        ScriptLine         = $_.InvocationInfo.ScriptLineNumber
        PositionMessage    = $_.InvocationInfo.PositionMessage
        ExecutionIdentity  = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        ExecutionComputer  = $env:COMPUTERNAME
    } | ConvertTo-Json -Depth 8 -Compress

    exit 1
}
