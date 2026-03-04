# Frontend Integration Guide

This document explains how to connect your frontend application (iOS or Web) to the **Digital Diary Backend**.

## 1. Authentication Overview

The backend uses **Supabase Auth (JWT)** for security. It does **not** handle login/signup itself. Instead, your frontend interacts with Supabase directly, receives a JWT (Access Token), and sends that token to the backend API.

### The Flow
1.  **Frontend**: User logs in via Supabase SDK.
2.  **Supabase**: Returns a session containing an `access_token`.
3.  **Frontend**: Stores this token.
4.  **Frontend**: Makes a request to the Backend (e.g., `POST /api/v1/contacts/`) with header:
    `Authorization: Bearer <your_access_token>`
5.  **Backend**: Validates the token using `SUPABASE_JWT_SECRET` and extracts the `user_id`.

---

## 2. Setup (Web / JavaScript)

If you are building a web app (React, Next.js, Vue), use the official Supabase Client.

### Installation
```bash
yarn add install @supabase/supabase-js axios
```

### Initialization
Create a Supabase client instance using your project credentials (from your Supabase Dashboard).

```javascript
import { createClient } from '@supabase/supabase-js'

const supabaseUrl = 'https://your-project.supabase.co'
const supabaseKey = 'your-anon-key'
const supabase = createClient(supabaseUrl, supabaseKey)
```

### Login & Get Token
```javascript
async function loginAndGetToken() {
  // 1. Sign in (example with Google Auth)
  const { data, error } = await supabase.auth.signInWithPassword({
    email: 'test@example.com',
    password: 'password123',
  })

  if (error) {
    console.error('Login error:', error)
    return null
  }

  // 2. Get the Access Token
  const token = data.session.access_token
  return token
}
```

### Making an API Call
```javascript
import axios from 'axios'

async function createContact(token, contactData) {
  try {
    const response = await axios.post('http://localhost:8000/api/v1/contacts/', contactData, {
      headers: {
        'Authorization': `Bearer ${token}`, // <--- CRITICAL: Pass the token here
        'Content-Type': 'application/json'
      }
    })
    console.log('Contact Created:', response.data)
  } catch (err) {
    console.error('API Error:', err.response?.data || err.message)
  }
}

// Usage
const contact = {
  full_name: "Bruce Wayne",
  primary_title: "CEO",
  primary_org: "Wayne Enterprises",
  dynamic_details: { email: "bruce@wayne.com" }
}

const token = await loginAndGetToken()
if (token) {
  createContact(token, contact)
}
```

---

## 3. Setup (iOS / Swift)

If you are using the Swift Supabase SDK.

### Installation
Add the package `supabase-swift` via Swift Package Manager.

### Implementation
```swift
import Supabase

let client = SupabaseClient(
    supabaseURL: URL(string: "https://your-project.supabase.co")!,
    supabaseKey: "your-anon-key"
)

func performBackendRequest() async {
    do {
        // 1. Get the current session
        guard let session = try? await client.auth.session else {
            print("User not logged in")
            return
        }
        
        let token = session.accessToken
        
        // 2. Prepare the Request
        let url = URL(string: "http://localhost:8000/api/v1/contacts/")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        
        // 3. Add Headers
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body: [String: Any] = [
            "full_name": "Diana Prince",
            "primary_title": "Curator",
            "dynamic_details": ["location": "Paris"]
        ]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        
        // 4. Send
        let (data, response) = try await URLSession.shared.data(for: request)
        
        if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 201 {
            print("Success!", String(data: data, encoding: .utf8) ?? "")
        } else {
            print("Error", String(data: data, encoding: .utf8) ?? "")
        }
        
    } catch {
        print("Network error: \(error)")
    }
}
```

---

## 4. Common Pitfalls

### "Signature verification failed"
-   **Cause**: The backend uses a different `SUPABASE_JWT_SECRET` than the one effectively signing the token (Supabase cloud).
-   **Fix**: Ensure your backend `.env` file has the *exact* JWT Secret from your Supabase Dashboard > Project Settings > API > JWT Settings.

### "401 Unauthorized"
-   **Cause**: Token is missing, expired, or malformed.
-   **Fix**: Log out and log back in on the frontend to get a fresh token. Check that the header format is `Bearer <token>` (note the space).

### "404 Contact Not Found" (Search)
-   **Cause**: You might be logged in as a different user than the one who created the data.
-   **Fix**: The backend strictly scopes data to the `user_id` inside the token. Ensure you are using the same account.
