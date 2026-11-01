# אתר הקרנפים / ברקן — תיק אבטחה ובדיקת מצב
**תאריך:** 1 בנובמבר 2026  
**נכס:** https://karnafim-community-46.onrender.com/  
**אופי:** אתר קהילת ותיקים עצמאי, לא שירות רשמי של צה"ל.

## עובדות שנבדקו מתוך מערכות הפרויקט

- Render אישר מצב `Live` לגרסת התחזוקה, שהושארה פעילה בעקבות מסך האזהרה של Google Chrome.
- /find, /archive, /memorials, /photos ועמודי מקור/הנצחה ציבוריים מחזירים HTTP 200.
- /login, /register, /new-post, /chats ונתיבים אישיים חסומים בזמן `KARNAFIM_MAINTENANCE=1` ומחזירים HTTP 503.
- פלט בסיס הנתונים בעת הבדיקה: חשבון חבר אחד; 0 סיפורים, 0 קובצי חברים, 0 הודעות. אין להסיק מכך שלא קיימות חולשות תוכנה או רישומי גישה אחרים.
- בבדיקת קובצי Flask והתצוגה הציבורית לא התגלו תגיות script שמורידות קוד חיצוני, iframe חיצוני, פקודות JavaScript eval, או טפסים שמגישים מידע ישירות לדומיין זר.
- מצב התחזוקה מציב `Content-Security-Policy`, `X-Content-Type-Options: nosniff` ו-`Cache-Control: no-store`. ה-CSP במצב התחזוקה חוסם סקריפטים ומגביל תמונות ל-Wikimedia.
- קוד התוכן כולל הצהרה שהיוזמה עצמאית; לא מתבצע אימות חברים מול צה"ל.

**חשוב:** בדיקות אלה אינן סריקת חדירה, אינן אישור של Google, ואינן מוכיחות שהאתר בטוח לפרסום פרטים אישיים.

## מה טרם אומת

1. האם Google סיווגה את האתר כ-Social engineering, Phishing, Malware, Hacked content או כקטגוריה אחרת.
2. אילו כתובות מדויקות הוגדרו כבעייתיות ומתי.
3. האם אזהרת Chrome עדיין קיימת לכל המשתמשים וההקשרים.
4. האם קיים סיכון שלא זוהה בתצורות הישנות של האתר בזמן שההרשמה הייתה פתוחה.
5. בדיקות הרשמה ו-Google Sign-In, הודעות, פרסומים, מדיה ותורים מקצה לקצה, לאחר חידוש הפעילות.

## מסלול אימות חינמי ומדויק

1. הוספת נכס מסוג **URL-prefix** ב-Google Search Console בכתובת זו בלבד:  
   `https://karnafim-community-46.onrender.com/`
2. בחירת אימות בעלות דרך HTML tag והעברת ערך ה-`content` של `google-site-verification` למנהל הפרויקט.
3. בקוד האתר יש תשתית לתג בעלות דרך משתנה הסביבה `KARNAFIM_GSC_VERIFICATION`. אין להכניס לשם סיסמה או מפתח API. חובה לוודא תג בדף הראשי לפני לחיצה על Verify.
4. לאחר אימות הבעלות: **Security issues**, פתיחת פירוט הבעיה ודוגמאות כתובות ה-URL, והערכת כל נתיב.
5. תיקון בעיות מוכחות, סריקה חוזרת, ואז בקשת **Request Review** הכוללת סוג הבעיה, התיקונים ותוצאות הבדיקות. לא להגיש בקשה שלא עומדת בעובדות.
6. לשמור על מצב התחזוקה עד לסיום בדיקת האבטחה, ולא לנסות לעקוף את Chrome.

מסלול חלופי לסיווג שגוי, בהתאם להנחיות Google, לאחר בדיקת הסיווג:  
https://safebrowsing.google.com/safebrowsing/report_error/?hl=en

## קישורים רשמיים

- Google Security Issues Report: https://support.google.com/webmasters/answer/9044101
- Google Verify Site Ownership: https://support.google.com/webmasters/answer/9008080
- Google Dangerous Site Guidance: https://support.google.com/webmasters/answer/6347750
- Google Safe Browsing: https://safebrowsing.google.com/

