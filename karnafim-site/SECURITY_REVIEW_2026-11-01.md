# אתר הקרנפים / ברקן — תיק אבטחה מאוחד ומעודכן

**עודכן:** 1 בנובמבר 2026  
**אתר:** https://karnafim-community-46.onrender.com/  
**ייעוד:** קהילת מורשת עצמאית של יוצאי פלוגה ב׳ (הקרנפים / ברקן), גדוד 46, חטיבה 401 — **אינה גוף צבאי או ממשלתי רשמי**.

## תוצאה מאומתת — Google עדיין לא ניקתה את הסיווג

בבדיקה ישירה של סטטוס Google Safe Browsing עבור הדומיין הוחזר:
`["sb.ssr",3,false,false,true,false,false,1793495678416,"karnafim-community-46.onrender.com",false]`

זהו סימון פעיל של האתר כלא בטוח; גם `/find` עדיין מופיע בסיווג השמור של Google אף שהכתובת עצמה מחזירה כיום `410 Gone`. חותמת הזמן שבתשובה היא חותמת המידע שבידי Google, **לא** זמן הבדיקה העדכני. המידע הציבורי אינו מציג רשימה מלאה של כתובות חשודות או ראיה מובהקת לסיבה המקורית.

**אין להכריז שהאזהרה הוסרה רק משום שהשרת מחזיר HTTP 200, ש-GitHub CI עבר או שהוגשה בקשת סקירה.**

## בקשה לבחינה מחודשת והתקשרות עם תמיכה

- דרך טופס Google Safe Browsing הרשמי הוגשה בקשה לבדיקה מחודשת של האתר, והיא התקבלה בציון `Submission was successful`. זהו אישור **קבלה** בלבד, לא אישור הסרת אזהרה. אין לשלוח שוב בקשות זהות לפני תשובה או ממצא חדש.
- ל־Render נשלחו פנייה והבהרות בתיק התמיכה הקיים, כולל בקשה לבירור אנושי של דיווחי abuse והכתובות המדויקות. לא אומתה תשובת אדם שבדק את האתר.
- המשתמש אינו מעוניין בפתיחת נכס Search Console. אין ליצור נכס בשמו או לכפות אימות; קיימת תשתית אופציונלית למטא־תג בעלות, אך לא הוגדר נכס פעיל.

## תיקונים בפועל

1. **מצב ציבורי מוגבל לצפייה:** האתר עולה ב־Flask ללא שימוש במסד הנתונים של החברים; דפי מורשת, הנצחה, הסברים ותנאי שימוש מוצגים לציבור בלי טפסים לסיסמאות.
2. **כתובות שנמחקו:** `/find`, `/login`, `/register`, `/password` ונתיבי `/auth/google/*` מחזירים `410 Gone` והנחיית `noindex` בעת תקופת האבטחה. כתובת `/find` הוסרה גם מנתיבי החיפוש של הקהילה וממפת האתר.
3. **מידע אישי חסום:** `/directory`, `/chats`, `/chat/<id>`, `/profile`, `/new-post`, `/community-media/<id>`, ממשקי ניהול ופרסום מחזירים `503` במצב התחזוקה, בלי לשלוף נתונים.
4. **כתובות לא קיימות:** בקשות לנתיבים אקראיים מקבלות `404` ו־`noindex`, כדי להבדיל בינן לבין שירות מושבת.
5. **הגנות HTTP:** CSP במצב צפייה בלבד עם `form-action 'none'`, ללא קוד JavaScript ציבורי, מניעת הטמעת האתר במסגרת, `nosniff`, HSTS ו־`no-store`.
6. **נעילת שחרור משולשת:** כדי להחזיר את האזור הפרטי חייבים בו־זמנית `KARNAFIM_MAINTENANCE=0`, `KARNAFIM_SAFETY_RELEASE_APPROVED=1` והגדרת Google OIDC מאומתת. שינוי מקרי של משתנה אחד אינו פותח מידע אישי.
7. **זהות והרשאות:** קיים פרויקט Google Cloud נפרד ולקוח OAuth מסוג Web עם כתובת callback ידועה. מזהה הלקוח הוגדר ב־Render. **Client Secret עדיין לא חובר; Google Sign-In לא נבדק מקצה לקצה ולא הופעל לציבור.**
8. **קובצי חברים:** הרשאות המדיה נבדקות בצד השרת. המעלה רשאי לראות קובץ שלו, מנהל הקהילה יכול לבדוק קובץ שממתין לפרסום, וחבר אחר אינו יכול לפתוח מדיה לא מאושרת. קובצי תמונה עוברים בדיקת סוג, פענוח והסרת EXIF.
9. **פרסום וביקורת:** בדיקות יחידה מבודדות מבטיחות שהרשאות פרסום, אישור או דחיית תוכן וקבלת הסכמה לא מחייבות גישה למשתמשים אמיתיים.
10. **קישורים ומקורות:** קישורים פנימיים ומקורות היסטוריים נבדקים ב־CI. קישורים חיצוניים היסטוריים שהוסרו אינם מוצגים כקישורים עובדים. בודק הכתובות יודע לקודד נתיבי URL בעברית.

