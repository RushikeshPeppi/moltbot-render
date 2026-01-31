from cryptography.fernet import Fernet

def generate_encryption_key() -> str:
    """Generate a new encryption key"""
    return Fernet.generate_key().decode()

if __name__ == "__main__":
    # Run this to generate a key for .env
    print(f"ENCRYPTION_KEY={generate_encryption_key()}")