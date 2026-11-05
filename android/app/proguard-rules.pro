# kotlinx.serialization
-keepattributes *Annotation*, InnerClasses
-keep,includedescriptorclasses class org.o2monitor.**$$serializer { *; }
-keepclassmembers class org.o2monitor.** { *** Companion; }
# LiteRT / TFLite
-keep class org.tensorflow.lite.** { *; }
