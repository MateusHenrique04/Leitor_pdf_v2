package com.lector.app.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.floatPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.lector.app.domain.Voices
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.lectorDataStore: DataStore<Preferences> by preferencesDataStore(name = "lector_prefs")

/** Preferências do app: voz e velocidade da narração e as restrições do download. */
class LectorPrefs(context: Context) {
    private val store = context.applicationContext.lectorDataStore

    /** Voz da narração e dos downloads; se a guardada não existe mais na lista, volta à padrão. */
    val voice: Flow<String> = store.data.map { p ->
        p[VOICE]?.takeIf { Voices.byId(it) != null } ?: Voices.DEFAULT_ID
    }

    val speed: Flow<Float> = store.data.map { p -> (p[SPEED] ?: 1f).coerceIn(0.5f, 2.5f) }

    val wifiOnly: Flow<Boolean> = store.data.map { p -> p[WIFI_ONLY] ?: true }

    val chargingOnly: Flow<Boolean> = store.data.map { p -> p[CHARGING_ONLY] ?: false }

    suspend fun setVoice(id: String) { store.edit { it[VOICE] = id } }
    suspend fun setSpeed(v: Float) { store.edit { it[SPEED] = v } }
    suspend fun setWifiOnly(v: Boolean) { store.edit { it[WIFI_ONLY] = v } }
    suspend fun setChargingOnly(v: Boolean) { store.edit { it[CHARGING_ONLY] = v } }

    private companion object {
        val VOICE = stringPreferencesKey("voice")
        val SPEED = floatPreferencesKey("speed")
        val WIFI_ONLY = booleanPreferencesKey("download_wifi_only")
        val CHARGING_ONLY = booleanPreferencesKey("download_charging_only")
    }
}
