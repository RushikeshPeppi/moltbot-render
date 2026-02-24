# How to Test Moltbot Skills - Simple Guide

## 📋 Test File
Open this file: **`all-skills-test-cases.csv`**

You can open it in Excel, Google Sheets, or any spreadsheet app.

---

## 🎯 What's Covered

This test sheet covers **3 main skills**:
- **Gmail** (15 tests) - Check inbox, send emails, reply, search
- **Calendar** (15 tests) - Create meetings, update times, list events
- **Reminders** (20 tests) - Set reminders, update, cancel, recurring

**Total: 50 test cases**

---

## 🚀 How to Run Tests

### Step 1: Open the CSV
- Open `all-skills-test-cases.csv` in Excel or Google Sheets
- You'll see 50 test cases covering all skills

### Step 2: Pick a Test
Each row is one test. Example:

| Test ID | Skill Used | Test Case Description |
|---------|-----------|----------------------|
| GMAIL-001 | google-workspace | Send: "check my inbox" |

### Step 3: Do the Test
1. Go to the playground (chat interface)
2. Type exactly what it says in "Test Case Description"
3. Press send

### Step 4: Check the Result
- Look at "Expected Output" column
- Does the AI response match?
  - ✅ **Pass** → Write "Pass" in "Tester Review" column
  - ❌ **Fail** → Write "Fail" in "Tester Review" column + add note

### Step 5: Write What Actually Happened
- In "Actual Output" column, copy-paste the AI's actual response
- This helps track what went wrong if test failed

---

## 📝 Example Test Run

**Test ID:** GMAIL-001

**What to do:** Type this in chat → `check my inbox`

**What should happen:** AI shows → `List of recent emails with sender, subject, and date`

**If it works:**
- Actual Output: (paste the email list AI showed)
- Tester Review: Pass

**If it fails:**
- Actual Output: (paste what AI actually said)
- Tester Review: Fail
- Notes: "Couldn't access inbox, got error"

---

## 🎨 Test Types

### Gmail Tests (GMAIL-001 to GMAIL-015)
- **What they test:** Reading inbox, searching emails, replying, sending, marking as read
- **Pre-requisite:** User must have connected their Google account
- **Time per test:** 10-30 seconds

### Calendar Tests (CAL-001 to CAL-015)
- **What they test:** Creating meetings, updating times, listing events, inviting people
- **Pre-requisite:** User must have connected their Google account
- **Key feature:** Tests smart search + update (NOT cancel + recreate)
- **Time per test:** 20-40 seconds

### Reminder Tests (REM-001 to REM-020)
- **What they test:** Creating reminders, recurring reminders, updating times, cancelling
- **Pre-requisite:** None (works without Google account)
- **Key feature:** Tests timezone handling and smart search
- **Time per test:** 10-30 seconds

---

## 👥 Multi-User Tests

Some tests need 2 users to verify data isolation:

**Gmail:**
- GMAIL-011: Each user should see only their own emails

**Calendar:**
- CAL-012: Each user should see only their own calendar events

**Reminders:**
- REM-011: User isolation for reminders list
- REM-012: User cannot cancel another user's reminder

**How to test:**
1. Open 2 browser windows (or 2 incognito tabs)
2. Login as different users in each window
3. Follow the test instructions
4. Verify users can't see/modify each other's data

---

## ⏰ What to Test First

### Quick Smoke Test (15 minutes)
Test these 15 to verify basic functionality:
- **Gmail:** GMAIL-001, GMAIL-002, GMAIL-004, GMAIL-005, GMAIL-011
- **Calendar:** CAL-001, CAL-002, CAL-003, CAL-012, CAL-013
- **Reminders:** REM-001, REM-003, REM-005, REM-006, REM-011

If these pass, core features are working.

### Important Tests (45 minutes)
Test first 30 cases (10 per skill):
- GMAIL-001 to GMAIL-010
- CAL-001 to CAL-010
- REM-001 to REM-010

### Full Test (2 hours)
Test all 50 cases for complete coverage.

---

## ✅ When is it Ready?

**Ready for release when:**
1. At least 45 out of 50 tests pass (90%)
2. All multi-user tests pass (data isolation)
3. All "update" tests use UPDATE endpoint (not cancel + recreate)
4. Timezone tests pass (times shown in local timezone)
5. No critical bugs (data leaks, crashes, wrong times)

---

## 🐛 If You Find a Bug

In the CSV, write this in the row:
- **Actual Output:** (what AI actually said)
- **Tester Review:** Fail
- **Notes:** Short description of the problem

Example:
```
Test ID: CAL-003
Actual Output: Created new meeting instead of updating existing one
Tester Review: Fail
Notes: AI cancelled old meeting and created new one (should UPDATE)
```

---

## 🎓 Understanding Each Skill