ב־GitHub קיימות בדיקות אוטומטיות של אבטחת נתיבים, תרחישי פרסום ומדיה וביקורת קישורים. בגרסה `08e73bc1` כל שלוש הבדיקות סיימו בהצלחה; יש לוודא שגרסת הייצור תואמת את ה־commit האחרון לאחר כל שינוי נוסף.

## מגבלה מוכרת של Render Free

לפי [התיעוד הרשמי של Render](https://render.com/docs/free), השירות החינמי עובר להשהיה לאחר 15 דקות ללא תעבורה. בזמן השהיה, Render עצמה מחזירה ל־`/robots.txt` תגובת `Disallow: /` בלי להעיר את השירות. זה עשוי להקשות על סריקה, אך **אין ראיה שהוא גורם לסיווג phishing של Google**. אין לעקוף אזהרת Chrome או להעביר את האתר לדומיין חדש רק כדי להסתיר אותה.

## מה עדיין מחייב אישור חיצוני או השלמה

- [ ] Google שינתה באופן מאומת את סטטוס Safe Browsing של **הדומיין המדויק**.
- [ ] זוהו או נשללו כתובות/משאבים חשודים נוספים לפי דוח של Google או מענה אנושי של Render.
- [ ] התקבל אישור אבטחה לפתיחת חשבונות.
- [ ] `GOOGLE_CLIENT_SECRET` נשמר בצורה פרטית במשתני סביבה של Render, ללא פרסום בצ׳אט או GitHub.
- [ ] בוצעה התחברות Google אמיתית, כולל אימות חתימות, state, nonce, issuer, audience ו־email_verified.
- [ ] אומתו הרשאות החברים ונחשפו רק נתונים שחבר בחר לשתף, לאחר אישור מנהל.
- [ ] כל בדיקות CI ומבחני האתר החי עברו ב־commit שהופעל ב־Render.

## נוסח תמציתי לאנליסט Google / Render

> This is an independently operated Israeli veterans' heritage community, not an official military or government sign-in portal. Former `/find`, local login, registration and Google OAuth endpoints are disabled (410/noindex). Member and media routes remain inaccessible in a database-independent read-only mode (503), with strict CSP disabling public forms and scripts. The latest CI security, publishing and link checks passed. Google Safe Browsing continues to flag the exact hostname, but no current offending URL has been provided by the public status interface. Please identify any exact URL or resource responsible for the classification and recrawl the remediated pages. No user password is collected by the public site.

**כלל יסוד:** אין לפתוח חשבונות, לאסוף סיסמאות או לפרסם מידע אישי עד להסרת האזהרה ולבדיקות התחברות מלאות.
