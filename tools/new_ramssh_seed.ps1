$bytes = New-Object byte[] 32
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$rng.Dispose()
$hex = -join ($bytes | ForEach-Object { $_.ToString('x2') })
Write-Output "seed_$hex"
[Array]::Clear($bytes, 0, $bytes.Length)
