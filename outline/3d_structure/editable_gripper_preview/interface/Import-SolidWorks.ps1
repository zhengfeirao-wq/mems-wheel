param(
    [ValidateSet(12,32)][int]$Channel = 32,
    [ValidateSet('assembled','exploded')][string]$State = 'assembled',
    [string]$PartId = '',
    [string]$AssetRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$ResolveOnly
)
$ErrorActionPreference = 'Stop'
$assetPath = (Resolve-Path -LiteralPath $AssetRoot).Path
$manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $assetPath 'interface\manifest.json') | ConvertFrom-Json
if ($manifest.schema_version -ne 1) { throw 'Unsupported interface schema.' }
$model = $manifest.models.PSObject.Properties[[string]$Channel].Value
if ($PartId) {
    if ($State -ne 'assembled') { throw 'Individual STEP files use assembled/source coordinates.' }
    $part = @($model.parts | Where-Object id -CEQ $PartId)
    if ($part.Count -ne 1) { throw "Unknown part ID: $PartId" }
    if (-not $part[0].step_file) { throw 'This part is a named component of the full assembly STEP; it has no standalone STEP.' }
    $reference = $part[0].step_file
} else {
    $reference = $model.step.PSObject.Properties[$State].Value
}
$stepPath = [IO.Path]::GetFullPath((Join-Path $assetPath $reference))
if (-not $stepPath.StartsWith($assetPath + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
    throw 'STEP path leaves the accepted asset directory.'
}
if (-not (Test-Path -LiteralPath $stepPath -PathType Leaf)) { throw "STEP file missing: $stepPath" }
if ($ResolveOnly) {
    [PSCustomObject]@{Revision=$manifest.revision;Channel=$Channel;State=$State;PartId=$PartId;Units='mm';StepFile=$stepPath}
    return
}
# Windows PowerShell 5.1. SOLIDWORKS must be installed and licensed locally.
try { $sw = New-Object -ComObject SldWorks.Application }
catch { throw "Cannot start SOLIDWORKS COM. Install/activate SOLIDWORKS, or use -ResolveOnly. $($_.Exception.Message)" }
$sw.Visible = $true
$importData = $sw.GetImportFileData($stepPath)
if ($null -eq $importData) { throw 'SOLIDWORKS did not provide STEP import data.' }
$importData.MapConfigurationData = $true
[int]$importErrors = 0
$document = $sw.LoadFile4($stepPath,'r',$importData,[ref]$importErrors)
if ($null -eq $document) { throw "SOLIDWORKS STEP import failed. Error: $importErrors" }
if ($importErrors -ne 0) { Write-Warning "SOLIDWORKS returned import error flags: $importErrors" }
# Return the live ModelDoc2 COM object to callers. Do not overwrite/save user files.
$document
