param (
    [string]$TargetHost,
    [string]$VMName,
    [int]$CPUCount,
    [int]$RAMGB,
    [string]$VSwitchName,
    [string]$IPAddress,
    [string]$Subnet,
    [string]$Gateway,
    [string]$DNS,
    [string]$Hostname,
    [string]$Domain,
    [string]$DomainUser,
    [string]$DomainPassword,
    [string]$AdminPassword
)

Invoke-Command -ComputerName $TargetHost -ScriptBlock {
    param($VMName, $CPUCount, $RAMGB, $VSwitchName, $IPAddress, $Subnet, $Gateway, $DNS, $Hostname, $Domain, $DomainUser, $DomainPassword, $AdminPassword)

    # --- PATHS ---
    $TemplateVHDX = "D:\Base\SVR2019-G2.vhdx"
    $VMRootPath = "D:\HyperV\VMs\$VMName"
    $VHDXDirectory = "$VMRootPath\Virtual Hard Disks"
    $NewVHDXPath = "$VHDXDirectory\$VMName.vhdx"

    # 1. PRE-CHECK
    if (Get-VM -Name $VMName -ErrorAction SilentlyContinue) { throw "A VM named '$VMName' already exists on this host." }
    if (-not (Test-Path $TemplateVHDX)) { throw "Cannot find template VHDX at $TemplateVHDX." }

    # 2. SETUP DIRECTORIES
    if (-not (Test-Path $VHDXDirectory)) {
        New-Item -ItemType Directory -Force -Path $VHDXDirectory | Out-Null
    }
    
    Copy-Item -Path $TemplateVHDX -Destination $NewVHDXPath -Force

    # 3. DYNAMIC DOMAIN XML
    $DomainXML = ""
    if (-not [string]::IsNullOrWhiteSpace($Domain)) {
        $DomainXML = @"
        <component name="Microsoft-Windows-UnattendedJoin" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
            <Identification>
                <Credentials>
                    <Domain>$Domain</Domain>
                    <Password>$DomainPassword</Password>
                    <Username>$DomainUser</Username>
                </Credentials>
                <JoinDomain>$Domain</JoinDomain>
            </Identification>
        </component>
"@
    }

    # 4. DYNAMIC NETWORK XML
    $NetworkXML = ""
    if (-not [string]::IsNullOrWhiteSpace($IPAddress)) {
        $cidr = 0
        $Subnet.Split('.') | ForEach-Object { $cidr += [Convert]::ToString([int]$_, 2).Replace('0','').Length }

        $NetworkXML = @"
        <component name="Microsoft-Windows-TCPIP" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
            <Interfaces>
                <Interface wcm:action="add">
                    <Identifier>Ethernet</Identifier>
                    <Ipv4Settings>
                        <DhcpEnabled>false</DhcpEnabled>
                    </Ipv4Settings>
                    <UnicastIpAddresses>
                        <IpAddress wcm:action="add" wcm:keyValue="1">$IPAddress/$cidr</IpAddress>
                    </UnicastIpAddresses>
                    <Routes>
                        <Route wcm:action="add">
                            <Identifier>0</Identifier>
                            <Metric>10</Metric>
                            <NextHopAddress>$Gateway</NextHopAddress>
                            <Prefix>0.0.0.0/0</Prefix>
                        </Route>
                    </Routes>
                </Interface>
            </Interfaces>
        </component>
        <component name="Microsoft-Windows-DNS-Client" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
            <Interfaces>
                <Interface wcm:action="add">
                    <Identifier>Ethernet</Identifier>
                    <DNSServerSearchOrder>
                        <IpAddress wcm:action="add" wcm:keyValue="1">$DNS</IpAddress>
                    </DNSServerSearchOrder>
                </Interface>
            </Interfaces>
        </component>
"@
    }

    # 5. ASSEMBLE FULL UNATTEND.XML
    $UnattendXML = @"
<?xml version="1.0" encoding="utf-8"?>
<unattend xmlns="urn:schemas-microsoft-com:unattend" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">
    
    <settings pass="specialize">
        <component name="Microsoft-Windows-Shell-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
            <ComputerName>$Hostname</ComputerName>
            <TimeZone>India Standard Time</TimeZone>
        </component>
        $DomainXML
        $NetworkXML
    </settings>

    <settings pass="oobeSystem">
        <component name="Microsoft-Windows-International-Core" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
            <InputLocale>en-IN</InputLocale>
            <SystemLocale>en-IN</SystemLocale>
            <UILanguage>en-US</UILanguage>
            <UserLocale>en-IN</UserLocale>
        </component>
        <component name="Microsoft-Windows-Shell-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
            <AutoLogon>
                <Password>
                    <Value>$AdminPassword</Value>
                    <PlainText>true</PlainText>
                </Password>
                <Enabled>true</Enabled>
                <LogonCount>1</LogonCount>
                <Username>Administrator</Username>
            </AutoLogon>
            <FirstLogonCommands>
                <SynchronousCommand wcm:action="add">
                    <Order>1</Order>
                    <Description>Enable RDP</Description>
                    <CommandLine>cmd.exe /c reg add "HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\Terminal Server" /v fDenyTSConnections /t REG_DWORD /d 0 /f</CommandLine>
                </SynchronousCommand>
                <SynchronousCommand wcm:action="add">
                    <Order>2</Order>
                    <Description>Allow RDP Through Firewall</Description>
                    <CommandLine>cmd.exe /c netsh advfirewall firewall set rule group="Remote Desktop" new enable=Yes</CommandLine>
                </SynchronousCommand>
                <SynchronousCommand wcm:action="add">
                    <Order>3</Order>
                    <Description>Disable Domain Firewall Profile</Description>
                    <CommandLine>cmd.exe /c netsh advfirewall set domainprofile state off</CommandLine>
                </SynchronousCommand>
                <SynchronousCommand wcm:action="add">
                    <Order>4</Order>
                    <Description>Disable IPv6</Description>
                    <CommandLine>powershell.exe -ExecutionPolicy Bypass -Command "Disable-NetAdapterBinding -Name '*' -ComponentID ms_tcpip6"</CommandLine>
                </SynchronousCommand>
            </FirstLogonCommands>
            <UserAccounts>
                <AdministratorPassword>
                    <Value>$AdminPassword</Value>
                    <PlainText>true</PlainText>
                </AdministratorPassword>
            </UserAccounts>
            <OOBE>
                <HideEULAPage>true</HideEULAPage>
                <HideLocalAccountScreen>true</HideLocalAccountScreen>
                <HideOEMRegistrationScreen>true</HideOEMRegistrationScreen>
                <HideOnlineAccountScreens>true</HideOnlineAccountScreens>
                <HideWirelessSetupInOOBE>true</HideWirelessSetupInOOBE>
                <NetworkLocation>Work</NetworkLocation>
                <ProtectYourPC>1</ProtectYourPC>
            </OOBE>
        </component>
    </settings>
</unattend>
"@

    # 6. MOUNT AND INJECT
    $Mount = Mount-VHD -Path $NewVHDXPath -PassThru
    Start-Sleep -Seconds 5
    
    $WinDrive = (Get-Disk -Number $Mount.Number | Get-Partition | Get-Volume | Where-Object { Test-Path "$($_.DriveLetter):\Windows" } | Select-Object -ExpandProperty DriveLetter)
    
    $PantherPath = "${WinDrive}:\Windows\Panther"
    if (-not (Test-Path $PantherPath)) { New-Item -ItemType Directory -Path $PantherPath | Out-Null }
    $UnattendXML | Out-File -FilePath "$PantherPath\unattend.xml" -Encoding UTF8 -Force
    
    Dismount-VHD -Path $NewVHDXPath

    # 7. CREATE AND START
    $RAMBytes = $RAMGB * 1GB
    New-VM -Name $VMName -MemoryStartupBytes $RAMBytes -VHDPath $NewVHDXPath -Path $VMRootPath -SwitchName $VSwitchName -Generation 2 | Out-Null
    Set-VMProcessor -VMName $VMName -Count $CPUCount | Out-Null
    Start-VM -Name $VMName
    
    return "VM '$VMName' provisioned and booting on $env:COMPUTERNAME"

} -ArgumentList $VMName, $CPUCount, $RAMGB, $VSwitchName, $IPAddress, $Subnet, $Gateway, $DNS, $Hostname, $Domain, $DomainUser, $DomainPassword, $AdminPassword