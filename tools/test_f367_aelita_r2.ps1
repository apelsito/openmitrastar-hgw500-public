param([Parameter(Mandatory=$true)][string]$ResultPath)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'f367_aelita_client_r2.ps1'),[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'PAYLOAD_PARSE'}
$function=$ast.Find({param($node)$node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -ceq 'Bound-Curl'},$true)
if(-not $function){throw 'MISSING_BOUND_CURL'}
Invoke-Expression $function.Extent.Text
function Assert-Control {}
$script:Seen=@()
function Invoke-FakeF367Curl {
 $script:Seen=@($args);$global:LASTEXITCODE=0
 $size=if($args -contains '--head'){0}else{4194304}
 Write-Output ('http=200;local=192.168.1.77;remote=192.168.1.49;bytes='+$size)
}
$curlExe='Invoke-FakeF367Curl';$config=[pscustomobject]@{traffic=[pscustomobject]@{timeout_seconds=30;bytes_each_direction=4194304}}
$stage=Join-Path ([IO.Path]::GetTempPath()) ('f367-curl-'+[Guid]::NewGuid().ToString('N'));[void][IO.Directory]::CreateDirectory($stage)
$checks=0
try {
 foreach($method in @('GET','PUT','HEAD')){
  $row=Bound-Curl $method 'http://192.168.1.49:8081/speed.bin' '192.168.1.77'
  $i=[Array]::IndexOf($script:Seen,'--interface')
  if($i-lt 0 -or $script:Seen[$i+1]-cne '192.168.1.77' -or $script:Seen -notcontains '--noproxy' -or $script:Seen[-1]-cne 'http://192.168.1.49:8081/speed.bin' -or $row.local_ip -cne '192.168.1.77'){throw 'SOURCE_BOUND_ARGS_NOT_USED'}
  if($method -ceq 'PUT' -and $script:Seen -notcontains '--upload-file'){throw 'UPLOAD_ARGS'}
  if($method -ceq 'HEAD' -and $script:Seen -notcontains '--head'){throw 'HEAD_ARGS'}
  $checks++
 }
 $result=@{passed=$true;tests=$checks;hardware_actions=$false;curl_backend='FAKE';actual_payload_function=$true}
 [IO.File]::WriteAllText([IO.Path]::GetFullPath($ResultPath),($result|ConvertTo-Json),[Text.UTF8Encoding]::new($false));$result|ConvertTo-Json
} finally {
 foreach($name in @('upload.bin','curl-GET.stderr','curl-PUT.stderr','curl-HEAD.stderr')){$path=Join-Path $stage $name;if([IO.File]::Exists($path)){[IO.File]::Delete($path)}}
 [IO.Directory]::Delete($stage,$false)
}
