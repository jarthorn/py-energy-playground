"""
Script to find the peak month for share_of_generation_pct for each series.
This script only uses the standard library and doesn't require external dependencies.
"""
import json
from pathlib import Path


def find_peak_months_by_series(json_file_path):
    """
    Determine which month had the peak share_of_generation_pct for each series.
    
    Args:
        json_file_path: Path to the JSON file containing the API response
        
    Returns:
        Dictionary mapping series names to tuples of (peak_month, peak_value)
    """
    with open(json_file_path, 'r') as f:
        response_data = json.load(f)
    
    # Extract the data array
    data_records = response_data.get('data', [])
    
    # Group records by series and track the peak for each
    peak_by_series = {}
    
    for record in data_records:
        series = record.get('series')
        date = record.get('date')
        share_pct = record.get('share_of_generation_pct')
        
        if series is None or date is None or share_pct is None:
            continue
        
        # If this is the first record for this series, or if this value is higher
        if series not in peak_by_series or share_pct > peak_by_series[series][1]:
            peak_by_series[series] = (date, share_pct)
    
    return peak_by_series


if __name__ == "__main__":
    # Get the project root directory (parent of src/)
    project_root = Path(__file__).parent.parent
    json_file = project_root / "data" / "canada-monthly-generation.json"
    
    peak_months = find_peak_months_by_series(str(json_file))
    
    print("="*70)
    print("Peak months by series (share_of_generation_pct):")
    print("="*70)
    print(f"{'Series':<45} | {'Month':<12} | {'Peak Value':>12}")
    print("-"*70)
    for series, (month, value) in sorted(peak_months.items()):
        print(f"{series:<45} | {month:<12} | {value:>11.2f}%")
