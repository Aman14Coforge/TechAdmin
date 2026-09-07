param (
    [string]$FirstName,
    [string]$LastName,
    [string]$UserName
)

try {
    # Find the exact user
    $User = Get-ADUser -Identity $UserName -Properties GivenName, Surname -ErrorAction Stop
    
    # Validation Check: Ensure the names provided in the UI match AD's records
    if ($User.GivenName -ne $FirstName -or $User.Surname -ne $LastName) {
        Write-Error "FAILED IDENTITY CHECK: The sAMAccountName '$UserName' belongs to '$($User.GivenName) $($User.Surname)'. This does not match your input of '$FirstName $LastName'. Deletion aborted."
        exit
    }

    # Execute deletion safely
    Remove-ADUser -Identity $User.SAMAccountName -Confirm:$false -ErrorAction Stop
    Write-Output "Identity verified. Successfully deleted account: $($User.SAMAccountName)"
}
catch {
    Write-Error "FAILED: Could not process deletion. Either the user '$UserName' does not exist, or permissions are insufficient."
}