### Gmail Skill (google-workspace)
**What it does:**
- Read inbox
- Search emails by sender, subject, content, date
- Reply to emails
- Send new emails
- Forward emails
- Mark as read/unread

**Key tests:**
- GMAIL-001: Basic inbox check
- GMAIL-002: Search by sender
- GMAIL-004: Reply to email
- GMAIL-011: Multi-user isolation

**Common issues:**
- User not connected to Google account
- Permission errors
- Can't find specific email

### Calendar Skill (google-workspace)
**What it does:**
- List calendar events
- Create meetings with attendees
- Update meeting times using SMART SEARCH
- Cancel meetings
- Add/remove attendees

**Key tests:**
- CAL-002: Create meeting
- CAL-003: Update time (must UPDATE, not recreate)
- CAL-004: Smart search by meeting title
- CAL-010: Disambiguation when multiple matches

**Common issues:**
- Creates new event instead of updating (CRITICAL BUG)
- Wrong timezone (shows UTC instead of IST)
- Can't find event to update

### Reminders Skill (reminders)
**What it does:**
- Create one-time reminders
- Create recurring reminders (daily, weekly, monthly)
- List all reminders
- Update reminder time using SMART SEARCH
- Cancel reminders
- Fire reminders via QStash → SMS

**Key tests:**
- REM-001: Basic reminder creation
- REM-006: Update time (must UPDATE, not recreate)
- REM-011: Multi-user isolation
- REM-013: Timezone accuracy

**Common issues:**
- Wrong timezone (fires at UTC instead of local time)
- Creates new reminder instead of updating (CRITICAL BUG)
- User can see another user's reminders (SECURITY BUG)

---

## 💡 Testing Tips

1. **Test in order** - Go from GMAIL-001 → GMAIL-015 → CAL-001 → CAL-015 → REM-001 → REM-020
2. **One at a time** - Don't rush, verify each result carefully
3. **Copy exact text** - Type exactly what the test says
4. **Check outputs** - Look for:
   - Correct data returned
   - Proper timezone (2pm not 14:00, not UTC)
   - Clean messages (no technical IDs shown)
   - No errors
5. **Watch for patterns** - If one test fails, similar tests might also fail

---

## 📊 Track Your Progress

Add this at the bottom of your CSV:

```
Tests Completed: X/50
Gmail: X/15 passed
Calendar: X/15 passed
Reminders: X/20 passed
Overall Pass Rate: X%
```

---

## 🔍 Critical Tests (Must Pass)

These tests MUST pass or the feature is broken:

**Gmail:**
- GMAIL-001 (check inbox)
- GMAIL-005 (send email)
- GMAIL-011 (user isolation)

**Calendar:**
- CAL-002 (create meeting)
- CAL-003 (update uses UPDATE not recreate)
- CAL-012 (user isolation)
- CAL-013 (timezone accuracy)

**Reminders:**
- REM-001 (create reminder)
- REM-006 (update uses UPDATE not recreate)
- REM-011 (user isolation)
- REM-013 (timezone accuracy)

If any of these fail → STOP and report to dev team immediately.

---

## ❓ FAQs

**Q: Do I need a Google account?**
A: Yes, for Gmail and Calendar tests. Reminders work without Google account.

**Q: How do I connect my Google account?**
A: In the playground, there should be a "Connect Google" button or similar option.

**Q: What if a test says "User 1" and "User 2"?**
A: Open 2 browser windows with different test accounts to verify data isolation.

**Q: Some tests say "Type X, then Type Y" - do I need 2 messages?**
A: Yes, first message creates something, second message tests updating/cancelling it.

**Q: What's the difference between "update" and "cancel + recreate"?**
A:
- **Update (CORRECT):** Modifies existing item, same ID, clean
- **Cancel + Recreate (WRONG):** Deletes old, creates new, messy database

**Q: How do I know if AI used UPDATE vs cancel+recreate?**
A: Check the response:
- ✅ Good: "Reminder updated to 3pm"
- ❌ Bad: "Reminder #29 cancelled. Now creating new reminder..."

**Q: What timezone should times be in?**
A: Always in the user's local timezone (e.g., IST). NEVER UTC in user-facing messages.

---

## 📞 Need Help?

**If a test is unclear:** Ask your QA lead
**If you find a bug:** Report with test ID to dev team
**If account issues:** Ask your manager for test credentials

---

## 🎉 Success Criteria

**Feature is READY when:**
- ✅ 90%+ pass rate (45+ out of 50 tests pass)
- ✅ All critical tests pass
- ✅ All multi-user tests pass (data isolation)
- ✅ All update tests use UPDATE endpoint (not cancel + recreate)
- ✅ All timezone tests pass
- ✅ No P0/P1 bugs remain

---

**Happy Testing!** 🚀

Test the features, report issues clearly, and help make Moltbot awesome!
