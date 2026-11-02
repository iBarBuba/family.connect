/*
 * TranscriptRequests.kt
 * Family Connect (Android)
 *
 * Asking for the text of a recording, with the consent question in front
 * of it (docs/protocol.md, "Transcripts on request" and "Consenting to the
 * assistant").
 *
 * The asker is the one sending the sound to the provider, so the backdrop's
 * rule applies: an asker this device knows has not agreed is asked FIRST
 * and nothing is sent; an asker the server says has not agreed
 * (`assistant_consent_required`) is asked on that answer. Agreeing finishes
 * the request already made, as it does for a backdrop.
 *
 * Kept free of Compose and of the view models so a plain test can drive
 * it: the three things it needs are handed in. What it holds is only what
 * is IN FLIGHT or how the last try ended; the text itself lives in the
 * database ([me.nettrash.familyconnect.data.repo.TranscriptRepository]).
 */

package me.nettrash.familyconnect.ui.chat

import java.util.concurrent.ConcurrentHashMap
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import me.nettrash.familyconnect.data.net.dto.AttachmentDto
import me.nettrash.familyconnect.data.repo.PaidFamilies
import me.nettrash.familyconnect.data.repo.TranscriptOutcome

class TranscriptRequests(
    private val scope: CoroutineScope,
    /** Read fresh at every ask, so a consent given elsewhere counts at once. */
    private val gate: suspend () -> AssistantConsent.TranscriptGate,
    /** The request (or the text already held), read. */
    private val fetch: suspend (Ask) -> TranscriptOutcome,
    /** POST /me/assistant-consent `{granted: true}`; whether it was recorded. */
    private val agree: suspend () -> Boolean,
    /** Epoch milliseconds: when a used-up month was refused, and whether it has renewed since. */
    private val clock: () -> Long = System::currentTimeMillis,
) {
    /**
     * Which recording, and where it lives on the server. [attachment] says
     * whether the server sends its own copy or this device supplies the
     * sound ([TranscriptRules.route]); null is the stored copy.
     */
    data class Ask(
        val chatId: Long,
        val messageId: Long,
        val attachmentId: Long,
        val attachment: AttachmentDto? = null,
    )

    /** What one attachment's line says while there is no text to show. */
    enum class Status {
        /** "Getting the text…" */
        LOADING,

        /** "Couldn't get the text. Try again." — with the action still there. */
        FAILED,

        /** The provider refused the recording. No retry. */
        REFUSED,

        /** "Not available for this message." No retry. */
        UNAVAILABLE,

        /** "This recording is too long to turn into text." No retry. */
        TOO_LONG,

        /** "Couldn't read the sound in this file." No retry. */
        UNREADABLE,

        /**
         * A paid family has used this month's transcript minutes: the
         * sentence names the 1st of the next month (UTC) after the refusal,
         * [renewsAt]. No retry until then ([statusAt]).
         */
        ALLOWANCE_USED,
    }

    private val _status = MutableStateFlow<Map<Long, Status>>(emptyMap())

    /** Per attachment id; absent means nothing to say beyond what the database holds. */
    val status: StateFlow<Map<Long, Status>> = _status.asStateFlow()

    /**
     * When each [Status.ALLOWANCE_USED] line's month renews, in epoch
     * milliseconds. Written before the status that needs it, so whoever
     * reads that status finds it here.
     */
    private val renewals = ConcurrentHashMap<Long, Long>()

    /**
     * The day an [Status.ALLOWANCE_USED] line names: the 1st after the
     * refusal CAME, so a redraw a month later still names the same day
     * (docs/protocol.md, "Transcripts on request").
     */
    fun renewsAt(attachmentId: Long): Long? = renewals[attachmentId]

    /**
     * What [attachmentId]'s line says at [now], from [statuses] as collected:
     * the same, except that a used-up month lasts only until it renews.
     * From then the server takes the request again, and the line is back to
     * "Show text" — under the player and in the menu alike.
     */
    fun statusAt(statuses: Map<Long, Status>, attachmentId: Long, now: Long = clock()): Status? {
        val status = statuses[attachmentId]
        val renews = renewals[attachmentId]
        return if (status == Status.ALLOWANCE_USED && renews != null && now >= renews) null else status
    }

    private val waiting = MutableStateFlow<Ask?>(null)

    /** Whether the consent screen should be up: true while a request waits on the answer. */
    val asking: Flow<Boolean> = waiting.map { it != null }

    /** "Show text". A second tap while one is running is the same request, not another. */
    fun request(ask: Ask) {
        if (_status.value[ask.attachmentId] == Status.LOADING) return
        scope.launch {
            when (gate()) {
                // Not offered, so not normally reachable.
                AssistantConsent.TranscriptGate.WITHHELD -> set(ask, Status.UNAVAILABLE)
                AssistantConsent.TranscriptGate.ASK_CONSENT -> hold(ask)
                AssistantConsent.TranscriptGate.ASK_FOR_TEXT -> run(ask)
            }
        }
    }

    /** "I Agree": record it, then ask for the text that was waiting. */
    fun agreed() {
        // Taken before anything suspends, so a second tap finds nothing.
        val held = waiting.value ?: return
        waiting.value = null
        scope.launch {
            if (agree()) run(held) else set(held, Status.FAILED)
        }
    }

    /** "Not Now": nothing was sent, and nothing needs saying. */
    fun dismissed() {
        waiting.value = null
    }

    private suspend fun run(ask: Ask) {
        set(ask, Status.LOADING)
        when (fetch(ask)) {
            // The text is in the database now; the line draws it from there.
            is TranscriptOutcome.Text -> set(ask, null)
            // The account that asked signed out while it was out: nothing
            // was kept, and the line goes back to saying nothing.
            TranscriptOutcome.Dropped -> set(ask, null)
            TranscriptOutcome.Refused -> set(ask, Status.REFUSED)
            TranscriptOutcome.Unavailable -> set(ask, Status.UNAVAILABLE)
            TranscriptOutcome.Failed -> set(ask, Status.FAILED)
            TranscriptOutcome.TooLong -> set(ask, Status.TOO_LONG)
            TranscriptOutcome.Unreadable -> set(ask, Status.UNREADABLE)
            TranscriptOutcome.AllowanceUsed ->
                set(ask, Status.ALLOWANCE_USED, renewsAt = PaidFamilies.nextMonthStartUtc(clock()))
            TranscriptOutcome.ConsentRequired ->
                // The server's answer outranks this device's stamp: ask,
                // and request again on a yes — unless the assistant cannot
                // be named, in which case there is no screen to show.
                if (gate() == AssistantConsent.TranscriptGate.WITHHELD) {
                    set(ask, Status.FAILED)
                } else {
                    set(ask, null)
                    hold(ask)
                }
        }
    }

    private fun hold(ask: Ask) {
        // One question at a time: an earlier request still waiting on it is
        // simply not made, and its line goes back to "Show text".
        waiting.value = ask
    }

    private fun set(ask: Ask, value: Status?, renewsAt: Long? = null) {
        if (renewsAt != null) renewals[ask.attachmentId] = renewsAt
        _status.update { current ->
            if (value == null) current - ask.attachmentId else current + (ask.attachmentId to value)
        }
        if (renewsAt == null) renewals.remove(ask.attachmentId)
    }
}
