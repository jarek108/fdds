import hashlib
import os
import logging

logger = logging.getLogger("hashes")

def calculate_file_hash(file_path: str) -> str:
    """Calculates SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            # Read in chunks to handle large files
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        logger.error(f"Error calculating hash for {file_path}: {e}")
        return None

def get_or_create_hash_file(file_path: str, force=False) -> str:
    """Returns the hash from .hash file, creating it if missing or forced."""
    hash_file_path = file_path + ".hash"
    
    if not force and os.path.exists(hash_file_path):
        try:
            with open(hash_file_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            logger.error(f"Error reading hash file {hash_file_path}: {e}")

    # Calculate and save new hash
    file_hash = calculate_file_hash(file_path)
    if file_hash:
        try:
            with open(hash_file_path, "w", encoding="utf-8") as f:
                f.write(file_hash)
            return file_hash
        except Exception as e:
            logger.error(f"Error writing hash file {hash_file_path}: {e}")
    
    return None

def ensure_hashes_recursive(root_dir: str):
    """Walks through directory and creates .hash files for all PDFs if missing."""
    count = 0
    for root, _, files in os.walk(root_dir):
        for file in files:
            if file.lower().endswith(".pdf"):
                pdf_path = os.path.join(root, file)
                if get_or_create_hash_file(pdf_path):
                    count += 1
    return count
