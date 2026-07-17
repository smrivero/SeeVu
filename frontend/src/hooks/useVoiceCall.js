import { useState, useRef, useCallback, useEffect } from 'react'
import { PipecatClient, RTVIEvent } from '@pipecat-ai/client-js'
import { WebSocketTransport, TwilioSerializer } from '@pipecat-ai/websocket-transport'

const STREAM_SID = 'ws_mock_stream_sid'
const CALL_SID = 'ws_mock_call_sid'
export const BOT_WS_URL_KEY = 'botWsUrl'

export function getBotWsUrl() {
  return (
    localStorage.getItem(BOT_WS_URL_KEY) ||
    import.meta.env.VITE_BOT_WS_URL ||
    `${window.location.origin}/ws`
  )
}

export function useVoiceCall(onBeforeConnect) {
  const [status, setStatus] = useState('disconnected')
  const clientRef = useRef(null)
  const audioRef = useRef(null)

  const setupAudioTrack = useCallback((track) => {
    const audio = audioRef.current
    if (!audio) return

    if (audio.srcObject?.getAudioTracks) {
      const oldTrack = audio.srcObject.getAudioTracks()[0]
      if (oldTrack?.id === track.id) return
    }
    audio.srcObject = new MediaStream([track])
  }, [])

  const emulateTwilioMessages = useCallback((transport) => {
    transport?.sendRawMessage({
      event: 'connected',
      protocol: 'Call',
      version: '1.0.0',
    })
    transport?.sendRawMessage({
      event: 'start',
      start: { streamSid: STREAM_SID, callSid: CALL_SID },
    })
  }, [])

  const disconnect = useCallback(async () => {
    const client = clientRef.current
    if (!client) return

    try {
      await client.disconnect()
    } catch {
      /* ignore */
    }

    clientRef.current = null
    const audio = audioRef.current
    if (audio?.srcObject?.getAudioTracks) {
      audio.srcObject.getAudioTracks().forEach((track) => track.stop())
      audio.srcObject = null
    }
    setStatus('disconnected')
  }, [])

  const connect = useCallback(async () => {
    if (clientRef.current) return

    setStatus('connecting')

    try {
      if (onBeforeConnect) {
        const ready = await onBeforeConnect()
        if (!ready) {
          setStatus('disconnected')
          return
        }
      }

      const wsUrl = getBotWsUrl()
      const transport = new WebSocketTransport({
        serializer: new TwilioSerializer(),
        recorderSampleRate: 8000,
        playerSampleRate: 8000,
        wsUrl,
      })

      const client = new PipecatClient({
        transport,
        enableMic: true,
        enableCam: false,
        callbacks: {
          onConnected: () => {
            emulateTwilioMessages(client.transport)
            setStatus('connected')
          },
          onDisconnected: () => {
            clientRef.current = null
            setStatus('disconnected')
          },
          onBotReady: () => {
            const tracks = client.tracks()
            if (tracks.bot?.audio) setupAudioTrack(tracks.bot.audio)
          },
          onError: (error) => console.error('Voice call error:', error),
        },
      })

      client.on(RTVIEvent.TrackStarted, (track, participant) => {
        if (!participant?.local && track.kind === 'audio') {
          setupAudioTrack(track)
        }
      })

      clientRef.current = client
      await client.initDevices()
      await client.connect()
    } catch (error) {
      console.error('Connect failed:', error)
      clientRef.current = null
      setStatus('error')
    }
  }, [emulateTwilioMessages, onBeforeConnect, setupAudioTrack])

  useEffect(() => {
    return () => {
      void disconnect()
    }
  }, [disconnect])

  return {
    status,
    connect,
    disconnect,
    audioRef,
    isConnected: status === 'connected',
    isConnecting: status === 'connecting',
  }
}
