package com.kolbo.chatbot.adapter

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.kolbo.chatbot.R
import com.kolbo.chatbot.databinding.ItemMessageBinding
import com.kolbo.chatbot.model.Message

class MessageAdapter : ListAdapter<Message, MessageAdapter.MessageViewHolder>(MessageDiffCallback()) {

    inner class MessageViewHolder(private val binding: ItemMessageBinding) : RecyclerView.ViewHolder(binding.root) {
        fun bind(message: Message) {
            binding.messageText.text = message.content
            binding.messageTime.text = message.getFormattedTime()
            
            val params = binding.messageContainer.layoutParams as ViewGroup.MarginLayoutParams
            val bgColor: Int
            val textColor: Int
            
            if (message.isUser) {
                params.marginEnd = 0
                params.marginStart = 60
                bgColor = ContextCompat.getColor(binding.root.context, R.color.user_message_bg)
                textColor = ContextCompat.getColor(binding.root.context, R.color.dark_gray)
            } else {
                params.marginEnd = 60
                params.marginStart = 0
                bgColor = ContextCompat.getColor(binding.root.context, R.color.bot_message_bg)
                textColor = ContextCompat.getColor(binding.root.context, R.color.dark_gray)
            }
            
            binding.messageContainer.layoutParams = params
            binding.messageContainer.setBackgroundColor(bgColor)
            binding.messageText.setTextColor(textColor)
        }
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): MessageViewHolder {
        val binding = ItemMessageBinding.inflate(LayoutInflater.from(parent.context), parent, false)
        return MessageViewHolder(binding)
    }

    override fun onBindViewHolder(holder: MessageViewHolder, position: Int) {
        holder.bind(getItem(position))
    }
}

class MessageDiffCallback : DiffUtil.ItemCallback<Message>() {
    override fun areItemsTheSame(oldItem: Message, newItem: Message) = oldItem.id == newItem.id
    override fun areContentsTheSame(oldItem: Message, newItem: Message) = oldItem == newItem
}
