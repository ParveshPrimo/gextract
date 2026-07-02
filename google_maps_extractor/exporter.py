import os
import pandas as pd
from typing import Tuple

from .database import get_job_results
from .utils import DOWNLOADS_DIR

COLUMN_MAPPING = {
    "name": "Business Name",
    "category": "Category",
    "rating": "Rating",
    "reviews": "Reviews",
    "phone": "Phone",
    "website": "Website",
    "address": "Address",
    "maps_url": "Google Maps URL",
    "latitude": "Latitude",
    "longitude": "Longitude",
    "opening_hours": "Opening Hours"
}

def export_results(job_id: int, format_type: str) -> Tuple[str, str]:
    """
    Export results for a specific job to CSV or Excel.
    
    Args:
        job_id: The ID of the extraction job.
        format_type: Either 'CSV' or 'Excel'.
        
    Returns:
        A tuple of (absolute_file_path, file_name)
    """
    # Fetch results from database
    results = get_job_results(job_id)
    if not results:
        # Create empty list of dicts to keep column schema
        results = []
        
    # Convert to DataFrame
    df = pd.DataFrame(results)
    
    # Filter and rename columns
    columns_to_keep = list(COLUMN_MAPPING.keys())
    
    # Ensure all required columns exist in df (even if empty)
    for col in columns_to_keep:
        if col not in df.columns:
            df[col] = None
            
    df = df[columns_to_keep]
    df = df.rename(columns=COLUMN_MAPPING)
    
    # Define filename and path
    ext = "csv" if format_type.upper() == "CSV" else "xlsx"
    filename = f"results_job_{job_id}.{ext}"
    filepath = os.path.join(DOWNLOADS_DIR, filename)
    
    # Export based on format
    if format_type.upper() == "CSV":
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
    else:
        df.to_excel(filepath, index=False, engine="openpyxl")
        
    return filepath, filename
