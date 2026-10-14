# הפעלת המוח בענן — פעם אחת בלבד

## האפשרות הפשוטה יותר — כפתור Deploy to Cloudflare

**[הפעל את מוח ה־AI בענן ב־Cloudflare](https://deploy.workers.cloudflare.com/?url=https://github.com/kolbomusic/kolbo-android-app/tree/kolbo-video-v520-lightweight-cloud-first-20261014/cloud-brain-worker)**

הקישור הרשמי של Cloudflare פותח תהליך חיבור ופריסה של ה־Worker עם קובץ התצורה שלו, כולל Workers AI. בחר **Workers Free**, התחבר לחשבון Cloudflare ואשר פריסה. אל תאשר תוכנית בתשלום.

לאחר שהפריסה הושלמה, העתק לצ'אט **רק** את הכתובת הציבורית שמסתיימת ב־`workers.dev`, למשל `https://kolbo-cloud-story-brain.example.workers.dev` — **זו דוגמה, לא כתובת פעילה**. אל תשלח סיסמה, Token או Account ID. אבדוק בעצמי שה־`/health` עובד ואת בקשת הניסוי בעברית, ורק אחרי הצלחה אעדכן את `endpoint.json` בענף הפרויקט. ה־APK 5.3 שהותקן יגלה את השרת בעצמו ללא התקנה חוזרת.

אם מסלול Deploy to Cloudflare אינו מצליח עם מבנה המאגר, ניתן להשתמש במסלול GitHub Actions שלהלן. גם במסלול הראשון עדיין נדרש אישור חד־פעמי שלך דרך Cloudflare — אין כאן פריסה לחשבון בלי הרשאה.

---


**מצב נוכחי:** קוד Cloudflare Worker קיים; `endpoint.json` כבוי בכוונה. אין שרת AI פעיל ואין להציג את תכנון הענן כמחובר עד מעבר בדיקת API אמיתית. האפליקציה 5.3.0 נשארת קלה, ללא מודלי AI או הורדות משקלים לטלפון.

## ההרשאה החד-פעמית הדרושה

1. ב־[Cloudflare Dashboard](https://dash.cloudflare.com/) נכנסים או פותחים חשבון במסלול **Workers Free**. מוצאים את **Account ID**. Cloudflare מפרסמת עד 10,000 Neurons ביום במסלול Free, בכפוף למגבלות ולשינויים בתנאים. אסור לשדרג למסלול בתשלום בלי אישור.
2. ב־Cloudflare יוצרים **API Token ייעודי** לפי [מדריך GitHub Actions של Cloudflare](https://developers.cloudflare.com/workers/ci-cd/external-cicd/github-actions/), עם הרשאות הנדרשות ליצירת Worker/עריכת Workers בלבד, בחשבון המסוים. אין להשתמש ב־Global API Key.
3. ב־[GitHub Actions Secrets של הפרויקט](https://github.com/kolbomusic/kolbo-android-app/settings/secrets/actions) מוסיפים **שני סודות** (לא כקבצים, לא כטקסט בפרויקט ולא בצ'אט):
   - `CLOUDFLARE_API_TOKEN` — ה־API Token.
   - `CLOUDFLARE_ACCOUNT_ID` — מזהה החשבון.
4. ב־[GitHub Actions](https://github.com/kolbomusic/kolbo-android-app/actions) מפעילים ידנית את `Kolbo Cloudflare deployment (only after owner config)` בענף `kolbo-video-v520-lightweight-cloud-first-20261014`. אין צורך במחשב שיישאר דולק. 
5. הפעולה מבצעת לבד: פריסת Worker, גילוי כתובת `workers.dev` הרשמית, בדיקת `/health`, בקשה סינתטית אחת ליצירת תסריט והפעלת `cloud-brain-worker/endpoint.json` **רק** אם הכול עבר. חיבור ה־APK הקיים מאתר את הכתובת החדשה ב־HTTPS. לא נדרשת התקנה מחדש.
6. אם הבנייה או בדיקת השרת נכשלות, הכתובת נשארת כבויה והאפליקציה ממשיכה עם תכנון מקומי בסיסי ללא הפקת AI כללית.

## אבטחה ומכסה
- ה־Worker אינו מקבל תמונות או סרטונים, אלא תיאור סיפור ותרגום בסיסי בלבד, וגם זה רק לאחר סימון הסכמה נפרדת באפליקציה.
- מובנים שני Rate Limiters של Cloudflare — **2 בקשות בדקה לכל כתובת IP**, ו־**3 בדקה בסך הכול**. אם bindings אלה חסרים, השרת מחזיר 503 בלי להריץ AI. הגבלות אלה אינן מנגנון הזדהות והן לא מגינות לחלוטין מפני שימוש לרעה בשרת ציבורי.
- אם Cloudflare Free ממצה את המכסה, תכנון AI לא יצליח עד התחדשות המכסה, אך המערכת לא תעבור אוטומטית לשירות בתשלום.
- הפקת הווידאו עצמה עדיין משתמשת במנועי Wan הציבוריים ומושפעת ממכסת ZeroGPU. מודל התכנון המשופר אינו מסוגל לאלץ מנוע וידאו חיצוני לציית בסצנות מורכבות או לספק מחשוב בלתי מוגבל.

## בדיקות
- קוד Worker: `cloud-brain-worker/src/index.js`; בדיקות Node: `cloud-brain-worker/test/worker.test.js`.
- בדיקות CI: `kolbo-v520-cloud-brain-tests.yml`. אינן צורכות מכסת AI; הן בודקות JSON, העדר Retry, הגבלת בקשות ו־Wrangler dry-run.
- בדיקת AI מלאה מתבצעת **רק** בעת ההפעלה החד־פעמית, ובתנאי שהמשתמש סיפק הרשאות.
- Android: פרויקט `mobile-kolbo`; הגרסה החדשה 5.3.0 שומרת על חוסר יכולת לסמן הצלחה סמנטית בלי מודל ראייה אמיתי.

**אין לשלוח סיסמאות או API Tokens לצ'אט.** הזינו אותם ישירות ב־GitHub Secrets בלבד.
