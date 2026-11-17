param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("cache-on", "cache-off", "cache-status", "stats", "reset-stats")]
    [string]$Action,
    [string]$BaseUrl = "",
    [switch]$Local
)

$ErrorActionPreference = "Stop"

if ($Local) {
    $BaseUrl = "http://localhost:8000"
    $line = Get-Content "$PSScriptRoot\..\.env" | Where-Object { $_ -match '^ADMIN_TOKEN=' } | Select-Object -First 1
    $token = $line -replace '^ADMIN_TOKEN=', ''
}
else {
    $tf = "-chdir=$PSScriptRoot\..\terraform"
    if (-not $BaseUrl) {
        $BaseUrl = terraform $tf output -raw app_url
    }
    $secretId = terraform $tf output -raw admin_token_secret_name
    $token = aws secretsmanager get-secret-value --secret-id $secretId --query SecretString --output text
}

$headers = @{ "X-Admin-Token" = $token }

switch ($Action) {
    "cache-on" {
        Invoke-RestMethod -Method Put -Uri "$BaseUrl/admin/cache" -Headers $headers -ContentType "application/json" -Body '{"enabled": true}'
        Write-Host "Cache enabled. Other instances pick it up within 5 seconds."
    }
    "cache-off" {
        Invoke-RestMethod -Method Put -Uri "$BaseUrl/admin/cache" -Headers $headers -ContentType "application/json" -Body '{"enabled": false}'
        Write-Host "Cache disabled. Other instances pick it up within 5 seconds."
    }
    "cache-status" {
        Invoke-RestMethod -Uri "$BaseUrl/admin/cache" -Headers $headers
    }
    "stats" {
        Invoke-RestMethod -Uri "$BaseUrl/admin/stats" -Headers $headers
    }
    "reset-stats" {
        Invoke-RestMethod -Method Delete -Uri "$BaseUrl/admin/stats" -Headers $headers
        Write-Host "Stats reset."
    }
}
