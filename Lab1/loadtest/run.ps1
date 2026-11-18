param(
    [string]$Label = "run",
    [int]$Vus = 60,
    [int]$Users = 5,
    [ValidateSet("sync", "async")][string]$Mode = "sync",
    [double]$Think = 0.3,
    [string]$RampUp = "3m",
    [string]$Steady = "5m",
    [string]$RampDown = "2m",
    [string]$BaseUrl = "",
    [switch]$Local
)

$ErrorActionPreference = "Stop"

if ($Local) {
    $BaseUrl = "http://host.docker.internal:8000"
}
if (-not $BaseUrl) {
    $BaseUrl = terraform "-chdir=$PSScriptRoot\..\terraform" output -raw app_url
}

$thinkText = $Think.ToString([System.Globalization.CultureInfo]::InvariantCulture)
New-Item -ItemType Directory -Force "$PSScriptRoot\results" | Out-Null

Write-Host "Target:  $BaseUrl"
Write-Host "Profile: 0 -> $Vus VU in $RampUp, hold $Steady, down in $RampDown, mode=$Mode, label=$Label"
Write-Host "Started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') (local time)"

docker run --rm -i `
    -v "${PSScriptRoot}:/scripts" -w /scripts `
    -e BASE_URL=$BaseUrl -e VUS=$Vus -e USERS=$Users -e MODE=$Mode -e THINK=$thinkText `
    -e RAMP_UP=$RampUp -e STEADY=$Steady -e RAMP_DOWN=$RampDown -e LABEL=$Label `
    grafana/k6:1.6.1 run --quiet notes.js

Write-Host "Finished: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') (local time)"
Write-Host "Report:   $PSScriptRoot\results\$Label.md"
