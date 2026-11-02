# הקרנפים | ברקן — קהילת יוצאי פלוגה ב׳

אתר Flask בעברית RTL, מסד נתונים PostgreSQL ב־Neon ואירוח ב־Render. קהילה פרטית, אישור חברות על ידי מנהל בנפרד מאימות זהות.

## שחזור הכניסה המקורית — 2.11.2026

הוחזר למערכת מסלול הדוא״ל והסיסמה המקוריים, ללא תלות ב־Google. גיבובי הסיסמאות הישנים מסוג PBKDF2-SHA256 נשארים במסד הנתונים ולא אופסו. הקוד תומך בכניסה לחשבון קיים, הגנת CSRF, הגבלת ניסיונות, בקשת חברות חדשה באישור מפורש, שינוי סיסמה וביטול התחברויות קודמות באמצעות `session_version`.

**אין לפרסם טפסי כניסה בזמן אזהרת Google Safe Browsing.** ההתחברות המקומית הוכנה ונבדקה עם משתמש סינתטי בלבד. לא בוצע מבחן התחברות לסיסמה האישית האמיתית של משתמש, ואין לנסות להתחבר דרך אזהרת Chrome.

תנאי הפעלה משולבים, רק לאחר הסרת האזהרה ואישור בטיחות מפורש:

- `KARNAFIM_AUTH_METHOD=local` — ברירת המחדל החדשה. `google` הוא מסלול חלופי בלבד.
- `KARNAFIM_LOCAL_AUTH_ENABLED=1` — מציין שמותר מסלול מקומי; ברירת המחדל היא כבוי.
- `KARNAFIM_SAFETY_RELEASE_APPROVED=1` — חובה רק לאחר בדיקת Google מאומתת, לא על סמך בדיקות CI.
- `KARNAFIM_MAINTENANCE=0` — חובה לצאת ממצב ציבורי לקריאה בלבד.
- `KARNAFIM_ALLOW_REGISTRATION=1` — אופציונלי; הרשמות חדשות סגורות כברירת מחדל. בחברות חדשה `approved=false` עד אישור מנהל.

אם אפילו תנאי חובה אחד לא מתקיים, האתר עולה לצפייה ציבורית בלבד בלי לקרוא את מסד החברים ובלי להציג טפסי סיסמה. ביטול תחזוקה בלבד אינו פותח חשבונות.

לבדיקת השחזור ללא פרטי משתמש אמיתיים:
`python karnafim-site/tests/test_local_account_recovery.py`

## מסלול Google אופציונלי

הקוד הקודם של Google Identity Services / OAuth נשמר להבטחת אפשרות חזרה, אך אינו נדרש לכניסה המקומית. כדי להשתמש בו בעתיד נדרש `KARNAFIM_AUTH_METHOD=google`, אישור בטיחות ואימות תצורה דרך `KARNAFIM_GOOGLE_AUTH_ENABLED` והנתונים של Google. אין לפתוח אחד המסלולים כל עוד הדפדפן מזהיר.

## פריסה ובדיקות

- `SECRET_KEY`, `DATABASE_URL`, `ADMIN_EMAIL` נשארים כערכי סוד ב־Render.
- `python -m unittest discover -s karnafim-site/tests -p 'test_readonly_boot.py' -v` מאמת נעילת גישה.
- `python karnafim-site/security_regression.py --live --expect-revision SHA` בודק התאמת הגרסה והתנהגות השרת.
- מסלול Google Safe Browsing ב־GitHub שומר ראיות. סיווג אחרון שנבדק: `some_pages_unsafe`; אין להכריז על הסרת האזהרה ללא בדיקה מחדש.

האזהרה של Google היא החלטה חיצונית. הצלחת GitHub/Render אינה מבטלת אותה. כתובות /login, /register, /password ו-/auth/google/* מחזירות HTTP 410 במצב תחזוקה; נתיבי מידע אישי נשארים סגורים.
