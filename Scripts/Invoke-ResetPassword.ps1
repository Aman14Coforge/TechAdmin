param (
    [string]$UserName,
    [string]$NewPassword
)

try {
    # 1. Verify the exact username exists
    $User = Get-ADUser -Identity $UserName -ErrorAction Stop
    
    # 2. Convert plain-text to a secure string
    $SecurePassword = ConvertTo-SecureString $NewPassword -AsPlainText -Force
    
    # 3. Reset the password
    Set-ADAccountPassword -Identity $User.SAMAccountName -NewPassword $SecurePassword -Reset:$true -ErrorAction Stop
    
    # 4. Force password change at next logon
    Set-ADUser -Identity $User.SAMAccountName -ChangePasswordAtLogon $true -ErrorAction Stop
    
    Write-Output "Successfully reset password for '$($User.SAMAccountName)'. They will be prompted to change it at next login."
} catch {
    Write-Error "FAILED: Could not process reset. Verify the username '$UserName' is correct. Details: $_"
}