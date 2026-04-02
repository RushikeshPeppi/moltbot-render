> **BrainSync Context Pumper** 🧠
> Dynamically loaded for active file: `fastapi-wrapper\app\config.py` (Domain: **Generic Logic**)

### 📐 Generic Logic Conventions & Fixes
- **[decision] Optimized Side**: - # ==================== Action Execution ====================
+ # ==================== Side-Effect Detection ====================
- @router.post("/execute-action")
+ async def _detect_side_effects_and_build_fallback(
- async def execute_action(request: ExecuteActionRequest):
+     user_id: str,
-     """
+     session_id: str,
-     Execute action via OpenClaw.
+     pre_call_reminder_ids: set,
-     
+     openclaw_response: dict
-     This is the main endpoint that Peppi calls to process user SMS messages.
+ ) -> Optional[str]:
-     Rate limiting is handled by Peppi (Laravel) before calling this endpoint.
+     """
-     
+     When the gateway returns empty payloads, check if a real side-effect
-     Flow:
+     (e.g., reminder creation, email sent) already happened.
-     1. Acquire user lock (prevent concurrent requests)
+     If so, build a contextual fallback response instead of retrying or erroring.
-     2. Create/get session
+     """
-     3. Get user credentials
+     try:
-     4. Call OpenClaw with retry logic (3 attempts)
+         # 1. Check for newly created reminders
-     5. Store response
+         current_reminders = await db.get_user_reminders(user_id, status='pending')
-     6. Log action
+         current_ids = {r.get('id') for r in current_reminders if r.get('id')}
-     7. Release lock
+         new_reminder_ids = current_ids - pre_call_reminder_ids
-     
+ 
-     Response format:
+         if new_reminder_ids:
-     {
+             # Find the newest reminder to build a contextual response
-         "code": 200,
+             new_reminders = [r for r in current_reminders if r.get('id') in new_reminder_ids]
-         "message": "Action executed successfully",
+             if new_reminders:
-         "data": {
+                 newest = max(new_reminders, key=lambda r: r.get('id', 0))
-             "session_id": "sess_xxx",
+                 trigger_at = newest.get('trigger_at', '')
-       
… [diff truncated]

📌 IDE AST Context: Modified symbols likely include [APIRouter, Request, JSONResponse, BaseModel, Optional]
- **[what-changed] Added session cookies authentication**: - from datetime import datetime
+ from datetime import datetime, timedelta
-         # 6. Call OpenClaw with retry logic (+ retry on empty payloads)
+         # 5. Snapshot reminders count BEFORE gateway call (for side-effect detection)
-         MAX_EMPTY_RETRIES = 2
+         pre_call_reminder_ids = set()
-         clean_response = None
+         try:
-         tokens_used = 0
+             existing_reminders = await db.get_user_reminders(user_id, status='pending')
-         openclaw_response = None
+             pre_call_reminder_ids = {r.get('id') for r in existing_reminders if r.get('id')}
- 
+         except Exception:
-         for attempt in range(1, MAX_EMPTY_RETRIES + 1):
+             pass  # Non-critical — used for dedup detection only
-             try:
+ 
-                 openclaw_response = await openclaw_client.send_message(
+         # 6. Call OpenClaw (single attempt — no empty-payload retries that cause duplicates)
-                     session_id=session_id,
+         clean_response = None
-                     message=request.message,
+         tokens_used = 0
-                     user_id=user_id,
+         input_tokens = 0
-                     timezone=request.timezone,
+         output_tokens = 0
-                     user_credentials=user_credentials,
+         cache_read = 0
-                     # Peppi sends full context; playground has no context so would use Redis history.
+         cache_write = 0
-                     # Gateway ignores the history field anyway, so always send empty.
+         openclaw_response = None
-                     conversation_history=[],
+ 
-                     user_context=user_context
+         try:
-                 )
+             openclaw_response = await openclaw_client.send_message(
-             except OpenClawClientError as e:
+                 session_id=session_id,
-                 logger.error(f"OpenClaw call failed: {e.message} (type: {e.error_type})"
… [diff truncated]

📌 IDE AST Context: Modified symbols likely include [APIRouter, Request, JSONResponse, BaseModel, Optional]
