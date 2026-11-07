<#
.SYNOPSIS
Import every Firebase Auth user from users.json into Clerk with Clerk's
official migration tool, keeping their passwords.

.DESCRIPTION
Run this on your own computer from the repo root. users.json holds every
user's password hash and must never be committed or uploaded anywhere.

Before running:

  1. Export the users (users.json is already gitignored):

       firebase auth:export users.json --format=json --project citey-ad63a

  2. Set the four hash parameters from the Firebase Console
     (Authentication > Users > "..." menu > Password hash parameters):

       $env:FIREBASE_HASH_SIGNER_KEY     = "..."   # base64_signer_key
       $env:FIREBASE_HASH_SALT_SEPARATOR = "..."   # base64_salt_separator
       $env:FIREBASE_HASH_ROUNDS         = "8"     # rounds
       $env:FIREBASE_HASH_MEM_COST       = "14"    # mem_cost

  3. Set the Clerk secret key of the instance to import into:

       $env:CLERK_SECRET_KEY = "sk_test_..."   # development
       $env:CLERK_SECRET_KEY = "sk_live_..."   # production, with -Production

  4. Install Bun once if you don't have it (https://bun.sh):

       powershell -c "irm bun.sh/install.ps1 | iex"

Then:

  .\backend\scripts\import_users_to_clerk.ps1 -DryRun     # counts only, sends nothing
  .\backend\scripts\import_users_to_clerk.ps1             # development instance
  .\backend\scripts\import_users_to_clerk.ps1 -Production # production instance

Each user's Firebase UID becomes their Clerk external_id, which the API uses
to find their data. Unverified emails stay unverified. Users who already
exist in Clerk fail with a duplicate error in the tool's log and are left as
they are, so the script is safe to run again.

.PARAMETER UsersFile
The Firebase export. Defaults to users.json in the current folder.

.PARAMETER Production
Required to import with an sk_live_ key, so production is never hit by accident.

.PARAMETER DryRun
Check the inputs and count the users without contacting Clerk.

.PARAMETER Yes
Skip the typed confirmation, for running from a non-interactive shell.

.PARAMETER ResumeAfter
A Firebase UID to resume after, if a previous run stopped partway.
#>
[CmdletBinding()]
param(
    [string]$UsersFile = "users.json",
    [switch]$Production,
    [switch]$DryRun,
    [switch]$Yes,
    [string]$ResumeAfter
)

$ErrorActionPreference = "Stop"

# Pinned so a change upstream can't alter what runs against the user data.
$ToolRepo   = "https://github.com/clerk/migration-tool.git"
$ToolCommit = "bbf75584668e9f10a239b545adbce57e1308c974"
$ToolDir    = Join-Path $env:LOCALAPPDATA "clerk-migration-tool"

function Fail([string]$Message) {
    Write-Host "Error: $Message" -ForegroundColor Red
    exit 1
}

# --- Inputs ------------------------------------------------------------------

if (-not (Test-Path $UsersFile)) {
    Fail "$UsersFile not found. Export it first: firebase auth:export users.json --format=json --project citey-ad63a"
}
$UsersPath = (Resolve-Path $UsersFile).Path

$hashVars = "FIREBASE_HASH_SIGNER_KEY", "FIREBASE_HASH_SALT_SEPARATOR", "FIREBASE_HASH_ROUNDS", "FIREBASE_HASH_MEM_COST"
$missing = $hashVars | Where-Object { -not [Environment]::GetEnvironmentVariable($_) }
if ($missing) {
    Fail "Set these from Firebase's password hash parameters: $($missing -join ', ')"
}
foreach ($name in "FIREBASE_HASH_ROUNDS", "FIREBASE_HASH_MEM_COST") {
    if ([Environment]::GetEnvironmentVariable($name) -notmatch '^\d+$') {
        Fail "$name must be a whole number."
    }
}

