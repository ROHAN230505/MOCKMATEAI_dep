<#
.SYNOPSIS
  Write an LLM API key into backend/.env.

.DESCRIPTION
  Prompts for the key and writes it in place. It exists so the key is typed
  into your own terminal rather than pasted into a chat transcript or left in
  shell history: it is read as a SecureString, never echoed, and never passed
  as a command-line argument.

  The provider is recognised from the key's own prefix, so there is no second
  setting to keep in sync:
    sk-ant-  Anthropic
    gsk_     Groq
    sk-      OpenAI

  Everything else in .env is preserved, and a timestamped backup is taken.
#>

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$envPath = Join-Path (Split-Path -Parent $scriptDir) '.env'
if (-not (Test-Path $envPath)) {
    Write-Host "Could not find $envPath" -ForegroundColor Red
    exit 1
}

Write-Host ''
Write-Host 'LLM API key -> backend/.env' -ForegroundColor Cyan
Write-Host 'Groq: console.groq.com   Anthropic: console.anthropic.com'
Write-Host ''

$secure = Read-Host 'API key (hidden as you type)' -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
$key = $key.Trim().Trim('"').Trim("'")

if ([string]::IsNullOrWhiteSpace($key)) {
    Write-Host 'Nothing entered. Aborted, nothing was changed.' -ForegroundColor Yellow
    exit 1
}

if ($key.StartsWith('sk-ant-'))  { $provider = 'Anthropic' }
elseif ($key.StartsWith('gsk_')) { $provider = 'Groq' }
elseif ($key.StartsWith('sk-'))  { $provider = 'OpenAI' }
else {
    Write-Host ''
    Write-Host 'That prefix is not recognised, so the app would ignore the key and' -ForegroundColor Yellow
    Write-Host 'keep using the offline mock adapter.' -ForegroundColor Yellow
    $go = Read-Host 'Write it anyway? (y/N)'
    if ($go -ne 'y') { Write-Host 'Aborted, nothing was changed.'; exit 1 }
    $provider = 'unrecognised'
}

$backup = "$envPath.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
Copy-Item $envPath $backup

$lines = [IO.File]::ReadAllLines($envPath)
$done = $false
for ($i = 0; $i -lt $lines.Length; $i++) {
    if ($lines[$i] -match '^s*MOCKMATEAI_LLM_API_KEYs*=') {
        $lines[$i] = "MOCKMATEAI_LLM_API_KEY=$key"
        $done = $true
    }
}
if (-not $done) { $lines += "MOCKMATEAI_LLM_API_KEY=$key" }

# UTF-8 with no BOM: a BOM lands in the first key's name and that setting is
# then silently ignored by the config loader.
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllLines($envPath, $lines, $utf8NoBom)

Write-Host ''
Write-Host 'Saved.' -ForegroundColor Green
Write-Host "  provider : $provider (from the key prefix)"
Write-Host "  key      : set ($($key.Length) characters, not shown)"
Write-Host "  backup   : $backup"
Write-Host ''
Write-Host 'Now restart the backend -- config is read once at startup.' -ForegroundColor Cyan
Write-Host ''
