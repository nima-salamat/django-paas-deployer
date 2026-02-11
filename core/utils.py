import uuid

def is_valid_uuid4(text):
    try:
        # Convert string to UUID
        val = uuid.UUID(text, version=4)
        
        # Check if it's version 4 (UUID v4 has specific bit pattern)
        # The version is stored in the 4 most significant bits of byte 6
        return val.version == 4 and str(val) == text
    except ValueError:
        return False


