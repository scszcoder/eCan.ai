param (
    [string]$url
)

function Check-ServerStatus {
    param (
        [string]$url
    )

    try {
        # Define a timeout value
        $timeout = 5

        # Create a web request with the specified timeout
        $request = [System.Net.WebRequest]::Create($url)
        $request.Timeout = $timeout * 1000

        # Get the response
        $response = $request.GetResponse()

        if ($response.StatusCode -eq 200) {
            Write-Output "Server is running"
        } else {
            Write-Output "Server is not running"
        }
    } catch [System.Net.WebException] {
        if ($_.Exception.Status -eq [System.Net.WebExceptionStatus]::Timeout) {
            Write-Output "Request timed out"
        } elseif ($_.Exception.Response.StatusCode -eq 404) {
            Write-Output "Server is running, but the endpoint is not found (404)"
        } else {
            Write-Output "Server is not running"
        }
    } catch {
        Write-Output "An unexpected error occurred: $_"
    }
}

Check-ServerStatus -url $url
