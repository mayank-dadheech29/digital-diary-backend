import os
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from uuid import UUID

# bearer_scheme will extract the "Bearer <token>" from the Authorization header
security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> UUID:
    """
    Validates the Supabase JWT by calling the Supabase Auth API (`GET /auth/v1/user`).
    
    This method is robust against key rotation (RS256 vs HS256) because it delegates
    verification to Supabase itself.
    """
    token = credentials.credentials
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_anon_key = os.getenv("SUPABASE_ANON_KEY")
    
    if not supabase_url or not supabase_anon_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server Config Error: Missing SUPABASE_URL or SUPABASE_ANON_KEY"
        )

    # Call Supabase to verify the token
    # We use the Anon Key in headers, but the User Token in Authorization
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{supabase_url}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": supabase_anon_key
                }
            )
        except httpx.RequestError as e:
             raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Auth Service Unavailable: {str(e)}"
            )

    if response.status_code != 200:
        # 401 from Supabase becomes 401 from us
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_data = response.json()
    user_id = user_data.get("id")
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User ID not found in token",
        )
        
    return UUID(user_id)
