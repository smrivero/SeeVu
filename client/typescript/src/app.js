"use strict";
/**
 * Copyright (c) 2024–2025, Daily
 *
 * SPDX-License-Identifier: BSD 2-Clause License
 */
var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
Object.defineProperty(exports, "__esModule", { value: true });
const client_js_1 = require("@pipecat-ai/client-js");
const websocket_transport_1 = require("@pipecat-ai/websocket-transport");
class WebsocketClientApp {
    constructor() {
        this.rtviClient = null;
        this.connectBtn = null;
        this.disconnectBtn = null;
        this.statusSpan = null;
        this.debugLog = null;
        this.wsUrlInput = null;
        this.botAudio = document.createElement('audio');
        this.botAudio.autoplay = true;
        document.body.appendChild(this.botAudio);
        this.setupDOMElements();
        this.setupEventListeners();
    }
    /**
     * Set up references to DOM elements and create necessary media elements
     */
    setupDOMElements() {
        this.connectBtn = document.getElementById('connect-btn');
        this.disconnectBtn = document.getElementById('disconnect-btn');
        this.statusSpan = document.getElementById('connection-status');
        this.debugLog = document.getElementById('debug-log');
        this.wsUrlInput = document.getElementById('ws-url');
        if (this.wsUrlInput) {
            this.wsUrlInput.value =
                localStorage.getItem(WebsocketClientApp.WS_URL_STORAGE_KEY) ||
                    WebsocketClientApp.DEFAULT_WS_URL;
        }
    }
    /**
     * Get the bot WebSocket URL from the input field, persisting it for next time
     */
    getWsUrl() {
        var _a;
        const value = ((_a = this.wsUrlInput) === null || _a === void 0 ? void 0 : _a.value.trim()) || WebsocketClientApp.DEFAULT_WS_URL;
        localStorage.setItem(WebsocketClientApp.WS_URL_STORAGE_KEY, value);
        return value;
    }
    /**
     * Set up event listeners for connect/disconnect buttons
     */
    setupEventListeners() {
        var _a, _b;
        (_a = this.connectBtn) === null || _a === void 0 ? void 0 : _a.addEventListener('click', () => this.connect());
        (_b = this.disconnectBtn) === null || _b === void 0 ? void 0 : _b.addEventListener('click', () => this.disconnect());
    }
    /**
     * Add a timestamped message to the debug log
     */
    log(message) {
        if (!this.debugLog)
            return;
        const entry = document.createElement('div');
        entry.textContent = `${new Date().toISOString()} - ${message}`;
        if (message.startsWith('User: ')) {
            entry.style.color = '#2196F3';
        }
        else if (message.startsWith('Bot: ')) {
            entry.style.color = '#4CAF50';
        }
        this.debugLog.appendChild(entry);
        this.debugLog.scrollTop = this.debugLog.scrollHeight;
        console.log(message);
    }
    /**
     * Update the connection status display
     */
    updateStatus(status) {
        if (this.statusSpan) {
            this.statusSpan.textContent = status;
        }
        this.log(`Status: ${status}`);
    }
    emulateTwilioMessages() {
        return __awaiter(this, void 0, void 0, function* () {
            var _a;
            const connectedMessage = {
                event: 'connected',
                protocol: 'Call',
                version: '1.0.0',
            };
            const websocketTransport = (_a = this.rtviClient) === null || _a === void 0 ? void 0 : _a.transport;
            void (websocketTransport === null || websocketTransport === void 0 ? void 0 : websocketTransport.sendRawMessage(connectedMessage));
            const startMessage = {
                event: 'start',
                start: {
                    streamSid: WebsocketClientApp.STREAM_SID,
                    callSid: WebsocketClientApp.CALL_SID,
                },
            };
            void (websocketTransport === null || websocketTransport === void 0 ? void 0 : websocketTransport.sendRawMessage(startMessage));
        });
    }
    /**
     * Check for available media tracks and set them up if present
     * This is called when the bot is ready or when the transport state changes to ready
     */
    setupMediaTracks() {
        var _a;
        if (!this.rtviClient)
            return;
        const tracks = this.rtviClient.tracks();
        if ((_a = tracks.bot) === null || _a === void 0 ? void 0 : _a.audio) {
            this.setupAudioTrack(tracks.bot.audio);
        }
    }
    /**
     * Set up listeners for track events (start/stop)
     * This handles new tracks being added during the session
     */
    setupTrackListeners() {
        if (!this.rtviClient)
            return;
        // Listen for new tracks starting
        this.rtviClient.on(client_js_1.RTVIEvent.TrackStarted, (track, participant) => {
            // Only handle non-local (bot) tracks
            if (!(participant === null || participant === void 0 ? void 0 : participant.local) && track.kind === 'audio') {
                this.setupAudioTrack(track);
            }
        });
        // Listen for tracks stopping
        this.rtviClient.on(client_js_1.RTVIEvent.TrackStopped, (track, participant) => {
            this.log(`Track stopped: ${track.kind} from ${(participant === null || participant === void 0 ? void 0 : participant.name) || 'unknown'}`);
        });
    }
    /**
     * Set up an audio track for playback
     * Handles both initial setup and track updates
     */
    setupAudioTrack(track) {
        this.log('Setting up audio track');
        if (this.botAudio.srcObject &&
            'getAudioTracks' in this.botAudio.srcObject) {
            const oldTrack = this.botAudio.srcObject.getAudioTracks()[0];
            if ((oldTrack === null || oldTrack === void 0 ? void 0 : oldTrack.id) === track.id)
                return;
        }
        this.botAudio.srcObject = new MediaStream([track]);
    }
    /**
     * Initialize and connect to the bot
     * This sets up the RTVI client, initializes devices, and establishes the connection
     */
    connect() {
        return __awaiter(this, void 0, void 0, function* () {
            try {
                const startTime = Date.now();
                const ws_opts = {
                    serializer: new websocket_transport_1.TwilioSerializer(),
                    recorderSampleRate: 8000,
                    playerSampleRate: 8000,
                    wsUrl: this.getWsUrl(),
                };
                const pcConfig = {
                    transport: new websocket_transport_1.WebSocketTransport(ws_opts),
                    enableMic: true,
                    enableCam: false,
                    callbacks: {
                        onConnected: () => {
                            this.emulateTwilioMessages();
                            this.updateStatus('Connected');
                            if (this.connectBtn)
                                this.connectBtn.disabled = true;
                            if (this.disconnectBtn)
                                this.disconnectBtn.disabled = false;
                        },
                        onDisconnected: () => {
                            this.updateStatus('Disconnected');
                            if (this.connectBtn)
                                this.connectBtn.disabled = false;
                            if (this.disconnectBtn)
                                this.disconnectBtn.disabled = true;
                            this.log('Client disconnected');
                        },
                        onBotReady: (data) => {
                            this.log(`Bot ready: ${JSON.stringify(data)}`);
                            this.setupMediaTracks();
                        },
                        onUserTranscript: (data) => {
                            if (data.final) {
                                this.log(`User: ${data.text}`);
                            }
                        },
                        onBotTranscript: (data) => this.log(`Bot: ${data.text}`),
                        onMessageError: (error) => console.error('Message error:', error),
                        onError: (error) => console.error('Error:', error),
                    },
                };
                this.rtviClient = new client_js_1.PipecatClient(pcConfig);
                this.setupTrackListeners();
                this.log('Initializing devices...');
                yield this.rtviClient.initDevices();
                this.log('Connecting to bot...');
                yield this.rtviClient.connect();
                const timeTaken = Date.now() - startTime;
                this.log(`Connection complete, timeTaken: ${timeTaken}`);
            }
            catch (error) {
                this.log(`Error connecting: ${error.message}`);
                this.updateStatus('Error');
                // Clean up if there's an error
                if (this.rtviClient) {
                    try {
                        yield this.rtviClient.disconnect();
                    }
                    catch (disconnectError) {
                        this.log(`Error during disconnect: ${disconnectError}`);
                    }
                }
            }
        });
    }
    /**
     * Disconnect from the bot and clean up media resources
     */
    disconnect() {
        return __awaiter(this, void 0, void 0, function* () {
            if (this.rtviClient) {
                try {
                    yield this.rtviClient.disconnect();
                    this.rtviClient = null;
                    if (this.botAudio.srcObject &&
                        'getAudioTracks' in this.botAudio.srcObject) {
                        this.botAudio.srcObject
                            .getAudioTracks()
                            .forEach((track) => track.stop());
                        this.botAudio.srcObject = null;
                    }
                }
                catch (error) {
                    this.log(`Error disconnecting: ${error.message}`);
                }
            }
        });
    }
}
WebsocketClientApp.STREAM_SID = 'ws_mock_stream_sid';
WebsocketClientApp.CALL_SID = 'ws_mock_call_sid';
WebsocketClientApp.DEFAULT_WS_URL = 'http://localhost:7860/ws';
WebsocketClientApp.WS_URL_STORAGE_KEY = 'pipecat-bot-ws-url';
window.addEventListener('DOMContentLoaded', () => {
    window.WebsocketClientApp = WebsocketClientApp;
    new WebsocketClientApp();
});
