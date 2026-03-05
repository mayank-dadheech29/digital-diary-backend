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
        print(f"DEBUG: Supabase auth check failed with status {response.status_code}")
        # 401 from Supabase becomes 401 from us
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_data = response.json()
    user_id = user_data.get("id")
    email = user_data.get("email")
    
    print(f"DEBUG: Authenticated user {email} (ID: {user_id})")
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User ID not found in token",
        )
        
    # Sync user with local DB
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from sqlalchemy.dialects.postgresql import insert
    
    if AsyncSessionLocal:
        async with AsyncSessionLocal() as session:
            try:
                # Upsert user record
                stmt = insert(User).values(
                    id=user_id,
                    email=email,
                ).on_conflict_do_update(
                    index_elements=['id'],
                    set_={'email': email}
                )
                await session.execute(stmt)
                await session.commit()
                print(f"DEBUG: Synced user {email} to local DB.")
            except Exception as e:
                # Log error but don't fail auth for now
                print(f"DEBUG: Error syncing user to local DB: {e}")

    return UUID(user_id)
