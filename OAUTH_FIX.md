# OAuth Callback Fix - URGENT

## Issue Found

The OAuth callback is failing because the `ENCRYPTION_KEY` environment variable in Render is not a valid Fernet encryption key format.

## Solution

You need to set the `ENCRYPTION_KEY` in Render dashboard to a proper Fernet key:

### Steps:

1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click on **moltbot-fastapi** service
3. Go to **Environment** tab
4. Find or add `ENCRYPTION_KEY`
5. Set the value to:
   ```
   vTQUVPgm-GMGwpoIjx90Y08GF1hEoGK8OIObyn-3PUw=
   ```
6. Click **Save Changes**
7. Render will automatically redeploy

## Why This Fixes It

- The Fernet encryption library requires keys in a specific format (32 bytes, base64-encoded)
- Render's `generateValue: true` creates random strings that aren't valid Fernet keys
- When storing OAuth tokens, the app encrypts them using this key
- If the key is invalid, encryption fails and OAuth callback returns CALLBACK_ERROR

## Verify Fix

After redeployment (5 minutes), try the OAuth flow again:

1. Call: `https://moltbot-fastapi.onrender.com/api/v1/oauth/google/init?user_id=123`
2. Visit the returned authorization URL
3. Authorize with your Google account
4. You should be redirected to: `https://peppi.app/clawdbot/oauth?status=success&service=google`

If it still fails, the error code will now be more specific:
- `TOKEN_STORAGE_FAILED` - Database issue
- `TOKEN_STORAGE_ERROR` - Encryption or other error (with details)
- `INVALID_USER_ID` - User ID validation failed

## Next Steps After Fix

Once OAuth works, test calendar features:

```bash
# Check connection status
curl https://moltbot-fastapi.onrender.com/api/v1/oauth/google/status/123

# Test calendar read
curl -X POST https://moltbot-fastapi.onrender.com/api/v1/execute-action \
  -H "Content-Type: application/json" \
  -d '{"user_id": "123", "message": "What is on my calendar today?"}'
```

---

**This is the root cause of the OAuth callback error. Setting the proper ENCRYPTION_KEY will fix it.**
