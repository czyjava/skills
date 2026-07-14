---
name: homeai-sms-login
description: Use when Codex needs to log into the HomeAI/装修 APP Android APK during APK-H5 comparison or automation runs using SMS verification, including triggering the APP login flow, querying the admin SMS send-record page in Chrome, polling for delayed verification codes, and safely filling the code back into the emulator without leaking secrets.
---

# HomeAI SMS Login

## Purpose

Use this skill to establish a logged-in state for the HomeAI/装修 APP on an Android emulator when the APP only exposes手机号验证码登录. The reliable path is: trigger SMS in APP, query the admin SMS send-record page, poll until the record appears, then fill the code back into APP.

## Preconditions

- Prefer the known stable emulator from automation memory: `codex_pixel_30`, device `emulator-5554`.
- The HomeAI APK should already be installed and privacy terms accepted.
- Chrome must have an authenticated admin session. Use the Chrome skill/plugin for the admin page because it relies on the user's logged-in browser state.
- Admin SMS records page:
  `https://admin.wanmeixiangsu.cn/auth.wanmeixiangsu.cn/#header=auth!main%2Faside1&aside=auth!app%2Fsms-send-record%2Findex%2Flist`

## APP Flow

1. Open the APP and go to `我的`.
2. Tap `点击登录`.
3. Enter the test phone number.
4. Check the user agreement/privacy checkbox.
5. Tap `验证码登录`.
6. If a slider verification appears, solve it visually. Avoid brute forcing repeatedly; one or two reasonable attempts is enough.
7. Confirm the APP reaches the 6-digit verification-code input page.

Record the trigger time locally for matching the backend record. Do not log the full phone number unless the user explicitly provided it in the thread and it is necessary for reproducibility.

## Query SMS Code

Use Chrome automation against the admin SMS records page:

1. Open or claim the existing SMS records tab.
2. Search by the test phone number in the page's search box.
3. Match the newest row that satisfies all conditions:
   - phone number matches the test account, usually masked in the table
   - application is `homeai`
   - platform is `android`
   - send status is successful
   - creation time is later than the APP trigger time
4. Extract the 6-digit code from the message content.

Security rule: the verification code is sensitive enough for automation. Use it only to fill the APP; do not include the code in final answers, memory, reports, commit messages, screenshots annotations, or logs.

## Polling Strategy

The SMS record is not always visible immediately.

- Poll for up to 3 minutes after triggering SMS.
- Search/refresh every 10-15 seconds.
- Treat a single empty result as "not ready yet", not as failure.
- If no matching record appears within 3 minutes, return to APP, tap `重新发送验证码`, then start a fresh 3-minute polling window.
- If repeated 3-minute windows fail, report a blocker with exact non-sensitive evidence: APP state, backend query conditions, and last checked time.

## Fill And Verify

1. Fill the 6-digit code into the APP verification-code boxes.
2. Tap `登录`.
3. Successful login commonly lands on a new-user profile page such as `更换个性化的头像和昵称`; this is sufficient proof that the login succeeded.
4. If needed, tap `跳过` and verify `我的` tab no longer shows `点击登录`.

## Sensitive Data Rules

- Never print tokens, cookies, passwords, SMS codes, full credential URLs, or identity documents.
- If a command must contain a phone number or code, keep it in a short-lived shell variable and do not echo it.
- Final summaries should say "已获取并回填验证码" rather than showing the code.
- Screenshots may display masked phone numbers or UI state; avoid screenshots that expose full secrets unless necessary and user-approved.

## Failure Notes

- `account.nav.wanmeixiangsu.cn` login QR URLs are not normal Android APP Links in this environment; prefer the SMS flow above.
- The backend SMS page can briefly show no rows before the record arrives. Always apply the 3-minute polling rule.
- If Chrome automation is unavailable, state that the blocker is the missing authenticated admin browser session rather than attempting to inspect cookies or browser profile storage.
