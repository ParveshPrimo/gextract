import os
import logging

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "database")
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "screenshots")

def setup_directories():
    """Create project directories if they do not exist."""
    for directory in [DB_DIR, DOWNLOADS_DIR, LOGS_DIR, SCREENSHOTS_DIR]:
        os.makedirs(directory, exist_ok=True)

def get_logger(job_id=None):
    """
    Get a configured logger.
    If job_id is provided, returns a job-specific logger that logs to
    logs/job_{job_id}.log as well as propagating to the main app log and console.
    """
    setup_directories()
    
    # Configure main logger
    main_logger = logging.getLogger("google_maps_extractor")
    main_logger.setLevel(logging.INFO)
    
    # Only add handlers if they don't exist
    if not main_logger.handlers:
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')
        
        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(formatter)
        main_logger.addHandler(ch)
        
        # Main log file handler
        app_log_path = os.path.join(LOGS_DIR, "app.log")
        app_fh = logging.FileHandler(app_log_path, mode='a', encoding='utf-8')
        app_fh.setLevel(logging.INFO)
        app_fh.setFormatter(formatter)
        main_logger.addHandler(app_fh)
        
    if job_id:
        # Child logger for specific job
        job_logger = logging.getLogger(f"google_maps_extractor.job_{job_id}")
        job_logger.setLevel(logging.INFO)
        
        if not job_logger.handlers:
            job_log_path = os.path.join(LOGS_DIR, f"job_{job_id}.log")
            job_fh = logging.FileHandler(job_log_path, mode='w', encoding='utf-8')
            job_fh.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            job_fh.setFormatter(formatter)
            job_logger.addHandler(job_fh)
            # Ensure it propagates to the main logger
            job_logger.propagate = True
            
        return job_logger
        
    return main_logger
