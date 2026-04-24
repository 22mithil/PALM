import { useState, useEffect, useRef, useCallback } from 'react';

export const useSpeechRecognition = () => {
  const [isListening, setIsListening] = useState(false);
  const [interimTranscript, setInterimTranscript] = useState('');
  const [finalTranscript, setFinalTranscript] = useState('');
  const [error, setError] = useState(null);
  const [isSupported, setIsSupported] = useState(true);
  
  const recognitionRef = useRef(null);
  const isListeningRef = useRef(isListening); // to track latest state in events

  useEffect(() => {
    isListeningRef.current = isListening;
  }, [isListening]);

  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setIsSupported(false);
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onresult = (event) => {
      let currentInterim = '';
      let currentFinal = '';

      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          currentFinal += event.results[i][0].transcript;
        } else {
          currentInterim += event.results[i][0].transcript;
        }
      }

      setInterimTranscript(currentInterim);
      if (currentFinal) {
        setFinalTranscript((prev) => prev + currentFinal);
      }
    };

    recognition.onerror = (event) => {
      console.error('Speech recognition error:', event.error);
      if (['not-allowed', 'service-not-allowed'].includes(event.error)) {
        setError('Microphone permission denied. Please allow it in your browser settings.');
        setIsListening(false);
      } else if (event.error === 'network') {
        setError('Network error: Speech recognition failed. It requires an active internet connection, or your browser might restrict it.');
        setIsListening(false);
      } else if (event.error !== 'no-speech') {
        setError(`Speech recognition error: ${event.error}`);
      }
    };

    recognition.onend = () => {
      // Auto restart if it was supposed to be listening (e.g. browser stopped it automatically after pause)
      if (isListeningRef.current) {
        try {
          recognition.start();
        } catch (e) {
          console.error('Failed to restart recognition', e);
          setIsListening(false);
        }
      } else {
        setIsListening(false);
      }
    };

    recognitionRef.current = recognition;

    return () => {
      recognition.stop();
    };
  }, []);

  const start = useCallback(() => {
    if (recognitionRef.current && !isListeningRef.current) {
      try {
        setError(null);
        setInterimTranscript('');
        recognitionRef.current.start();
        setIsListening(true);
      } catch (err) {
        console.error('Error starting recognition:', err);
      }
    }
  }, []);

  const stop = useCallback(() => {
    if (recognitionRef.current && isListeningRef.current) {
      setIsListening(false);
      recognitionRef.current.stop();
      setInterimTranscript('');
    }
  }, []);

  const clearTranscript = useCallback(() => {
    setInterimTranscript('');
    setFinalTranscript('');
  }, []);

  return { 
    start, 
    stop, 
    isListening, 
    interimTranscript, 
    finalTranscript, 
    clearTranscript,
    isSupported,
    error
  };
};
