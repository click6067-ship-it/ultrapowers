# Orca managed WSL CLI PowerShell bridge
[CmdletBinding(PositionalBinding=$false, DefaultParameterSetName='Run')]
param(
  [Parameter(ParameterSetName='Run', Mandatory=$true)]
  [string]$OrcaLauncher,

  [Parameter(ParameterSetName='Run')]
  [string]$WslCwd,

  [Parameter(ParameterSetName='Run', Mandatory=$true)]
  [Parameter(ParameterSetName='SelfTest', Mandatory=$true)]
  [string]$ForwardArgsB64,

  # Decode ForwardArgsB64, escape it, parse the escaped command line back
  # through the real Win32 CommandLineToArgvW, and print the recovered argv
  # as Base64(UTF8(JSON)). Never launches a child process.
  [Parameter(ParameterSetName='SelfTest', Mandatory=$true)]
  [switch]$SelfTestArgEscaping
)

function Repair-CaseFoldedProcessPath {
  $processEnv = [Environment]::GetEnvironmentVariables("Process")
  $pathKeys = @(
    $processEnv.Keys |
      Where-Object { $_ -ieq "Path" }
  )
  if ($pathKeys.Count -le 1) {
    return
  }

  # Orca's uppercase PATH contains its attribution shim plus the inherited
  # Windows path. Capture it before deleting both case variants.
  $pathValue = $processEnv["PATH"]
  if ([string]::IsNullOrEmpty($pathValue)) {
    $pathValue = [Environment]::GetEnvironmentVariable("Path", "Process")
  }
  if ([string]::IsNullOrEmpty($pathValue)) {
    throw "Cannot normalize duplicate PATH/Path keys without a path value."
  }
  foreach ($pathKey in $pathKeys) {
    Remove-Item -LiteralPath ("Env:" + $pathKey) -ErrorAction SilentlyContinue
  }
  [Environment]::SetEnvironmentVariable("Path", $pathValue, "Process")

  $remaining = @(
    [Environment]::GetEnvironmentVariables("Process").Keys |
      Where-Object { $_ -ieq "Path" }
  )
  if ($remaining.Count -ne 1) {
    throw "PATH/Path normalization did not produce exactly one process key."
  }
}

# Windows PowerShell 5.1 rebuilds `& exe @args` command lines without escaping
# embedded double quotes (no $PSNativeCommandArgumentPassing before PS 7.2), so
# the child's CommandLineToArgvW consumed quotes out of orchestration specs and
# payloads. Assemble the command line here with the inverse of the
# CommandLineToArgvW rules: 2n backslashes before a delimiter quote, 2n+1
# before a literal quote, doubled trailing backslashes inside quotes.
function ConvertTo-NativeArgument {
  param([AllowEmptyString()][string]$Argument)
  if ($Argument.Length -gt 0 -and $Argument -notmatch '[\s"]') {
    return $Argument
  }
  $builder = New-Object System.Text.StringBuilder
  [void]$builder.Append('"')
  $index = 0
  while ($index -lt $Argument.Length) {
    $backslashes = 0
    while ($index -lt $Argument.Length -and $Argument[$index] -eq '\') {
      $backslashes++
      $index++
    }
    if ($index -ge $Argument.Length) {
      [void]$builder.Append('\' * ($backslashes * 2))
    } elseif ($Argument[$index] -eq '"') {
      [void]$builder.Append('\' * ($backslashes * 2 + 1)).Append('"')
      $index++
    } else {
      [void]$builder.Append('\' * $backslashes).Append($Argument[$index])
      $index++
    }
  }
  [void]$builder.Append('"')
  return $builder.ToString()
}

function ConvertTo-NativeCommandLine {
  param([string[]]$Arguments)
  return @(
    $Arguments | ForEach-Object { ConvertTo-NativeArgument -Argument $_ }
  ) -join ' '
}

function Read-ForwardArgs {
  param([string]$Encoded)
  $forwardJson = [Text.Encoding]::UTF8.GetString(
    [Convert]::FromBase64String($Encoded)
  )
  return @($forwardJson | ConvertFrom-Json)
}

if ($PSCmdlet.ParameterSetName -eq 'SelfTest') {
  $exitCode = 1
  try {
    Repair-CaseFoldedProcessPath
    $vectors = Read-ForwardArgs -Encoded $ForwardArgsB64
    Add-Type -Namespace OrcaBridge -Name ArgvProbe -MemberDefinition @'
[DllImport("shell32.dll", SetLastError = true)]
public static extern IntPtr CommandLineToArgvW([MarshalAs(UnmanagedType.LPWStr)] string lpCmdLine, out int pNumArgs);
[DllImport("kernel32.dll")]
public static extern IntPtr LocalFree(IntPtr hMem);
'@
    $commandLine = '"C:\probe dir\child.exe"'
    $tail = ConvertTo-NativeCommandLine -Arguments $vectors
    if ($tail.Length -gt 0) {
      $commandLine = $commandLine + ' ' + $tail
    }
    $argvCount = 0
    $argvPtr = [OrcaBridge.ArgvProbe]::CommandLineToArgvW(
      $commandLine, [ref]$argvCount
    )
    if ($argvPtr -eq [IntPtr]::Zero) {
      throw "CommandLineToArgvW rejected the assembled command line."
    }
    try {
      $parsed = New-Object 'System.Collections.Generic.List[string]'
      for ($argvIndex = 1; $argvIndex -lt $argvCount; $argvIndex++) {
        $itemPtr = [Runtime.InteropServices.Marshal]::ReadIntPtr(
          $argvPtr, $argvIndex * [IntPtr]::Size
        )
        $parsed.Add([Runtime.InteropServices.Marshal]::PtrToStringUni($itemPtr))
      }
    } finally {
      [void][OrcaBridge.ArgvProbe]::LocalFree($argvPtr)
    }
    $resultJson = ConvertTo-Json -Compress -InputObject @{
      argv = $parsed.ToArray()
    }
    # Base64 keeps the recovered argv immune to console codepage mangling.
    Write-Output ([Convert]::ToBase64String(
      [Text.Encoding]::UTF8.GetBytes($resultJson)
    ))
    $exitCode = 0
  } catch {
    Write-Error $_
  }
  exit $exitCode
}

$exitCode = 0
try {
  Repair-CaseFoldedProcessPath

  $ForwardArgs = Read-ForwardArgs -Encoded $ForwardArgsB64

  if ([string]::IsNullOrEmpty($WslCwd)) {
    Remove-Item Env:ORCA_CLI_CWD -ErrorAction SilentlyContinue
  } else {
    $env:ORCA_CLI_CWD = $WslCwd
  }
  Push-Location -LiteralPath (Split-Path -Parent $OrcaLauncher)

  # ProcessStartInfo.Arguments is passed to CreateProcessW verbatim, so the
  # escaping above is exactly what the child's argv parser sees. Standard
  # handles stay inherited (no redirection): stdout/stderr streaming and
  # stdin behave as with direct invocation.
  $startInfo = New-Object System.Diagnostics.ProcessStartInfo
  $startInfo.FileName = $OrcaLauncher
  $startInfo.Arguments = ConvertTo-NativeCommandLine -Arguments $ForwardArgs
  $startInfo.UseShellExecute = $false
  $startInfo.WorkingDirectory = (Get-Location).ProviderPath
  $process = [System.Diagnostics.Process]::Start($startInfo)
  $process.WaitForExit()
  $exitCode = $process.ExitCode
} catch {
  Write-Error $_
  $exitCode = 1
}
exit $exitCode
