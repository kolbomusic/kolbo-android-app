package com.kolbo.chatbot.viewmodel

import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.kolbo.chatbot.model.Message
import com.kolbo.chatbot.repository.ChatRepository
import kotlinx.coroutines.launch

class ChatViewModel : ViewModel() {

    private val repository = ChatRepository()
    
    private val _messages = MutableLiveData<List<Message>>(emptyList())
    val messages: LiveData<List<Message>> = _messages
    
    private val _isLoading = MutableLiveData<Boolean>(false)
    val isLoading: LiveData<Boolean> = _isLoading

    fun sendMessage(content: String) {
        val userMessage = Message(content = content, isUser = true)
        _messages.value = _messages.value?.plus(userMessage) ?: listOf(userMessage)
        
        viewModelScope.launch {
            _isLoading.value = true
            try {
                val response = repository.getGeminiResponse(content)
                val botMessage = Message(content = response, isUser = false)
                _messages.value = _messages.value?.plus(botMessage) ?: listOf(botMessage)
            } catch (e: Exception) {
                val errorMessage = Message(
                    content = "שגיאה: ${e.message}",
                    isUser = false
                )
                _messages.value = _messages.value?.plus(errorMessage) ?: listOf(errorMessage)
            } finally {
                _isLoading.value = false
            }
        }
    }
}
