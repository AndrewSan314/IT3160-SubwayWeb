$Port = if ($args.Count -gt 0) { $args[0] } else { 8010 }
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot
python -m uvicorn app.main:app --host 127.0.0.1 --port $Port --reload
