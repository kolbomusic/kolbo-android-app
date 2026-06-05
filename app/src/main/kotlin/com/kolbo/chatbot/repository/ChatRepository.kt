package com.kolbo.chatbot.repository

import com.google.ai.client.generativeai.GenerativeModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class ChatRepository {
    
    // ⚠️ הוסף את ה-API Key שלך בקובץ local.properties
    // GEMINI_API_KEY=your_key_here
    private val apiKey = "YOUR_GEMINI_API_KEY_HERE" // החלף זאת ב-API Key שלך
    
    private val generativeModel = GenerativeModel(
        modelName = "gemini-pro",
        apiKey = apiKey
    )

    suspend fun getGeminiResponse(userMessage: String): String = withContext(Dispatchers.IO) {
        try {
            val response = generativeModel.generateContent(userMessage)
            response.text ?: "לא הצלחתי להשיג תשובה"
        } catch (e: Exception) {
            throw Exception("שגיאה בהתחברות ל-Gemini: ${e.message}")
        }
    }
}