$key = $env:CLERK_SECRET_KEY
if (-not $key) {
    Fail "Set CLERK_SECRET_KEY to the instance's secret key (sk_test_ for development)."
}
if ($key.StartsWith("sk_live_")) {
    if (-not $Production) { Fail "CLERK_SECRET_KEY is a production key. Pass -Production to import into production." }
    $instance = "PRODUCTION"
} elseif ($key.StartsWith("sk_test_")) {
    if ($Production) { Fail "-Production was passed but CLERK_SECRET_KEY is a development key (sk_test_)." }
    $instance = "development"
} else {
    Fail "CLERK_SECRET_KEY should start with sk_test_ or sk_live_."
}

# --- Summary -----------------------------------------------------------------

$export = Get-Content $UsersPath -Raw | ConvertFrom-Json
$users = if ($export.users) { @($export.users) } else { @($export) }
$withEmail    = @($users | Where-Object { $_.email })
$withPassword = @($withEmail | Where-Object { $_.passwordHash })
$unverified   = @($withEmail | Where-Object { -not $_.emailVerified })

Write-Host ""
Write-Host "Clerk instance:        $instance"
Write-Host "Users in export:       $($users.Count)"
Write-Host "  with an email:       $($withEmail.Count)"
Write-Host "  with a password:     $($withPassword.Count)"
Write-Host "  email not verified:  $($unverified.Count)"
Write-Host ""

if ($DryRun) {
    Write-Host "Dry run: nothing was sent to Clerk."
    exit 0
}

# --- Tool --------------------------------------------------------------------

if (-not (Get-Command bun -ErrorAction SilentlyContinue)) {
    Fail "Bun is not installed. Install it with: powershell -c `"irm bun.sh/install.ps1 | iex`" and open a new terminal."
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail "git is not installed."
}

if (-not (Test-Path (Join-Path $ToolDir ".git"))) {
    Write-Host "Downloading Clerk's migration tool to $ToolDir"
    git clone --quiet $ToolRepo $ToolDir
    if ($LASTEXITCODE -ne 0) { Fail "git clone failed." }
}

Push-Location $ToolDir
try {
    git fetch --quiet origin
    git checkout --quiet $ToolCommit
    if ($LASTEXITCODE -ne 0) { Fail "Could not check out the pinned commit $ToolCommit." }

    # A leftover .env in the tool folder would override the key set here.
    if (Test-Path ".env") {
        Fail "$ToolDir\.env exists and could hold a different secret key. Delete it and run again."
    }

    bun install --frozen-lockfile
    if ($LASTEXITCODE -ne 0) { Fail "bun install failed." }

    if (-not $Yes) {
        $confirm = Read-Host "Import $($withEmail.Count) users into the $instance Clerk instance? Type yes to continue"
        if ($confirm -ne "yes") {
            Write-Host "Cancelled."
            exit 0
        }
    }

    # The tool joins --file onto its own folder even when the path is
    # absolute, so it needs the export's path relative to that folder.
    $toolUri = New-Object System.Uri ((Join-Path $ToolDir "x"))
    $usersUri = New-Object System.Uri $UsersPath
    $relativeUsers = [System.Uri]::UnescapeDataString($toolUri.MakeRelativeUri($usersUri).ToString()) -replace '/', '\'

    # The secret key is passed through the environment, not the command line,
    # so it doesn't show up in the process list or shell history.
    $toolArgs = @(
        "migrate", "-y",
        "-t", "firebase",
        "-f", $relativeUsers,
        "--firebase-signer-key", $env:FIREBASE_HASH_SIGNER_KEY,
        "--firebase-salt-separator", $env:FIREBASE_HASH_SALT_SEPARATOR,
        "--firebase-rounds", $env:FIREBASE_HASH_ROUNDS,
        "--firebase-mem-cost", $env:FIREBASE_HASH_MEM_COST
    )
    if ($ResumeAfter) { $toolArgs += @("-r", $ResumeAfter) }

    bun @toolArgs
    $exit = $LASTEXITCODE

    Write-Host ""
    Write-Host "Logs: $ToolDir\logs"
    Write-Host "Duplicate errors there are users who were already in Clerk, which is expected."
    exit $exit
} finally {
    Pop-Location
}
