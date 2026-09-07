param (
    [string]$GroupName,
    [string]$Description = ""
)

try {
    # 1. PRE-CHECK: Does the group already exist?
    $ExistingGroup = Get-ADGroup -Filter "SamAccountName -eq '$GroupName'"
    if ($ExistingGroup) {
        Write-Error "CONFLICT: A security group named '$GroupName' already exists."
        exit 1  # Forces Python to recognize the failure
    }

    # 2. Proceed with creation
    New-ADGroup -Name $GroupName -SamAccountName $GroupName -GroupCategory Security -GroupScope Global -Description $Description -ErrorAction Stop
    
    Write-Output "Successfully created Security Group: '$GroupName'."
} catch {
    Write-Error "FAILED: $_"
    exit 1
}