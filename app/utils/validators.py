"""
Validators for COA data fields
"""
import re
from typing import Optional, Tuple


def validate_lot_number(lot_number: str) -> Tuple[bool, Optional[str]]:
    """
    Validate lot number format
    Returns: (is_valid, error_message)
    """
    if not lot_number:
        return False, "Lot number cannot be empty"
    
    # Allow alphanumeric with hyphens
    pattern = r'^[A-Z0-9\-]+$'
    if not re.match(pattern, lot_number.upper()):
        return False, "Lot number must contain only letters, numbers, and hyphens"
    
    if len(lot_number) < 3:
        return False, "Lot number must be at least 3 characters long"
    
    if len(lot_number) > 50:
        return False, "Lot number cannot exceed 50 characters"
    
    return True, None


def validate_storage_condition(condition: str) -> Tuple[bool, Optional[str]]:
    """
    Validate storage condition format
    Returns: (is_valid, error_message)
    """
    if not condition:
        return False, "Storage condition cannot be empty"
    
    # Check for temperature patterns
    temp_patterns = [
        r'\d+\s*[-–]\s*\d+\s*°?[CF]',  # e.g., 2-8°C, 15-25C
        r'(?:≤|<=|NMT)\s*\d+\s*°?[CF]',  # e.g., ≤25°C, NMT 30C
        r'(?:≥|>=)\s*\d+\s*°?[CF]',  # e.g., ≥-20°C
        r'room\s*temperature',  # room temperature
        r'ambient',  # ambient
        r'frozen',  # frozen
        r'refrigerat',  # refrigerated/refrigerator
    ]
    
    condition_lower = condition.lower()
    has_temp = any(re.search(pattern, condition, re.IGNORECASE) for pattern in temp_patterns)
    
    if not has_temp and len(condition) < 5:
        return False, "Storage condition seems too short or invalid"
    
    return True, None


def validate_manufacturer(manufacturer: str) -> Tuple[bool, Optional[str]]:
    """
    Validate manufacturer name
    Returns: (is_valid, error_message)
    """
    if not manufacturer:
        return False, "Manufacturer name cannot be empty"
    
    # Remove extra spaces
    manufacturer = ' '.join(manufacturer.split())
    
    if len(manufacturer) < 3:
        return False, "Manufacturer name is too short"
    
    if len(manufacturer) > 200:
        return False, "Manufacturer name is too long"
    
    # Check for common company suffixes
    company_suffixes = [
        'ltd', 'limited', 'inc', 'incorporated', 'corp', 'corporation',
        'co', 'company', 'llc', 'gmbh', 'sa', 'spa', 'plc',
        '有限公司', '股份有限公司', '集团', '公司'
    ]
    
    has_suffix = any(
        manufacturer.lower().endswith(suffix) or 
        f' {suffix}' in manufacturer.lower() 
        for suffix in company_suffixes
    )
    
    # Warning if no company suffix found (but still valid)
    if not has_suffix:
        print(f"Warning: Manufacturer '{manufacturer}' doesn't contain common company suffix")
    
    return True, None



def sanitize_field_value(value: str, field_type: str) -> str:
    """
    Sanitize field values before storage
    """
    if not value:
        return ""
    
    # Remove leading/trailing whitespace
    value = value.strip()
    
    # Remove multiple spaces
    value = ' '.join(value.split())
    
    if field_type == "lot_number":
        # Uppercase lot numbers
        value = value.upper()
    elif field_type == "storage_condition":
        # Standardize temperature symbols
        value = value.replace('℃', '°C').replace('℉', '°F')
        # Standardize ranges
        value = re.sub(r'\s*[-–]\s*', '-', value)
    
    return value


def validate_pdf_filename(filename: str) -> Tuple[bool, Optional[str]]:
    """
    Validate PDF filename
    Returns: (is_valid, error_message)
    """
    if not filename:
        return False, "Filename cannot be empty"
    
    if not filename.lower().endswith('.pdf'):
        return False, "File must be a PDF"
    
    # Check for invalid characters
    invalid_chars = '<>:"|?*'
    if any(char in filename for char in invalid_chars):
        return False, f"Filename contains invalid characters: {invalid_chars}"
    
    # Check length
    if len(filename) > 255:
        return False, "Filename is too long"
    
    return True, None