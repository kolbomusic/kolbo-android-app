package com.kolbo.chatbot

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.ViewModelProvider
import androidx.recyclerview.widget.LinearLayoutManager
import com.kolbo.chatbot.adapter.MessageAdapter
import com.kolbo.chatbot.databinding.ActivityMainBinding
import com.kolbo.chatbot.viewmodel.ChatViewModel

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var viewModel: ChatViewModel
    private lateinit var adapter: MessageAdapter

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        
        setupToolbar()
        setupRecyclerView()
        setupViewModel()
        setupListeners()
    }

    private fun setupToolbar() {
        setSupportActionBar(binding.toolbar)
        supportActionBar?.title = "Kolbo Chatbot"
    }

    private fun setupRecyclerView() {
        adapter = MessageAdapter()
        binding.messagesRecyclerView.apply {
            layoutManager = LinearLayoutManager(this@MainActivity).apply {
                stackFromEnd = true
            }
            adapter = this@MainActivity.adapter
        }
    }

    private fun setupViewModel() {
        viewModel = ViewModelProvider(this).get(ChatViewModel::class.java)
        
        viewModel.messages.observe(this) { messages ->
            adapter.submitList(messages)
            binding.messagesRecyclerView.scrollToPosition(messages.size - 1)
        }
        
        viewModel.isLoading.observe(this) { isLoading ->
            binding.sendButton.isEnabled = !isLoading
        }
    }

    private fun setupListeners() {
        binding.sendButton.setOnClickListener {
            val message = binding.messageInput.text.toString().trim()
            if (message.isNotEmpty()) {
                viewModel.sendMessage(message)
                binding.messageInput.text.clear()
            }
        }
    }
}
