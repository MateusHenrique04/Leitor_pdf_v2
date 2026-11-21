package com.lector.app.domain

/** Cache LRU limitado por "tamanho" total (aqui, pixels), não por quantidade. Não é thread-safe. */
class SizedLruCache<K, V>(private val maxSize: Long, private val sizeOf: (V) -> Long) {
    private val map = LinkedHashMap<K, V>(16, 0.75f, true) // ordem de acesso
    var currentSize: Long = 0L
        private set
    val count: Int get() = map.size

    fun get(key: K): V? = map[key]

    fun put(key: K, value: V) {
        map.remove(key)?.let { currentSize -= sizeOf(it) }
        val size = sizeOf(value)
        if (size > maxSize) return // não cabe nunca: não guarda
        map[key] = value
        currentSize += size
        val it = map.entries.iterator()
        while (currentSize > maxSize && it.hasNext()) {
            val eldest = it.next()
            currentSize -= sizeOf(eldest.value)
            it.remove()
        }
    }

    fun clear() {
        map.clear()
        currentSize = 0L
    }
}
