$ErrorActionPreference = "Stop"
$docker = "C:\Program Files\Docker\Docker\resources\bin"
if (Test-Path $docker) {
    $env:PATH = "$docker;$env:PATH"
}

$script = @'
set -eu
db="$POSTGRES_DB"
user="$POSTGRES_USER"
target="price_lens_restore_smoke"
dump="/tmp/price-lens-restore-smoke.dump"
exists="$(psql -U "$user" -d "$db" -tAc "SELECT 1 FROM pg_database WHERE datname = '$target'")"
if [ "$exists" = "1" ]; then
  echo "Refusing to overwrite existing database $target" >&2
  exit 2
fi
before="$(psql -U "$user" -d "$db" -tAc 'SELECT count(*) FROM core.market_price_observations')"
trap 'dropdb -U "$user" --if-exists "$target" >/dev/null; rm -f "$dump"' EXIT
pg_dump -U "$user" -d "$db" -Fc -f "$dump"
createdb -U "$user" -T template0 "$target"
pg_restore -U "$user" -d "$target" --exit-on-error "$dump"
after="$(psql -U "$user" -d "$target" -tAc 'SELECT count(*) FROM core.market_price_observations')"
test "$before" = "$after"
echo "Backup/restore passed: $before observations restored; source database unchanged."
'@

$encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($script))
docker compose exec -T db sh -c "echo $encoded | base64 -d | sh"
if ($LASTEXITCODE -ne 0) { throw "Backup/restore smoke failed." }
