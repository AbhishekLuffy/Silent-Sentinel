from database_utils import get_all_logs
from tabulate import tabulate

def view_database_logs():
    """Display all logs from the database in a nicely formatted table."""
    logs = get_all_logs()
    
    if not logs:
        print("No logs found in the database.")
        return

    # Convert logs to a list of dictionaries for better display
    headers = ["ID", "Filename", "Timestamp", "Location URL", "Transcription"]
    
    # Format the table
    print("\n=== Silent Sentinel Audio Logs ===\n")
    print(tabulate(logs, headers=headers, tablefmt="grid"))
    print(f"\nTotal Entries: {len(logs)}")

if __name__ == "__main__":
    view_database_logs() 