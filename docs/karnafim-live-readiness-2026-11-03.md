# הקרנפים / ברקן — תמונת מצב מאומתת 03.11.2026

מסמך בדיקות ציבוריות, ללא גישה לחשבונות או לנתוני חברים. לא מהווה אישור אבטחה מלא או היתר להסרת הגנות.

## שירות חי מקורי
- `https://karnafim-community-46.onrender.com` ענה HTTP 200 במסלולים `/`, `/health`, `/ready`.
- `/health`: `status=ok`, `auth_enabled=true`, `database_configured=true`, `signup_enabled=true`, `registration_mode=manual_review`, `email_delivery_release_verified=false`.
- `/ready`: `status=ready`, `member_portal=enabled`.
- `/login` ו-`/signup`: GET 200; **לא בוצעה התחברות או הרשמה אמיתית**.
- למבקר בלתי מחובר `/profile`, `/find`, `/inbox`, `/media/1` מפנים בפועל ל-`/login`; נצפו כותרות CSP ו-`nosniff`. אין בכך בדיקת הרשאות לחשבונות מחוברים.
- Google Transparency Report Public Site Status החזיר `no_unsafe_content_found`, עם `phishing_signal=false`. ייתכן מצב שונה בדפדפן/בכתובת ספציפית; יש לאמת לפני שימוש בפרטי גישה.

## אתר הבנייה החדש
- `https://karnafim-barkan-46.onrender.com/health`: HTTP 200, `auth_enabled=false`, `database_configured=false`, `signup_enabled=false`.
- `/ready` ודפי הציבור שנבדקו עוברים בהפניה לאתר המקורי, ולכן תשובת 200 **אינה** מעידה שפריסת המערכת הדינמית החדשה מוכנה.
- אין להחליף את שירות הייצור הפעיל בגרסת הבנייה מחדש בלי גיבוי, תכנית הגירה, בדיקת הרשאות ואימות כלים ומסד נתונים.

## בדיקות הקוד בענף הבנייה מחדש
- בדיקות אבטחה: הצלחה — https://github.com/kolbomusic/kolbo-android-app/actions/runs/41637597716
- אינטגרציית PostgreSQL זמני (כולל אישור חברים, העלאת מדיה, צ'אט והצעת מקור הנצחה): הצלחה — https://github.com/kolbomusic/kolbo-android-app/actions/runs/41637597807
- ייצוא ציבורי: הצלחה — https://github.com/kolbomusic/kolbo-android-app/actions/runs/41637597787
- פרסום לתיקיית CDN ציבורית נפרדת: הצלחה — https://github.com/kolbomusic/kolbo-android-app/actions/runs/41637597819

## הנצחה ותמונות
- בעמוד `/memorial` החי נמצאו חמישה כרטיסים וקישורים לרשומות `izkor.gov.il` האישיות של בניה ריין, אורי גרוסמן, אדם גורן, אלכסנדר בונימוביץ ויהונתן (יוני) שרעבי.
- בבדיקת HTML לא נמצאו תמונות חיצוניות שהוטמעו בעמוד.
- תמונות מקומיות לפרסום עדיין זקוקות לאימות זכויות, אסמכתת הסכמה ובדיקת זהות; אין לטעון שהוצגו בפועל.
- מערכת הצעות מקור תמונה ותיעוד אישור נמצאת בענף הבנייה החדש, **לא אומתה כפרוסה לאתר המקורי**.

## דוח ייצור ציבורי
https://github.com/kolbomusic/kolbo-android-app/actions/runs/41638630067

## צעדים חסרים
1. לבחון את מצב ההזהרה בדפדפן ואת כל כתובות היישום החשובות במערכת.
2. לבצע בדיקת הרשאות התחברות והרשמה מקצה לקצה בסביבת ניסיון מבודדת או בחשבון בדיקה ייעודי ללא גישה למידע אמיתי.
3. לאמת מסירת מייל אם רוצים לעבור לאימות דוא״ל אוטומטי; כרגע הרשמה דורשת בדיקה ידנית.
4. להשיג תמונות עם זכויות מאושרות ולבדוק התאמה אישית לפני פרסום.
5. אם עוברים לקוד `karnafim-next`, להגדיר במפורש שירות Render ומסד נתונים, לבצע פריסה מדורגת ולהימנע מהחלפת סביבת המקור לפני בדיקה מלאה.
