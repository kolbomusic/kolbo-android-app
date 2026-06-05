package com.kolbo.chatbot.model

import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

data class Message(
    val id: String = System.currentTimeMillis().toString(),
    val content: String,
    val isUser: Boolean,
    val timestamp: LocalDateTime = LocalDateTime.now()
) {
    fun getFormattedTime(): String {
        return timestamp.format(DateTimeFormatter.ofPattern("HH:mm"))
    }
}
