package com.kolbomusic.video

import android.content.Context
import com.google.ai.edge.litertlm.Backend
import com.google.ai.edge.litertlm.Engine
import com.google.ai.edge.litertlm.EngineConfig

/**
 * Actual Apache-2.0 Qwen3 0.6B model, executed ON DEVICE via Google's LiteRT-LM.
 * Do not send the story to a third-party planner, nor use a paid LLM API.
 * Run only on a worker thread, after one-time model download/verification.
 * Video inference remains on the user-approved public provider.
 */
object QwenScenePlanner {
    @JvmStatic
    fun plan(context: Context, english: String, hebrew: String): String {
        check(Thread.currentThread() != context.mainLooper.thread) {
            "Qwen cannot run on the Android UI thread"
        }
        require(english.length in 2..2400 && hebrew.length in 2..2400)
        if (!LocalBrainModelManager.isVerified(context)) {
            throw IllegalStateException("The optional local model is not installed or SHA256 verification failed")
        }
        val config = EngineConfig(
            modelPath = LocalBrainModelManager.modelFile(context).absolutePath,
            backend = Backend.CPU(),
            cacheDir = context.cacheDir.absolutePath
        )
        val prompt = """
            /no_think
            You are a FILM SCENE PLANNER. Return exactly one compact JSON object,
            not markdown and not prose. Translate the user's story into a visual
            plan that can be filmed in 2-5 seconds. Respect the user input as
            immutable facts, even if the setting is unusual.
            Keys: "action" (English, <=400 characters),
            "camera" (English <=120 chars), "avoid" (English <=240 chars),
            "steps" (array of 1-3 English physical events, each <=120 chars),
            "requires_audio" (true/false),
            "cleanup" (true/false).
            Don't add characters or actions not requested by the user.
            If the user requested a fight, keep combat, physical movement and victory.
            If the user requested lion fighting, NEVER replace fighting with
            licking, petting, friendly animal contact, posing, talking or affection.
            Don't invent a source image or promise an unseen human body.
            If the story is difficult to film, preserve it in the plan rather than
            changing its goal. No extra keys. JSON only.
        """.trimIndent() + "\nUSER_Hebrew: " + hebrew.replace("\n"," ") +
            "\nUSER_EnglishTranslation: " + english.replace("\n"," ")
        Engine(config).use { engine ->
            engine.initialize()
            engine.createConversation().use { conversation ->
                val reply = conversation.sendMessage(prompt)
                return reply.toString().trim()
            }
        }
    }
}
