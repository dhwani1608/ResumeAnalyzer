import io
import zipfile
from typing import List, Tuple

def extract_resumes_from_zip(zip_bytes: bytes) -> List[Tuple[str, bytes]]:
    """
    Extracts valid resume files from a ZIP archive.
    Returns a list of (filename, file_bytes).
    """
    resumes = []
    valid_extensions = {'.pdf', '.docx', '.txt', '.md'}
    
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        for file_info in z.infolist():
            # Skip directories and hidden files
            if file_info.is_dir() or file_info.filename.startswith('__') or file_info.filename.startswith('.'):
                continue
                
            ext = '.' + file_info.filename.split('.')[-1].lower() if '.' in file_info.filename else ''
            if ext in valid_extensions:
                with z.open(file_info) as f:
                    resumes.append((file_info.filename, f.read()))
                    
    return resumes
