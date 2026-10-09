<#
.SYNOPSIS
  Write Google OAuth credentials into backend/.env.

.DESCRIPTION
  Prompts for the two values and writes them in place. It exists so the client
  secret is typed into your own terminal instead of being pasted into a chat
  transcript or left in shell history -- the secret is read as a SecureString,
  never echoed, and never passed as a command-line argument.

  Everything else in .env is preserved byte for byte, and a timestamped backup
  is taken first.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scriptsset_google_oauth.ps1
#>

$ErrorActionPreference = 'Stop'

# Resolve .env relative to this script, so it works from any directory.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$envPath = Join-Path (Split-Path -Parent $scriptDir) '.env'

if (-not (Test-Path $envPath)) {
    Write-Host "Could not find $envPath" -ForegroundColor Red
    Write-Host 'Run this from the backend folder, or copy .env.example to .env first.'
    exit 1
}

Write-Host ''
Write-Host 'Google OAuth credentials -> backend/.env' -ForegroundColor Cyan
Write-Host 'From: console.cloud.google.com -> APIs & Services -> Credentials'
Write-Host ''

# --- Client ID (not secret, so shown as typed) ---------------------------
$clientId = Read-Host 'Client ID'
$clientId = $clientId.Trim().Trim('"').Trim("'")
if ([string]::IsNullOrWhiteSpace($clientId)) {
    Write-Host 'Nothing entered. Aborted, nothing was changed.' -ForegroundColor Yellow
    exit 1
}
if ($clientId -notlike '*.apps.googleusercontent.com') {
    Write-Host ''
    Write-Host 'That does not look like a Google client ID.' -ForegroundColor Yellow
    Write-Host 'They end in .apps.googleusercontent.com'
    $go = Read-Host 'Use it anyway? (y/N)'
    if ($go -ne 'y') { Write-Host 'Aborted, nothing was changed.'; exit 1 }
}

# --- Client secret (masked; never echoed, never in history) --------------
$secure = Read-Host 'Client secret (hidden as you type)' -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $clientSecret = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}
$clientSecret = $clientSecret.Trim().Trim('"').Trim("'")
if ([string]::IsNullOrWhiteSpace($clientSecret)) {
    Write-Host 'No secret entered. Aborted, nothing was changed.' -ForegroundColor Yellow
    exit 1
}

# --- Back up, then rewrite just the two lines ----------------------------
$backup = "$envPath.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
Copy-Item $envPath $backup

$lines = [IO.File]::ReadAllLines($envPath)
$setId = $false
$setSecret = $false
for ($i = 0; $i -lt $lines.Length; $i++) {
    if ($lines[$i] -match '^s*MOCKMATEAI_GOOGLE_CLIENT_IDs*=') {
        $lines[$i] = "MOCKMATEAI_GOOGLE_CLIENT_ID=$clientId"
        $setId = $true
    }
    elseif ($lines[$i] -match '^s*MOCKMATEAI_GOOGLE_CLIENT_SECRETs*=') {
        $lines[$i] = "MOCKMATEAI_GOOGLE_CLIENT_SECRET=$clientSecret"
        $setSecret = $true
    }
}
# Append if the keys were absent rather than empty.
if (-not $setId) { $lines += "MOCKMATEAI_GOOGLE_CLIENT_ID=$clientId" }
if (-not $setSecret) { $lines += "MOCKMATEAI_GOOGLE_CLIENT_SECRET=$clientSecret" }

# UTF-8 with no BOM: a BOM lands in the first key's name and the setting is
# then silently ignored by the config loader.
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllLines($envPath, $lines, $utf8NoBom)

Write-Host ''
Write-Host 'Saved.' -ForegroundColor Green
Write-Host "  client id     : $clientId"
Write-Host "  client secret : set ($($clientSecret.Length) characters, not shown)"
Write-Host "  backup        : $backup"
Write-Host ''
Write-Host 'Now restart the backend -- config is read once at startup.' -ForegroundColor Cyan
Write-Host ''
