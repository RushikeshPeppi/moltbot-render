"""
Moltbot Test Scenarios — All 193 scenarios for exhaustive testing.
Each scenario: (id, category, name, message, timezone, image_urls, num_media, verify_type, expected)
"""

API_URL = "https://moltbot-fastapi.onrender.com/api/v1"
USER_ID = "usr_84e773f8"
DEFAULT_TZ = "Asia/Kolkata"
IMG_BASE = "https://raw.githubusercontent.com/RushikeshPeppi/moltbot-render/main/test-images"

# Verification types
V_CAL_READ = "calendar_read"      # Read calendar to verify event
V_REM_LIST = "reminder_list"      # GET /reminders/list to verify
V_EMAIL_READ = "email_inbox"      # Read inbox to verify
V_RESPONSE = "response_only"     # Just check API response is sensible
V_NONE = "none"                   # No verification needed

SCENARIOS = []

# ============================================================
# A. CALENDAR — Create Events (30 scenarios)
# ============================================================
SCENARIOS += [
    {"id": "A1", "cat": "Calendar Create", "name": "Basic event tomorrow",
     "msg": "Schedule a meeting tomorrow at 3pm", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A2", "cat": "Calendar Create", "name": "Event with specific date",
     "msg": "Meeting on April 25 at 10am", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A3", "cat": "Calendar Create", "name": "Event with attendee",
     "msg": "Meeting with rushi9325311775@gmail.com tomorrow at 2pm", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A4", "cat": "Calendar Create", "name": "Event with Google Meet",
     "msg": "Set up a meeting tomorrow at 4pm with Google Meet", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A5", "cat": "Calendar Create", "name": "Event with Meet + attendee",
     "msg": "Meeting with rushi9325311775@gmail.com tomorrow at 11am with Google Meet", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A6", "cat": "Calendar Create", "name": "Event with location",
     "msg": "Meeting at Starbucks Koregaon Park tomorrow at 5pm", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A7", "cat": "Calendar Create", "name": "Event with description",
     "msg": "Meeting tomorrow at 3pm about Q2 budget review", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A8", "cat": "Calendar Create", "name": "Event with duration",
     "msg": "1 hour meeting tomorrow at 2pm", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A9", "cat": "Calendar Create", "name": "Event 30 min duration",
     "msg": "30 minute standup tomorrow at 9am", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A10", "cat": "Calendar Create", "name": "Event 2 hour duration",
     "msg": "2 hour workshop tomorrow at 10am", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A11", "cat": "Calendar Create", "name": "All-day event",
     "msg": "Block my calendar for April 28, full day", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A12", "cat": "Calendar Create", "name": "Event next Monday",
     "msg": "Team sync next Monday at 10am", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A13", "cat": "Calendar Create", "name": "Event this Friday",
     "msg": "Lunch this Friday at 1pm", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A14", "cat": "Calendar Create", "name": "Event today",
     "msg": "Meeting today at 6pm", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A15", "cat": "Calendar Create", "name": "Event in 2 days",
     "msg": "Interview in 2 days at 11am", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A16", "cat": "Calendar Create", "name": "Event next week",
     "msg": "Planning session next week Tuesday at 3pm", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A17", "cat": "Calendar Create", "name": "Multiple attendees",
     "msg": "Meeting with a@test.com and b@test.com tomorrow at 2pm", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A18", "cat": "Calendar Create", "name": "Event crossing midnight",
     "msg": "Party tonight from 10pm to 2am", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A19", "cat": "Calendar Create", "name": "Early morning event",
     "msg": "Meeting tomorrow at 6am", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A20", "cat": "Calendar Create", "name": "Noon event",
     "msg": "Lunch meeting at noon tomorrow", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A21", "cat": "Calendar Create", "name": "Midnight event",
     "msg": "Reminder call at midnight tonight", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A22", "cat": "Calendar Create", "name": "Evening event bare digit",
     "msg": "Dinner at 7 tomorrow", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A23", "cat": "Calendar Create", "name": "Bare digit 3",
     "msg": "Meeting at 3 tomorrow", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A24", "cat": "Calendar Create", "name": "Bare digit 9",
     "msg": "Standup at 9 tomorrow", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A25", "cat": "Calendar Create", "name": "Military time",
     "msg": "Meeting at 1430 tomorrow", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A26", "cat": "Calendar Create", "name": "Dot-separated time",
     "msg": "Call at 3.30 tomorrow", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A27", "cat": "Calendar Create", "name": "Half past time",
     "msg": "Meeting at half past 2 tomorrow", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A28", "cat": "Calendar Create", "name": "Quarter to time",
     "msg": "Call at quarter to 5 tomorrow", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A29", "cat": "Calendar Create", "name": "Date as ordinal",
     "msg": "Meeting on the 25th at 3pm", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "A30", "cat": "Calendar Create", "name": "Hinglish input",
     "msg": "Kal 3 baje meeting rakh do", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
]

# ============================================================
# B. CALENDAR — Read/List (10)
# ============================================================
SCENARIOS += [
    {"id": "B1", "cat": "Calendar Read", "name": "Today's calendar", "msg": "What's on my calendar today?", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "B2", "cat": "Calendar Read", "name": "Tomorrow's events", "msg": "What meetings do I have tomorrow?", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "B3", "cat": "Calendar Read", "name": "This week", "msg": "What's my schedule this week?", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "B4", "cat": "Calendar Read", "name": "Specific date", "msg": "What's on April 25?", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "B5", "cat": "Calendar Read", "name": "Next event", "msg": "What's my next meeting?", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "B6", "cat": "Calendar Read", "name": "Free/busy check", "msg": "Am I free tomorrow at 3pm?", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "B7", "cat": "Calendar Read", "name": "Events with person", "msg": "When is my meeting with rushi9325311775@gmail.com?", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "B8", "cat": "Calendar Read", "name": "Today late night IST", "msg": "What's on my calendar today?", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "B9", "cat": "Calendar Read", "name": "Search by keyword", "msg": "Find my budget meeting", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "B10", "cat": "Calendar Read", "name": "No events day", "msg": "What's on my calendar on Sunday?", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
]

# ============================================================
# C. CALENDAR — Update (10)
# ============================================================
SCENARIOS += [
    {"id": "C1", "cat": "Calendar Update", "name": "Reschedule by time", "msg": "Move my 3pm meeting to 5pm", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "C2", "cat": "Calendar Update", "name": "Reschedule by date", "msg": "Move tomorrow's standup to Thursday", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "C3", "cat": "Calendar Update", "name": "Rename event", "msg": "Rename my 3pm meeting to Budget Review", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "C4", "cat": "Calendar Update", "name": "Add attendee", "msg": "Add bob@test.com to my 3pm meeting", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "C5", "cat": "Calendar Update", "name": "Add Meet to existing", "msg": "Add Google Meet to my 3pm meeting tomorrow", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "C6", "cat": "Calendar Update", "name": "Change duration", "msg": "Extend my 3pm meeting to 2 hours", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "C7", "cat": "Calendar Update", "name": "Add location", "msg": "Add location 'WeWork BKC' to my meeting tomorrow", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "C8", "cat": "Calendar Update", "name": "Change description", "msg": "Update the description of my budget meeting", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "C9", "cat": "Calendar Update", "name": "Move to different day", "msg": "Move my Friday meeting to next Monday", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "C10", "cat": "Calendar Update", "name": "Reschedule across midnight", "msg": "Move my 11pm meeting to 1am", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
]

# ============================================================
# D. CALENDAR — Delete (5)
# ============================================================
SCENARIOS += [
    {"id": "D1", "cat": "Calendar Delete", "name": "Cancel by name", "msg": "Cancel my team standup tomorrow", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "D2", "cat": "Calendar Delete", "name": "Cancel by time", "msg": "Cancel my 3pm meeting", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "D3", "cat": "Calendar Delete", "name": "Cancel tomorrow's events", "msg": "Clear my calendar tomorrow", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "D4", "cat": "Calendar Delete", "name": "Cancel next meeting", "msg": "Cancel my next meeting", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "D5", "cat": "Calendar Delete", "name": "Cancel non-existent", "msg": "Cancel my dentist appointment tomorrow", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
]

# ============================================================
# E. REMINDERS — Create (20)
# ============================================================
SCENARIOS += [
    {"id": "E1", "cat": "Reminder Create", "name": "Basic reminder", "msg": "Remind me to call mom tomorrow at 9am", "tz": DEFAULT_TZ, "verify": V_REM_LIST},
    {"id": "E2", "cat": "Reminder Create", "name": "Relative time", "msg": "Remind me to check oven in 30 minutes", "tz": DEFAULT_TZ, "verify": V_REM_LIST},
    {"id": "E3", "cat": "Reminder Create", "name": "Relative hours", "msg": "Remind me in 2 hours to pick up groceries", "tz": DEFAULT_TZ, "verify": V_REM_LIST},
    {"id": "E4", "cat": "Reminder Create", "name": "Today specific time", "msg": "Remind me at 6pm today to leave office", "tz": DEFAULT_TZ, "verify": V_REM_LIST},
    {"id": "E5", "cat": "Reminder Create", "name": "Daily recurring", "msg": "Remind me to take vitamins every day at 8am", "tz": DEFAULT_TZ, "verify": V_REM_LIST},
    {"id": "E6", "cat": "Reminder Create", "name": "Weekday recurring", "msg": "Remind me on weekdays at 9am to check email", "tz": DEFAULT_TZ, "verify": V_REM_LIST},
    {"id": "E7", "cat": "Reminder Create", "name": "Weekly recurring", "msg": "Remind me every Monday at 10am for standup", "tz": DEFAULT_TZ, "verify": V_REM_LIST},
    {"id": "E8", "cat": "Reminder Create", "name": "Monthly recurring", "msg": "Remind me on the 1st of every month to pay rent", "tz": DEFAULT_TZ, "verify": V_REM_LIST},
    {"id": "E9", "cat": "Reminder Create", "name": "Long message >160", "msg": "Remind me tomorrow at 10am to call the insurance company about the claim from last month and follow up on the status of the reimbursement for the hospital visit", "tz": DEFAULT_TZ, "verify": V_REM_LIST},
    {"id": "E10", "cat": "Reminder Create", "name": "No time specified", "msg": "Remind me to buy milk", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "E11", "cat": "Reminder Create", "name": "Military time", "msg": "Remind me at 1430 to call office", "tz": DEFAULT_TZ, "verify": V_REM_LIST},
    {"id": "E12", "cat": "Reminder Create", "name": "Bare digit 5", "msg": "Remind me at 5 to leave", "tz": DEFAULT_TZ, "verify": V_REM_LIST},
    {"id": "E13", "cat": "Reminder Create", "name": "Bare digit 8", "msg": "Remind me at 8 to wake up", "tz": DEFAULT_TZ, "verify": V_REM_LIST},
    {"id": "E14", "cat": "Reminder Create", "name": "Next week reminder", "msg": "Remind me next Friday at 3pm about the report", "tz": DEFAULT_TZ, "verify": V_REM_LIST},
    {"id": "E15", "cat": "Reminder Create", "name": "Tomorrow no AM/PM", "msg": "Remind me tomorrow at 7 to exercise", "tz": DEFAULT_TZ, "verify": V_REM_LIST},
    {"id": "E16", "cat": "Reminder Create", "name": "Emoji in message", "msg": "Remind me tomorrow at 10am 💊 medicine time", "tz": DEFAULT_TZ, "verify": V_REM_LIST},
    {"id": "E17", "cat": "Reminder Create", "name": "Special chars", "msg": "Remind me at 3pm: John's party @ Dave's place", "tz": DEFAULT_TZ, "verify": V_REM_LIST},
    {"id": "E18", "cat": "Reminder Create", "name": "Reminder tonight", "msg": "Remind me tonight at 9pm to call dad", "tz": DEFAULT_TZ, "verify": V_REM_LIST},
    {"id": "E19", "cat": "Reminder Create", "name": "This evening", "msg": "Remind me this evening to water plants", "tz": DEFAULT_TZ, "verify": V_REM_LIST},
    {"id": "E20", "cat": "Reminder Create", "name": "Past time today", "msg": "Remind me today at 6am to wake up", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
]

# ============================================================
# F. REMINDERS — List/Cancel/Update (8)
# ============================================================
SCENARIOS += [
    {"id": "F1", "cat": "Reminder Manage", "name": "List all", "msg": "Show my reminders", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "F2", "cat": "Reminder Manage", "name": "List pending", "msg": "What reminders do I have?", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "F3", "cat": "Reminder Manage", "name": "Cancel by description", "msg": "Cancel my medicine reminder", "tz": DEFAULT_TZ, "verify": V_REM_LIST},
    {"id": "F4", "cat": "Reminder Manage", "name": "Cancel all", "msg": "Cancel all my reminders", "tz": DEFAULT_TZ, "verify": V_REM_LIST},
    {"id": "F5", "cat": "Reminder Manage", "name": "Update time", "msg": "Change my 9am reminder to 10am", "tz": DEFAULT_TZ, "verify": V_REM_LIST},
    {"id": "F6", "cat": "Reminder Manage", "name": "Update message", "msg": "Change my medicine reminder to 'Take vitamins'", "tz": DEFAULT_TZ, "verify": V_REM_LIST},
    {"id": "F7", "cat": "Reminder Manage", "name": "Cancel non-existent", "msg": "Cancel my gym reminder", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "F8", "cat": "Reminder Manage", "name": "List when empty", "msg": "Show my reminders", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
]

# ============================================================
# G. EMAIL — Send (10)
# ============================================================
SCENARIOS += [
    {"id": "G1", "cat": "Email Send", "name": "Basic email", "msg": "Send an email to rushi9325311775@gmail.com saying hi there", "tz": DEFAULT_TZ, "verify": V_EMAIL_READ},
    {"id": "G2", "cat": "Email Send", "name": "Email with subject", "msg": "Email rushi9325311775@gmail.com subject: Test, body: This is a test", "tz": DEFAULT_TZ, "verify": V_EMAIL_READ},
    {"id": "G3", "cat": "Email Send", "name": "Professional email", "msg": "Send a professional email to rushi9325311775@gmail.com about project update", "tz": DEFAULT_TZ, "verify": V_EMAIL_READ},
    {"id": "G4", "cat": "Email Send", "name": "Short email", "msg": "Email rushi9325311775@gmail.com: I'll be late", "tz": DEFAULT_TZ, "verify": V_EMAIL_READ},
    {"id": "G5", "cat": "Email Send", "name": "Email with formatting", "msg": "Send email to rushi9325311775@gmail.com with bullet points: item 1, item 2, item 3", "tz": DEFAULT_TZ, "verify": V_EMAIL_READ},
    {"id": "G6", "cat": "Email Send", "name": "Reply context", "msg": "Reply to the last email from rushi9325311775@gmail.com saying thanks", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "G7", "cat": "Email Send", "name": "Invalid email", "msg": "Send email to notanemailaddress", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "G8", "cat": "Email Send", "name": "Long body email", "msg": "Send detailed project report email to rushi9325311775@gmail.com about quarterly budget review and team performance metrics", "tz": DEFAULT_TZ, "verify": V_EMAIL_READ},
    {"id": "G9", "cat": "Email Send", "name": "Email to self", "msg": "Send email to rushi9325311775@gmail.com saying test from Moltbot", "tz": DEFAULT_TZ, "verify": V_EMAIL_READ},
    {"id": "G10", "cat": "Email Send", "name": "Email with CC", "msg": "Email rushi9325311775@gmail.com, cc rushi9325311775@gmail.com about meeting", "tz": DEFAULT_TZ, "verify": V_EMAIL_READ},
]

# ============================================================
# H. EMAIL — Read (8)
# ============================================================
SCENARIOS += [
    {"id": "H1", "cat": "Email Read", "name": "Check inbox", "msg": "Check my inbox", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "H2", "cat": "Email Read", "name": "Unread only", "msg": "Show unread emails", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "H3", "cat": "Email Read", "name": "From specific person", "msg": "Any emails from rushi9325311775@gmail.com?", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "H4", "cat": "Email Read", "name": "Search by subject", "msg": "Find emails about project update", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "H5", "cat": "Email Read", "name": "Latest email", "msg": "What's my latest email?", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "H6", "cat": "Email Read", "name": "Count unread", "msg": "How many unread emails do I have?", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "H7", "cat": "Email Read", "name": "Read specific", "msg": "Read the email from Google", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "H8", "cat": "Email Read", "name": "Empty inbox search", "msg": "Any emails from nonexistent@nowhere.com?", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
]

# ============================================================
# I. IMAGE SCENARIOS (15)
# ============================================================
SCENARIOS += [
    {"id": "I1", "cat": "Image", "name": "Event poster → calendar", "msg": "Add this to my calendar", "tz": DEFAULT_TZ, "verify": V_CAL_READ,
     "image_urls": [f"{IMG_BASE}/event_poster.png"], "num_media": 1},
    {"id": "I2", "cat": "Image", "name": "Bill → reminder", "msg": "Remind me to pay this", "tz": DEFAULT_TZ, "verify": V_REM_LIST,
     "image_urls": [f"{IMG_BASE}/utility_bill.png"], "num_media": 1},
    {"id": "I3", "cat": "Image", "name": "Receipt → email", "msg": "Send this to rushi9325311775@gmail.com", "tz": DEFAULT_TZ, "verify": V_EMAIL_READ,
     "image_urls": [f"{IMG_BASE}/restaurant_receipt.png"], "num_media": 1},
    {"id": "I4", "cat": "Image", "name": "Shopping list → reminder", "msg": "Remind me about this tomorrow", "tz": DEFAULT_TZ, "verify": V_REM_LIST,
     "image_urls": [f"{IMG_BASE}/shopping_list.png"], "num_media": 1},
    {"id": "I5", "cat": "Image", "name": "Class schedule → reminders", "msg": "Set reminders for all these classes", "tz": DEFAULT_TZ, "verify": V_REM_LIST,
     "image_urls": [f"{IMG_BASE}/class_schedule.png"], "num_media": 1},
    {"id": "I6", "cat": "Image", "name": "Chat screenshot → reminder", "msg": "Remind me about this", "tz": DEFAULT_TZ, "verify": V_REM_LIST,
     "image_urls": [f"{IMG_BASE}/chat_screenshot.png"], "num_media": 1},
    {"id": "I7", "cat": "Image", "name": "Meeting invite → calendar", "msg": "Add this meeting", "tz": DEFAULT_TZ, "verify": V_CAL_READ,
     "image_urls": [f"{IMG_BASE}/meeting_invite.png"], "num_media": 1},
    {"id": "I8", "cat": "Image", "name": "Image only no text", "msg": "", "tz": DEFAULT_TZ, "verify": V_RESPONSE,
     "image_urls": [f"{IMG_BASE}/whiteboard_notes.png"], "num_media": 1},
    {"id": "I9", "cat": "Image", "name": "Blurry image", "msg": "Add this to my calendar", "tz": DEFAULT_TZ, "verify": V_RESPONSE,
     "image_urls": [f"{IMG_BASE}/blurry_image.png"], "num_media": 1},
    {"id": "I10", "cat": "Image", "name": "Multiple images", "msg": "Add all these", "tz": DEFAULT_TZ, "verify": V_CAL_READ,
     "image_urls": [f"{IMG_BASE}/event_poster.png", f"{IMG_BASE}/meeting_invite.png"], "num_media": 2},
    {"id": "I11", "cat": "Image", "name": "Prescription → reminder", "msg": "Remind me to refill this", "tz": DEFAULT_TZ, "verify": V_REM_LIST,
     "image_urls": [f"{IMG_BASE}/prescription.png"], "num_media": 1},
    {"id": "I12", "cat": "Image", "name": "Whiteboard → email", "msg": "Email this to rushi9325311775@gmail.com", "tz": DEFAULT_TZ, "verify": V_EMAIL_READ,
     "image_urls": [f"{IMG_BASE}/whiteboard_notes.png"], "num_media": 1},
    {"id": "I13", "cat": "Image", "name": "Invoice → calendar", "msg": "When is this due?", "tz": DEFAULT_TZ, "verify": V_RESPONSE,
     "image_urls": [f"{IMG_BASE}/invoice.png"], "num_media": 1},
    {"id": "I14", "cat": "Image", "name": "Image + specific time", "msg": "Remind me about this on Monday at 9am", "tz": DEFAULT_TZ, "verify": V_REM_LIST,
     "image_urls": [f"{IMG_BASE}/whiteboard_notes.png"], "num_media": 1},
    {"id": "I15", "cat": "Image", "name": "Image + no time", "msg": "Remind me about this", "tz": DEFAULT_TZ, "verify": V_RESPONSE,
     "image_urls": [f"{IMG_BASE}/shopping_list.png"], "num_media": 1},
]

# ============================================================
# J. TIMEZONE — General & IST (15)
# ============================================================
SCENARIOS += [
    {"id": "J1", "cat": "TZ General", "name": "IST standard", "msg": "Meeting tomorrow at 3pm", "tz": "Asia/Kolkata", "verify": V_CAL_READ},
    {"id": "J2", "cat": "TZ General", "name": "IST near midnight", "msg": "Meeting tomorrow at 9am", "tz": "Asia/Kolkata", "verify": V_CAL_READ},
    {"id": "J3", "cat": "TZ General", "name": "IST today at 11pm", "msg": "What's on my calendar today?", "tz": "Asia/Kolkata", "verify": V_RESPONSE},
    {"id": "J4", "cat": "TZ General", "name": "Reminder across IST midnight", "msg": "Remind me at 12:30am tomorrow", "tz": "Asia/Kolkata", "verify": V_REM_LIST},
    {"id": "J5", "cat": "TZ General", "name": "Half-hour offset", "msg": "Meeting at 3pm tomorrow", "tz": "Asia/Kolkata", "verify": V_CAL_READ},
    {"id": "J6", "cat": "TZ General", "name": "Nepal +5:45", "msg": "Meeting at 3pm tomorrow", "tz": "Asia/Kathmandu", "verify": V_CAL_READ},
    {"id": "J7", "cat": "TZ General", "name": "Reminder relative IST", "msg": "Remind me in 30 minutes", "tz": "Asia/Kolkata", "verify": V_REM_LIST},
    {"id": "J8", "cat": "TZ General", "name": "UTC", "msg": "Meeting tomorrow at 3pm", "tz": "UTC", "verify": V_CAL_READ},
    {"id": "J9", "cat": "TZ General", "name": "Japan", "msg": "Meeting tomorrow at 3pm", "tz": "Asia/Tokyo", "verify": V_CAL_READ},
    {"id": "J10", "cat": "TZ General", "name": "UK BST", "msg": "Meeting tomorrow at 3pm", "tz": "Europe/London", "verify": V_CAL_READ},
    {"id": "J11", "cat": "TZ General", "name": "Australia", "msg": "Meeting tomorrow at 3pm", "tz": "Australia/Sydney", "verify": V_CAL_READ},
    {"id": "J12", "cat": "TZ General", "name": "Date line crossing", "msg": "Meeting tomorrow at 10am", "tz": "Pacific/Auckland", "verify": V_CAL_READ},
    {"id": "J13", "cat": "TZ General", "name": "Dubai", "msg": "Meeting at 3pm tomorrow", "tz": "Asia/Dubai", "verify": V_CAL_READ},
    {"id": "J14", "cat": "TZ General", "name": "Singapore", "msg": "Meeting at 3pm tomorrow", "tz": "Asia/Singapore", "verify": V_CAL_READ},
    {"id": "J15", "cat": "TZ General", "name": "Germany CEST", "msg": "Meeting at 3pm tomorrow", "tz": "Europe/Berlin", "verify": V_CAL_READ},
]

# ============================================================
# JN. TIMEZONE — America/New_York (20)
# ============================================================
SCENARIOS += [
    {"id": "JN1", "cat": "TZ New York", "name": "Basic event", "msg": "Meeting tomorrow at 3pm", "tz": "America/New_York", "verify": V_CAL_READ},
    {"id": "JN2", "cat": "TZ New York", "name": "Morning event", "msg": "Standup tomorrow at 9am", "tz": "America/New_York", "verify": V_CAL_READ},
    {"id": "JN3", "cat": "TZ New York", "name": "Bare digit 3", "msg": "Meeting at 3 tomorrow", "tz": "America/New_York", "verify": V_CAL_READ},
    {"id": "JN4", "cat": "TZ New York", "name": "Bare digit 8", "msg": "Call at 8 tomorrow", "tz": "America/New_York", "verify": V_CAL_READ},
    {"id": "JN5", "cat": "TZ New York", "name": "Military time", "msg": "Meeting at 1400 tomorrow", "tz": "America/New_York", "verify": V_CAL_READ},
    {"id": "JN6", "cat": "TZ New York", "name": "Midnight crossing", "msg": "Party from 10pm to 2am", "tz": "America/New_York", "verify": V_CAL_READ},
    {"id": "JN7", "cat": "TZ New York", "name": "Reminder at noon", "msg": "Remind me at noon to eat lunch", "tz": "America/New_York", "verify": V_REM_LIST},
    {"id": "JN8", "cat": "TZ New York", "name": "Reminder at midnight", "msg": "Remind me at midnight", "tz": "America/New_York", "verify": V_REM_LIST},
    {"id": "JN9", "cat": "TZ New York", "name": "Reminder in 30 min", "msg": "Remind me in 30 minutes to call", "tz": "America/New_York", "verify": V_REM_LIST},
    {"id": "JN10", "cat": "TZ New York", "name": "Daily recurring NY", "msg": "Remind me every day at 7am to exercise", "tz": "America/New_York", "verify": V_REM_LIST},
    {"id": "JN11", "cat": "TZ New York", "name": "Weekday recurring NY", "msg": "Remind me weekdays at 8:30am", "tz": "America/New_York", "verify": V_REM_LIST},
    {"id": "JN12", "cat": "TZ New York", "name": "Calendar today NY", "msg": "What's on my calendar today?", "tz": "America/New_York", "verify": V_RESPONSE},
    {"id": "JN13", "cat": "TZ New York", "name": "Calendar tomorrow NY", "msg": "What meetings tomorrow?", "tz": "America/New_York", "verify": V_RESPONSE},
    {"id": "JN14", "cat": "TZ New York", "name": "Event near NY midnight", "msg": "Meeting at 11:45pm tonight", "tz": "America/New_York", "verify": V_CAL_READ},
    {"id": "JN15", "cat": "TZ New York", "name": "Event 12:30am NY", "msg": "Remind me at 12:30am tomorrow", "tz": "America/New_York", "verify": V_REM_LIST},
    {"id": "JN16", "cat": "TZ New York", "name": "Event + attendee NY", "msg": "Meeting with rushi9325311775@gmail.com at 2pm tomorrow", "tz": "America/New_York", "verify": V_CAL_READ},
    {"id": "JN17", "cat": "TZ New York", "name": "Event + Meet NY", "msg": "Set up a meeting with Google Meet at 10am tomorrow", "tz": "America/New_York", "verify": V_CAL_READ},
    {"id": "JN18", "cat": "TZ New York", "name": "Email from NY", "msg": "Send email to rushi9325311775@gmail.com saying hello", "tz": "America/New_York", "verify": V_EMAIL_READ},
    {"id": "JN19", "cat": "TZ New York", "name": "This afternoon NY", "msg": "Meeting this afternoon", "tz": "America/New_York", "verify": V_RESPONSE},
    {"id": "JN20", "cat": "TZ New York", "name": "Late night query NY", "msg": "What's on my calendar today?", "tz": "America/New_York", "verify": V_RESPONSE},
]

# ============================================================
# JUS. TIMEZONE — Other US (15)
# ============================================================
SCENARIOS += [
    {"id": "JUS1", "cat": "TZ US Other", "name": "LA basic", "msg": "Meeting tomorrow at 3pm", "tz": "America/Los_Angeles", "verify": V_CAL_READ},
    {"id": "JUS2", "cat": "TZ US Other", "name": "LA midnight crossing", "msg": "Party from 11pm to 1am", "tz": "America/Los_Angeles", "verify": V_CAL_READ},
    {"id": "JUS3", "cat": "TZ US Other", "name": "LA reminder", "msg": "Remind me at 9am tomorrow", "tz": "America/Los_Angeles", "verify": V_REM_LIST},
    {"id": "JUS4", "cat": "TZ US Other", "name": "LA daily recurring", "msg": "Remind me every day at 6am", "tz": "America/Los_Angeles", "verify": V_REM_LIST},
    {"id": "JUS5", "cat": "TZ US Other", "name": "LA calendar check", "msg": "What's on my calendar today?", "tz": "America/Los_Angeles", "verify": V_RESPONSE},
    {"id": "JUS6", "cat": "TZ US Other", "name": "Chicago basic", "msg": "Meeting tomorrow at 3pm", "tz": "America/Chicago", "verify": V_CAL_READ},
    {"id": "JUS7", "cat": "TZ US Other", "name": "Chicago midnight", "msg": "Remind me at 12:30am tomorrow", "tz": "America/Chicago", "verify": V_REM_LIST},
    {"id": "JUS8", "cat": "TZ US Other", "name": "Chicago recurring", "msg": "Remind me weekdays at 7am", "tz": "America/Chicago", "verify": V_REM_LIST},
    {"id": "JUS9", "cat": "TZ US Other", "name": "Denver/Mountain", "msg": "Meeting tomorrow at 3pm", "tz": "America/Denver", "verify": V_CAL_READ},
    {"id": "JUS10", "cat": "TZ US Other", "name": "Denver reminder", "msg": "Remind me at 5pm to leave", "tz": "America/Denver", "verify": V_REM_LIST},
    {"id": "JUS11", "cat": "TZ US Other", "name": "Phoenix no DST", "msg": "Meeting tomorrow at 3pm", "tz": "America/Phoenix", "verify": V_CAL_READ},
    {"id": "JUS12", "cat": "TZ US Other", "name": "Hawaii", "msg": "Meeting tomorrow at 10am", "tz": "Pacific/Honolulu", "verify": V_CAL_READ},
    {"id": "JUS13", "cat": "TZ US Other", "name": "Alaska", "msg": "Meeting tomorrow at 2pm", "tz": "America/Anchorage", "verify": V_CAL_READ},
    {"id": "JUS14", "cat": "TZ US Other", "name": "LA late night", "msg": "What's on today?", "tz": "America/Los_Angeles", "verify": V_RESPONSE},
    {"id": "JUS15", "cat": "TZ US Other", "name": "Chicago + Meet", "msg": "Meeting with Google Meet at 9am tomorrow", "tz": "America/Chicago", "verify": V_CAL_READ},
]

# ============================================================
# K. AMBIGUOUS & NATURAL LANGUAGE (12)
# ============================================================
SCENARIOS += [
    {"id": "K1", "cat": "Ambiguous", "name": "No time given", "msg": "Schedule a meeting tomorrow", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "K2", "cat": "Ambiguous", "name": "No date given", "msg": "Schedule a meeting at 3pm", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "K3", "cat": "Ambiguous", "name": "Morning", "msg": "Meeting tomorrow morning", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "K4", "cat": "Ambiguous", "name": "Afternoon", "msg": "Meeting tomorrow afternoon", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "K5", "cat": "Ambiguous", "name": "Evening", "msg": "Dinner tomorrow evening", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "K6", "cat": "Ambiguous", "name": "End of day", "msg": "Remind me end of day", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "K7", "cat": "Ambiguous", "name": "Two events one msg", "msg": "Meeting at 3pm and another at 5pm tomorrow", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "K8", "cat": "Ambiguous", "name": "Correction follow-up", "msg": "Actually make it 4pm", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "K9", "cat": "Ambiguous", "name": "Vague request", "msg": "Can you do something with my calendar?", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "K10", "cat": "Ambiguous", "name": "Past date", "msg": "Schedule meeting yesterday at 3pm", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "K11", "cat": "Ambiguous", "name": "Far future", "msg": "Meeting on December 25, 2030 at 3pm", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "K12", "cat": "Ambiguous", "name": "Later today", "msg": "Remind me later today", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
]

# ============================================================
# L. CHAT / NON-ACTION (5)
# ============================================================
SCENARIOS += [
    {"id": "L1", "cat": "Chat", "name": "General question", "msg": "What's the capital of France?", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "L2", "cat": "Chat", "name": "Math", "msg": "What's 15% of 2500?", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "L3", "cat": "Chat", "name": "Greeting", "msg": "Hey, how are you?", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "L4", "cat": "Chat", "name": "Thank you", "msg": "Thanks for your help!", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "L5", "cat": "Chat", "name": "What can you do", "msg": "What can you help me with?", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
]

# ============================================================
# M. ERROR & EDGE CASES (10)
# ============================================================
SCENARIOS += [
    {"id": "M1", "cat": "Edge Case", "name": "Empty message", "msg": "", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "M2", "cat": "Edge Case", "name": "Very long message", "msg": "Schedule a meeting " * 100, "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "M3", "cat": "Edge Case", "name": "SQL injection", "msg": "'; DROP TABLE users; --", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "M4", "cat": "Edge Case", "name": "Script injection", "msg": "<script>alert('xss')</script>", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "M5", "cat": "Edge Case", "name": "Unicode/emoji heavy", "msg": "📅 Schedule 🎉 party 🕐 at 3pm 🏠 tomorrow", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "M6", "cat": "Edge Case", "name": "All caps", "msg": "SCHEDULE A MEETING TOMORROW AT 3PM", "tz": DEFAULT_TZ, "verify": V_CAL_READ},
    {"id": "M7", "cat": "Edge Case", "name": "No Google connected", "msg": "Schedule a meeting tomorrow at 3pm", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "M8", "cat": "Edge Case", "name": "Calendar + reminder combo", "msg": "Schedule a meeting at 3pm and remind me 30 min before", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "M9", "cat": "Edge Case", "name": "Contradictory request", "msg": "Schedule a meeting tomorrow at 3pm and 5pm", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
    {"id": "M10", "cat": "Edge Case", "name": "French language", "msg": "Demain à 15h réunion", "tz": DEFAULT_TZ, "verify": V_RESPONSE},
]
