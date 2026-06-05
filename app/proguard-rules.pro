-keep class com.google.ai.** { *; }
-keep interface com.google.ai.** { *; }
-dontwarn com.google.ai.**

-keep class com.google.gson.** { *; }
-keep interface com.google.gson.** { *; }

-keepattributes Signature
-keepattributes EnclosingMethod
-keep class sun.misc.Unsafe { *; }
