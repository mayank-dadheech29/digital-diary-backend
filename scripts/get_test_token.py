import jwt
import os
import datetime
from dotenv import load_dotenv
import uuid

# Load .env explicitly
load_dotenv()

secret = os.getenv("SUPABASE_JWT_SECRET")
if not secret or secret == "your-secret-token":
    print("Error: SUPABASE_JWT_SECRET not set in .env")
    exit(1)

# Create a FIXED dummy user UUID for consistent testing
user_id = "11111111-1111-1111-1111-111111111111"

# Create a token valid for 1 hour
payload = {
    "sub": user_id,
    "aud": "authenticated",
    "role": "authenticated",
    "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)
}

token = jwt.encode(payload, secret, algorithm="HS256")

print(f"\nGeneratng token for User ID: {user_id}")
print(f"Token: {token}\n")

print("Test Create Contact:")
print(f"curl -X POST 'http://localhost:8000/api/v1/contacts/' \\")
print(f"  -H 'Authorization: Bearer {token}' \\")
print(f"  -H 'Content-Type: application/json' \\")
print(f"  -d '{{\"full_name\": \"Test Person\", \"primary_title\": \"Developer\", \"dynamic_details\": {{\"email\": \"test@example.com\"}}}}'")

print("\n\nTest Search:")
print(f"curl -X POST 'http://localhost:8000/api/v1/contacts/search' \\")
print(f"  -H 'Authorization: Bearer {token}' \\")
print(f"  -H 'Content-Type: application/json' \\")
print(f"  -d '{{\"query\": \"Developer\", \"limit\": 1}}'")
