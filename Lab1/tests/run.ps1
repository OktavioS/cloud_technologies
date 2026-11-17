param(
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

Write-Host "Testing $BaseUrl"

docker run --rm `
    -v "${PSScriptRoot}:/tests" -w /tests `
    -e BASE_URL=$BaseUrl `
    python:3.12.8-slim-bookworm `
    sh -c "pip install -q --root-user-action=ignore -r requirements.txt && pytest -v -p no:cacheprovider"
