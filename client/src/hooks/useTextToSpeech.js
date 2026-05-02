import { useState, useEffect, useRef, useCallback } from 'react';

/**
 * Strip markdown, LaTeX, and formatting artifacts so text reads naturally
 * when passed to the SpeechSynthesis API.
 */
function cleanForTTS(text) {
  return text
    .replace(/\$\$([\s\S]*?)\$\$/g, ' $1 ')              // extract block LaTeX inner text
    .replace(/\$([^$]*?)\$/g, ' $1 ')                    // extract inline LaTeX inner text
    .replace(/```[\s\S]*?```/g, '')                      // code blocks
    .replace(/`[^`]*`/g, '')                             // inline code
    .replace(/[*_~#>|\\]/g, '')                          // markdown symbols
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')             // links → label only
    .replace(/^\d+\.\s+/gm, '')                          // strip "1. ", "2. " list prefixes
    .replace(/[\p{Emoji_Presentation}\p{Extended_Pictographic}]/gu, '') // strip emojis
    .replace(/\n{2,}/g, '. ')                            // paragraph breaks → pause
    .replace(/\n/g, ' ')
    .trim();
}

/**
 * Pick the best available English voice.
 * Prefers a local en-US voice, then any en-* voice, then whatever is available.
 */
function pickVoice() {
  const voices = window.speechSynthesis.getVoices();
  if (!voices.length) return null;
  return (
    voices.find((v) => v.lang === 'en-US' && v.localService) ||
    voices.find((v) => v.lang.startsWith('en')) ||
    voices[0]
  );
}

/**
 * useTextToSpeech — client-side TTS via the Web Speech API.
 *
 * Returns: { speak, stop, isSpeaking, isPaused, isSupported }
 *
 * Features:
 *  • Dedicated cleanForTTS() strips markdown/LaTeX before speaking.
 *  • Sentence-level chunking with recursive onend to bypass Chrome's
 *    ~250-word cutoff bug.
 *  • Interruption-safe: calling speak() while already speaking will
 *    stop the current utterance first.
 *  • Explicit voice selection (best en-US, handles async voiceschanged).
 */
export const useTextToSpeech = () => {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [isSupported, setIsSupported] = useState(true);

  const voiceRef = useRef(null);
  const chunksRef = useRef([]);
  const chunkIndexRef = useRef(0);
  const isSpeakingRef = useRef(false); // mirror for use inside callbacks

  // ── Check browser support & load voices ──────────────────────────
  useEffect(() => {
    if (typeof window === 'undefined' || !window.speechSynthesis) {
      setIsSupported(false);
      return;
    }

    // Try to pick a voice immediately (works when voices are cached)
    voiceRef.current = pickVoice();

    // Also listen for the async event (first page load, some browsers)
    const handleVoicesChanged = () => {
      voiceRef.current = pickVoice();
    };
    window.speechSynthesis.addEventListener('voiceschanged', handleVoicesChanged, { once: true });

    return () => {
      window.speechSynthesis.removeEventListener('voiceschanged', handleVoicesChanged);
    };
  }, []);

  // ── Internal: speak a single chunk, then recurse ─────────────────
  const speakChunk = useCallback(() => {
    const chunks = chunksRef.current;
    const idx = chunkIndexRef.current;

    if (idx >= chunks.length) {
      // All chunks done
      setIsSpeaking(false);
      isSpeakingRef.current = false;
      chunksRef.current = [];
      chunkIndexRef.current = 0;
      return;
    }

    const utterance = new SpeechSynthesisUtterance(chunks[idx]);

    // Attach the best voice we've found (may still be null → uses default)
    if (voiceRef.current) {
      utterance.voice = voiceRef.current;
    }
    utterance.rate = 0.85;
    utterance.pitch = 1;

    utterance.onend = () => {
      chunkIndexRef.current += 1;
      speakChunk(); // recursive — speak next chunk
    };

    utterance.onerror = (e) => {
      // 'interrupted' and 'canceled' are expected when stop() is called
      if (e.error !== 'interrupted' && e.error !== 'canceled') {
        console.error('[TTS] Utterance error:', e.error);
      }
      setIsSpeaking(false);
      isSpeakingRef.current = false;
      chunksRef.current = [];
      chunkIndexRef.current = 0;
    };

    window.speechSynthesis.speak(utterance);
  }, []);

  // ── Public: stop all speech and reset state ──────────────────────
  const stop = useCallback(() => {
    if (!isSupported) return;
    chunksRef.current = [];
    chunkIndexRef.current = 0;
    window.speechSynthesis.cancel();
    setIsSpeaking(false);
    setIsPaused(false);
    isSpeakingRef.current = false;
  }, [isSupported]);

  // ── Public: speak cleaned text, interrupting any current speech ──
  const speak = useCallback((rawText) => {
    if (!isSupported || !rawText) return;

    // Always interrupt any ongoing speech first
    stop();

    const cleaned = cleanForTTS(rawText);
    if (!cleaned) return;

    // Split by sentence boundaries → array of chunks
    const sentences = cleaned.split(/(?<=[.?!])\s+/).filter(Boolean);
    // If the regex produced no split (e.g. no punctuation), speak as one chunk
    chunksRef.current = sentences.length ? sentences : [cleaned];
    chunkIndexRef.current = 0;

    setIsSpeaking(true);
    isSpeakingRef.current = true;

    // Re-pick voice in case voiceschanged fired after mount
    if (!voiceRef.current) {
      voiceRef.current = pickVoice();
    }

    speakChunk();
  }, [isSupported, stop, speakChunk]);

  // ── Cleanup on unmount ───────────────────────────────────────────
  useEffect(() => {
    return () => {
      chunksRef.current = [];
      chunkIndexRef.current = 0;
      window.speechSynthesis?.cancel();
    };
  }, []);

  return { speak, stop, isSpeaking, isPaused, isSupported };
};
