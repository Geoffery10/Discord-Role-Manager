# Hide the output
$VerbosePreference = 'SilentlyContinue'

# Start the dashboard in a background job
$dashboardJob = Start-Job -ScriptBlock {
    python -m dashboard.main
}
Write-Host "Dashboard started in background (Job ID: $($dashboardJob.Id))"

# Continuously retry running the Python script
while($true) {
    try {
        # Run the python script
        python .\main.py
    }
    catch {
        Write-Host "An error occurred, retrying..."
        continue
    }
}
