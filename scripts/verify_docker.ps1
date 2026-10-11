$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

function Assert-DockerCheck([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

docker compose config --quiet
Assert-DockerCheck ($LASTEXITCODE -eq 0) 'Compose validation failed.'
$backendId = docker compose ps -q backend
$frontendId = docker compose ps -q frontend
Assert-DockerCheck ([bool]$backendId -and [bool]$frontendId) 'Start both Docker services first.'
$backend = (docker inspect $backendId | ConvertFrom-Json)[0]
$frontend = (docker inspect $frontendId | ConvertFrom-Json)[0]
foreach ($container in @($backend, $frontend)) {
    Assert-DockerCheck ($container.State.Health.Status -eq 'healthy') 'Container is not healthy.'
    Assert-DockerCheck $container.HostConfig.ReadonlyRootfs 'Container root filesystem is writable.'
    Assert-DockerCheck ($container.Config.User -and $container.Config.User -ne 'root' -and $container.Config.User -ne '0') 'Container runs as root.'
    Assert-DockerCheck ($container.HostConfig.CapDrop -contains 'ALL') 'Container capabilities are not dropped.'
}
Assert-DockerCheck (@($backend.HostConfig.PortBindings.PSObject.Properties).Count -eq 0) 'Backend port must not be published.'
Assert-DockerCheck ($frontend.HostConfig.PortBindings.'8080/tcp'[0].HostIp -eq '127.0.0.1') 'Frontend must bind only to loopback.'
Assert-DockerCheck ($backend.Mounts[0].Type -eq 'volume') 'Database must use an isolated named volume.'

# Check names only; never print environment values or read host credentials.
foreach ($imageName in @('closureops-backend:task11a', 'closureops-frontend:task11a')) {
    $image = (docker image inspect $imageName | ConvertFrom-Json)[0]
    foreach ($entry in $image.Config.Env) {
        $name = ($entry -split '=', 2)[0]
        Assert-DockerCheck ($name -notmatch '(?i)(AKAMAI_INFERENCE_KEY|AWS_ACCESS_KEY|AWS_SECRET|AWS_SESSION_TOKEN|PASSWORD|CREDENTIAL|API_KEY)') 'Image contains a credential environment variable.'
    }
}
$scanBackend = @'
from pathlib import Path
root = Path('/app')
for path in root.rglob('*'):
    name = path.name.lower()
    assert name not in {'.git','.venv','node_modules','credentials.json','.aws','tests','test-results'}, 'Private directory found'
    assert not name.startswith('.env'), 'Environment file found'
    assert path.suffix.lower() not in {'.sqlite','.sqlite3','.db','.key','.pem'}, 'Private application artifact found'
assert not Path('/var/lib/closureops/docker-demo.sqlite3').exists(), 'Database baked into image'
print('Backend application image artifact check passed')
'@
docker run --rm --entrypoint python closureops-backend:task11a -c $scanBackend
Assert-DockerCheck ($LASTEXITCODE -eq 0) 'Backend image artifact check failed.'
$scanFrontend = 'find /usr/share/nginx/html -name ".env*" -o -name "*.sqlite3" -o -name "*.db" -o -name "*.key" -o -name "*.pem" -o -name "credentials.json" -o -name "node_modules" -o -name ".git" -o -name "*.map"'
$privateFrontendPaths = docker run --rm --entrypoint sh closureops-frontend:task11a -c $scanFrontend
Assert-DockerCheck ($LASTEXITCODE -eq 0 -and -not $privateFrontendPaths) 'Private artifacts or source maps found in frontend image.'

$health = Invoke-RestMethod 'http://127.0.0.1:8080/api/health'
Assert-DockerCheck ($health.status -eq 'ok' -and $health.local_demo_writes_enabled -eq $false -and $health.ai_briefing_enabled -eq $false) 'Health response reports an unsafe capability.'
Assert-DockerCheck (($health | ConvertTo-Json) -notmatch '(?i)(AKAMAI_INFERENCE_KEY|AWS_SECRET|access_token|password)') 'Unexpected sensitive health response field.'
$directBackendCheck = @'
import urllib.request, urllib.error
for route in ['/api/evaluations','/api/evaluations/eval_' + '0' * 32 + '/ai-briefing']:
    request = urllib.request.Request('http://127.0.0.1:8001' + route, data=b'{}', headers={'Content-Type':'application/json'}, method='POST')
    try:
        urllib.request.urlopen(request, timeout=5)
        raise AssertionError('Backend accepted a privileged request')
    except urllib.error.HTTPError as error:
        assert error.code == 403, 'Backend rejection must be 403'
print('Direct backend writes and inference rejected independently of Nginx')
'@
docker compose exec -T backend python -c $directBackendCheck
Assert-DockerCheck ($LASTEXITCODE -eq 0) 'Direct backend capability check failed.'
Write-Output 'Docker image, transport, persistence mount, and read-only capability checks passed.'
