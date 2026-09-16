[CmdletBinding()]
param(
    [switch]$Dialog,
    [switch]$FromStdin,
    [string]$KeyFile = (Join-Path $env:LOCALAPPDATA 'SSOS-ESP32\typesafe-api-key.dpapi')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$secure = $null

try {
    if ($FromStdin) {
        $inputKey = [Console]::In.ReadToEnd().Trim()
        if ([string]::IsNullOrWhiteSpace($inputKey)) { throw 'No API key supplied.' }
        $secure = ConvertTo-SecureString $inputKey -AsPlainText -Force
        $inputKey = $null
    } elseif ($Dialog) {
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        $form = New-Object System.Windows.Forms.Form
        $form.Text = 'SSOS - TypeSafe API key'
        $form.ClientSize = New-Object System.Drawing.Size(510, 190)
        $form.StartPosition = 'CenterScreen'
        $form.FormBorderStyle = 'FixedDialog'
        $form.MaximizeBox = $false
        $form.MinimizeBox = $false
        $form.TopMost = $true
        $label = New-Object System.Windows.Forms.Label
        $label.Location = New-Object System.Drawing.Point(16, 16)
        $label.Size = New-Object System.Drawing.Size(475, 55)
        $label.Text = "Paste your typesafe.ai API key below. It will be encrypted for your Windows account and used for the Jev experiment. It is not sent to chat or stored in the repository."
        $inputBox = New-Object System.Windows.Forms.TextBox
        $inputBox.Location = New-Object System.Drawing.Point(16, 80)
        $inputBox.Size = New-Object System.Drawing.Size(475, 25)
        $inputBox.UseSystemPasswordChar = $true
        $save = New-Object System.Windows.Forms.Button
        $save.Text = 'Save key'
        $save.Location = New-Object System.Drawing.Point(280, 135)
        $save.DialogResult = [System.Windows.Forms.DialogResult]::OK
        $cancel = New-Object System.Windows.Forms.Button
        $cancel.Text = 'Cancel'
        $cancel.Location = New-Object System.Drawing.Point(390, 135)
        $cancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
        $form.Controls.AddRange(@($label, $inputBox, $save, $cancel))
        $form.AcceptButton = $save
        $form.CancelButton = $cancel
        try {
            if ($form.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
                Write-Host 'Key entry cancelled. No credential saved.'
                return
            }
            if ([string]::IsNullOrWhiteSpace($inputBox.Text)) { throw 'No API key supplied.' }
            $secure = ConvertTo-SecureString $inputBox.Text.Trim() -AsPlainText -Force
        } finally {
            $inputBox.Clear()
            $form.Dispose()
        }
    } else {
        $secure = Read-Host 'Paste your TypeSafe API key (input hidden)' -AsSecureString
        if ($secure.Length -eq 0) { throw 'No API key supplied.' }
    }

    $folder = Split-Path -Parent $KeyFile
    New-Item -ItemType Directory -Force -Path $folder | Out-Null
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl = New-Object System.Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true, $false)
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($identity, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule)
    Set-Acl -LiteralPath $folder -AclObject $acl
    # With no explicit encryption key, Windows DPAPI binds this to the current user.
    $encrypted = ConvertFrom-SecureString $secure
    [System.IO.File]::WriteAllText($KeyFile, $encrypted)
    Write-Host 'TypeSafe key saved using Windows account encryption. The key value was not printed.'
} finally {
    if ($null -ne $secure) { $secure.Dispose() }
}
