import { useState, useEffect, useCallback } from 'react'
import { sendToBackground } from '../../utils/messaging'

/**
 * Voice input hook.
 *
 * Instead of calling SpeechRecognition from the chrome-extension:// origin
 * (which Chrome blocks), we inject the recogniser into the active https:// tab
 * via chrome.scripting.executeScript (ISOLATED world). Chrome then shows the
 * normal microphone permission prompt for that site.
 *
 * The injected function sends a VOICE_RESULT runtime message which this hook
 * picks up via chrome.runtime.onMessage.
 */
export function useSpeechInput(onResult: (text: string) => void, language = '') {
  const [listening, setListening] = useState(false)
  const [speechError, setSpeechError] = useState<string | null>(null)

  // Listen for VOICE_RESULT messages sent back from the injected page script.
  useEffect(() => {
    const handler = (message: {
      type: string
      transcript?: string
      error?: string
    }) => {
      if (message.type !== 'VOICE_RESULT') return

      setListening(false)

      if (message.transcript) {
        setSpeechError(null)
        onResult(message.transcript)
      } else if (message.error) {
        setSpeechError(
          message.error === 'not-allowed'
            ? 'Microphone blocked. Click the 🎙 icon in the address bar and allow microphone for this site.'
            : message.error === 'no-speech'
            ? 'No speech detected — try again.'
            : message.error === 'not-supported'
            ? 'Speech recognition is not supported in this browser.'
            : `Speech error: ${message.error}`,
        )
      }
    }

    chrome.runtime.onMessage.addListener(handler)
    return () => chrome.runtime.onMessage.removeListener(handler)
  }, [onResult])

  const startListening = useCallback(async () => {
    setSpeechError(null)
    setListening(true)

    const res = await sendToBackground<{ started?: boolean; error?: string }>({
      type: 'START_VOICE_CAPTURE',
      language,
    })

    if (res.error) {
      setSpeechError(res.error)
      setListening(false)
    }
    // If started: true, we wait for VOICE_RESULT to arrive via onMessage above.
  }, [])

  const stopListening = useCallback(() => {
    // The recognition in the page runs until it hears speech or times out.
    // We just update our local state — the page script will finish on its own.
    setListening(false)
  }, [])

  return { listening, speechError, startListening, stopListening, supported: true }
}
