$ErrorActionPreference = "Stop"
$docker = "C:\Program Files\Docker\Docker\resources\bin"
if (Test-Path $docker) {
    $env:PATH = "$docker;$env:PATH"
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

docker compose up --build -d db api frontend
if ($LASTEXITCODE -ne 0) { throw "Docker Compose failed to start Price Lens." }

$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        $health = Invoke-RestMethod "http://localhost:8000/api/v1/health" -TimeoutSec 3
        if ($health.status -eq "ok") {
            $ready = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 2
    }
}
if (-not $ready) { throw "API did not become healthy. Check: docker compose logs api" }

Write-Host "Price Lens is ready."
Write-Host "AI Search: http://localhost:3000/#ai-search"
Write-Host "API docs:  http://localhost:8000/docs"
