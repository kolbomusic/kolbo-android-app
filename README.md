# Kolbo Chatbot - Android App with Gemini AI

🤖 אפליקציית צ'אט בוט מתקדמת עם Google Gemini AI

## 🚀 תכונות
- ✅ ממשק צ'אט חדיש ונוח
- ✅ אינטגרציה עם Gemini API
- ✅ תמיכה בעברית מלאה (RTL)
- ✅ ממשק מגיב (Responsive)
- ✅ Management של הודעות בזמן אמת

## 📋 דרישות
- Android 7.0 (API 24) ומעלה
- Android Studio Hedgehog או חדש יותר
- JDK 11+

## 🔑 הגדרה ראשונית

### 1. קבל API Key מ-Google
1. עבור ל-[Google AI Studio](https://makersuite.google.com/app/apikey)
2. צור API Key חדש
3. העתק את ה-Key

### 2. הוסף את ה-Key לפרויקט
ערוך את `local.properties`:
```properties
GEMINI_API_KEY=your_api_key_here
```

או עדכן ישירות בקובץ:
`app/src/main/kotlin/com/kolbo/chatbot/repository/ChatRepository.kt`

## 🏗️ Structure הפרויקט
```
kolbo-android-app/
├── app/
│   ├── src/main/
│   │   ├── kotlin/com/kolbo/chatbot/
│   │   │   ├── MainActivity.kt
│   │   │   ├── model/Message.kt
│   │   │   ├── adapter/MessageAdapter.kt
│   │   │   ├── viewmodel/ChatViewModel.kt
│   │   │   └── repository/ChatRepository.kt
│   │   ├── res/
│   │   │   ├── layout/
│   │   │   ├── values/
│   │   │   └── drawable/
│   │   └── AndroidManifest.xml
│   └── build.gradle
├── build.gradle
└── settings.gradle
```

## 📦 Dependencies
- **AndroidX**: Core, AppCompat, ConstraintLayout
- **Google Generative AI**: SDK לשימוש ב-Gemini
- **Coroutines**: לעיבוד אסינכרוני
- **Material**: עיצוב Material Design

## 🛠️ בניית ההפליקציה
```bash
./gradlew build
```

## ▶️ הפעלה
1. חבר טלפון או הפעל אמולטור
2. הרץ: `./gradlew installDebug`
3. או דחוף F5 ב-Android Studio

## 📝 License
MIT

## 👨‍💻 Author
Kolbo Music
