param (
    [string]$FirstName,
    [string]$LastName,
    [string]$UserName,
    [string]$EmailAddress,
    [string]$Department,
    [string]$Password,
    [string]$TargetOU = ""
)

try {
    # 1. PRE-CHECK: Does the user already exist?
    $ExistingUser = Get-ADUser -Filter "SamAccountName -eq '$UserName'"
    if ($ExistingUser) {
        Write-Error "CONFLICT: A user with the login ID '$UserName' already exists in Active Directory."
        exit 1  # Forces Python to recognize the failure
    }

    # 2. Proceed with creation
    $SecurePassword = ConvertTo-SecureString $Password -AsPlainText -Force
    $Domain = (Get-ADDomain).ForestRoot

    $UserParams = @{
        GivenName             = $FirstName
        Surname               = $LastName
        Name                  = "$FirstName $LastName"
        SamAccountName        = $UserName
        UserPrincipalName     = "$UserName@$Domain"
        EmailAddress          = $EmailAddress
        Department            = $Department
        AccountPassword       = $SecurePassword
        Enabled               = $true 
        ChangePasswordAtLogon = $true  
    }

    if (![string]::IsNullOrWhiteSpace($TargetOU) -and $TargetOU -ne "OU=DevTestUsers,DC=yourdomain,DC=local") {
        $UserParams.Add("Path", $TargetOU)
    }

    New-ADUser @UserParams -ErrorAction Stop
    Enable-ADAccount -Identity $UserName -ErrorAction Stop

    Write-Output "Successfully provisioned and ENABLED account for $UserName."

} catch {
    # Catch any other unexpected AD errors and force a hard exit
    Write-Error "FAILED: $_"
    exit 1
}