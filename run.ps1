# Hide the output
$VerbosePreference = 'SilentlyContinue'

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