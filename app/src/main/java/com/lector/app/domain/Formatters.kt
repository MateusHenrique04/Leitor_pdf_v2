package com.lector.app.domain

import java.util.Locale

object Formatters {
    private val pt = Locale.forLanguageTag("pt-BR")

    /** 512 B, 2 KB, 5,0 MB, 150 MB, 1,50 GB. */
    fun bytes(b: Long): String {
        val kb = 1024.0
        val mb = kb * 1024
        val gb = mb * 1024
        return when {
            b < 1024 -> "$b B"
            b < mb -> String.format(pt, "%.0f KB", b / kb)
            b < gb -> {
                val v = b / mb
                if (v >= 100) String.format(pt, "%.0f MB", v) else String.format(pt, "%.1f MB", v)
            }
            else -> String.format(pt, "%.2f GB", b / gb)
        }
    }

    /** 45 s, 10 min, 1 h 02 min. */
    fun duration(seconds: Long): String = when {
        seconds < 60 -> "$seconds s"
        seconds < 3600 -> "${seconds / 60} min"
        else -> String.format(pt, "%d h %02d min", seconds / 3600, (seconds % 3600) / 60)
    }
}
