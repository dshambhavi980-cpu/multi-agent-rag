param([Parameter(Mandatory = $true)][string]$DatabaseUrl)

$ErrorActionPreference = "Stop"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$target = Join-Path "backups" $stamp
New-Item -ItemType Directory -Path $target -Force | Out-Null
npx supabase db dump --db-url $DatabaseUrl --schema public,app_private,storage --file (Join-Path $target "schema.sql")
Copy-Item -LiteralPath "supabase/config.toml" -Destination (Join-Path $target "supabase-config.toml")
Copy-Item -LiteralPath "apps/api/app/evaluation_suites" -Destination (Join-Path $target "evaluation-suites") -Recurse
Copy-Item -LiteralPath "benchmarks" -Destination (Join-Path $target "benchmarks") -Recurse
Write-Output "Backup created in $target. Encrypt it before off-site storage."