## כללי הפעלה עד לסגירה

- אין להפעיל מחדש את `/login`, `/register`, `/new-post`, `/chats` או העלאת תמונות לפני האימות.
- אין לחשוף קבצים פרטיים, נתוני חברים או כתובות של אנשים שלא נתנו הסכמה.
- יש להבחין בין בדיקת `HTTP 200` לבין אישור בטיחות של Safe Browsing.
- אין למחוק נתונים קיימים או להחליף סודות ללא צורך מבוסס וביקורת גיבויים.

## עדכון טיפול עצמאי — 1.11.2026

- Render service `srv-dbj5hs8u01pc73ehboug` נבדק: הפריסה האחרונה `dep-dbj8p1oae00c73dh7ng0` עלתה ל-`Live`.
- חיבור GSC Wizard חסום בפועל עקב `payment_required`. לא בוצעה באמצעותו בדיקת Security Issues.
- במפת האתר יש נתיבי מורשת ציבוריים; חשבונות משתמשים והעלאות נשארים במצב התחזוקה (`KARNAFIM_MAINTENANCE=1`).
- פנייה רשמית נשלחה ל-`support@render.com` מחשבון Gmail המחובר בתאריך 1.11.2026; נושא: **Security review request: Chrome Safe Browsing warning on karnafim-community-46.onrender.com**. מזהה שיחה פנימי ב-Gmail `1a1949ac9ef2dc8e`.
- הופעל מעקב יומי לתגובות Render ולשינויי סטטוס מהותיים, ללא פתיחת האתר לפעולות אישיות.
- נבדק חיבור TinyFish: האפליקציה מסומנת כמותקנת, אך פעולות הדפדפן שלה אינן מופיעות ברשימת הכלים הזמינה בסשן זה. לכן לא בוצעה הגשה לטופס Google; אין לטעון שכן.
- המסך האדום ב-Chrome הוא עדות לסיווג סכנה פעיל מבחינת המשתמש; `HTTP 200`, `robots.txt`, `sitemap.xml` או הוספה לאינדקס **אינם** ראיה להסרתו.
- בירור הסיווג המדויק מחייב גישה ל-`Security Issues` של נכס האתר ב-Google Search Console או כלי דפדפן מחובר שמאפשר את בדיקת התלונה של Safe Browsing; אין לאמת בעלות באמצעות נתונים מומצאים.
- אין להגיש בקשת ״סיווג שגוי״ בטענה שנשללה פריצה או דיוג לפני ביסוס זאת בבדיקה מספקת.

## דיווח מאומת ל־Google Safe Browsing — 1.11.2026

- דוח הציבורי של Google Transparency Report מציג **Some pages on this site are unsafe** עבור דומיין האתר. סיווג הסיכון: ניסיון להונות מבקרים למסור פרטים אישיים או להוריד תוכנה. גם בדיקות /find, /login, /register ו-/ הציגו סיווג unsafe; אין להסיק שכל הנתיבים עצמם כוללים תוכן פוגעני.
- לאחר בדיקות התשתית והגבלת הפעולות האישיות, הוגש דרך טופס Google Safe Browsing /report_error דיווח עבור `https://karnafim-community-46.onrender.com/` (סוג: This page is safe), עם הסבר עובדתי על מצב הקריאה בלבד ועל היעדר ממצאים חשודים בבדיקות שבוצעו. Google אישרה **Status of submission: Submission was successful**.
- שדה ההסבר של Google הוגבל ל־800 תווים והטקסט נקטע; אין לייחס למשתמש הגשת טקסט מלא.
- אישור קבלת הטופס **אינו** אישור ניקוי, אישור בטיחות או ביטול האזהרה. יש להמתין לשינוי מאומת ב־Transparency Report/Chrome, להשלים בדיקות קוד ותוכן ולשמור על KARNAFIM_MAINTENANCE=1.
- תיעוד הריצה בדפדפן האוטומטי: https://agent.tinyfish.ai/runs/f3d61c7a-5155-4c58-bba8-c54a701d2368
