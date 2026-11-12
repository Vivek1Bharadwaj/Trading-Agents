import { useState, useRef, useCallback, useEffect } from 'react';

const RECONNECT_DELAYS_MS = [1000, 2000, 3000, 5000, 8000, 10000];

const getWsUrl = () => {
    const apiUrl = (import.meta.env.VITE_API_URL || '').trim().replace(/\/+$/, '');
    if (apiUrl) {
        return apiUrl.replace(/^http/, 'ws') + '/ws/analysis';
    }
    if (typeof window !== 'undefined' && window.location && window.location.host) {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${window.location.host}/ws/analysis`;
    }
    return 'ws://localhost:8000/ws/analysis';
};

const generateRunId = () => {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
        return crypto.randomUUID();
    }
    return `run-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
};

export const useWebSocket = () => {
    const [messages, setMessages] = useState([]);
    const [agentStatuses, setAgentStatuses] = useState({});
    const [reportSections, setReportSections] = useState({});
    const [stats, setStats] = useState({ llm_calls: 0, tool_calls: 0, tokens: { input: 0, output: 0 }, elapsed: 0 });
    const [isConnected, setIsConnected] = useState(false);
    const [connectionState, setConnectionState] = useState('idle');
    const [rating, setRating] = useState(null);
    const [error, setError] = useState(null);
    const [isComplete, setIsComplete] = useState(false);

    const wsRef = useRef(null);
    const pingRef = useRef(null);
    const reconnectTimerRef = useRef(null);
    const activeRunIdRef = useRef(null);
    const hasStartedRef = useRef(false);
    const lastSeqRef = useRef(0);
    const reconnectAttemptsRef = useRef(0);
    const manualCloseRef = useRef(false);
    const completedRef = useRef(false);
    const receivedErrorRef = useRef(false);

    const clearTimers = useCallback(() => {
        if (pingRef.current) {
            clearInterval(pingRef.current);
            pingRef.current = null;
        }
        if (reconnectTimerRef.current) {
            clearTimeout(reconnectTimerRef.current);
            reconnectTimerRef.current = null;
        }
    }, []);

    const closeSocket = useCallback((sendCancel = false) => {
        if (wsRef.current) {
            const oldWs = wsRef.current;
            oldWs._superseded = true;
            if (sendCancel && oldWs.readyState === WebSocket.OPEN) {
                try {
                    oldWs.send(JSON.stringify({ type: 'cancel' }));
                } catch {
                    // ignore cancel send failure while closing
                }
            }
            try {
                oldWs.close();
            } catch {
                // ignore close errors on stale socket
            }
            wsRef.current = null;
        }
    }, []);

    const disconnect = useCallback(() => {
        manualCloseRef.current = true;
        activeRunIdRef.current = null;
        clearTimers();
        closeSocket(true);
        setIsConnected(false);
        setConnectionState('idle');
    }, [clearTimers, closeSocket]);

    useEffect(() => () => disconnect(), [disconnect]);

    const connect = useCallback((config) => {
        clearTimers();
        closeSocket(true);

        const runId = generateRunId();
        activeRunIdRef.current = runId;
        hasStartedRef.current = false;
        lastSeqRef.current = 0;
        reconnectAttemptsRef.current = 0;
        manualCloseRef.current = false;
        completedRef.current = false;
        receivedErrorRef.current = false;

        setIsConnected(false);
        setConnectionState('connecting');
        setError(null);
        setRating(null);
        setMessages([]);
        setAgentStatuses({});
        setReportSections({});
        setStats({ llm_calls: 0, tool_calls: 0, tokens: { input: 0, output: 0 }, elapsed: 0 });
        setIsComplete(false);

        const analysisRequest = {
            ticker: config.ticker,
            analysis_date: config.date,
            output_language: config.language === 'Custom' ? config.customLanguage : config.language,
            analysts: config.analysts,
            research_depth: config.depth,
            llm_provider: config.provider,
            backend_url: config.provider === 'OpenAI-compatible' ? config.customUrl : null,
            quick_think_llm: config.quickModel,
            deep_think_llm: config.deepModel,
            api_key: config.apiKey,
            google_thinking_level: config.providerConfig?.mode,
            openai_reasoning_effort: config.providerConfig?.effort,
            anthropic_effort: config.providerConfig?.effort,
            run_id: runId,
        };

        const openSocket = () => {
            if (manualCloseRef.current || completedRef.current || receivedErrorRef.current || activeRunIdRef.current !== runId) {
                return;
            }

            const ws = new WebSocket(getWsUrl());
            ws._superseded = false;
            wsRef.current = ws;

            ws.onopen = () => {
                if (ws._superseded || manualCloseRef.current || activeRunIdRef.current !== runId) {
                    ws._superseded = true;
                    try { ws.close(); } catch { /* ignore */ }
                    return;
                }

                if (reconnectTimerRef.current) {
                    clearTimeout(reconnectTimerRef.current);
                    reconnectTimerRef.current = null;
                }

                setIsConnected(true);
                setConnectionState('connected');

                if (pingRef.current) {
                    clearInterval(pingRef.current);
                }
                // Client-side heartbeat ping every 15s to maintain active tunnel through proxies/Render
                pingRef.current = setInterval(() => {
                    if (ws.readyState === WebSocket.OPEN) {
                        try {
                            ws.send(JSON.stringify({ type: 'ping' }));
                        } catch {
                            // ignore ping send errors
                        }
                    }
                }, 15000);

                if (!hasStartedRef.current) {
                    hasStartedRef.current = true;
                    ws.send(JSON.stringify(analysisRequest));
                } else {
                    ws.send(JSON.stringify({
                        action: 'resume',
                        run_id: runId,
                        last_seq: lastSeqRef.current,
                    }));
                }
            };

            ws.onmessage = (event) => {
                if (ws._superseded || activeRunIdRef.current !== runId) {
                    return;
                }
                try {
                    const payload = JSON.parse(event.data);
                    reconnectAttemptsRef.current = 0;

                    const seq = typeof payload.seq === 'number' ? payload.seq : null;
                    if (seq !== null) {
                        if (seq <= lastSeqRef.current) {
                            return;
                        }
                        lastSeqRef.current = seq;
                    }

                    switch (payload.type) {
                        case 'status':
                        case 'pong':
                            break;
                        case 'agent_update':
                            setAgentStatuses(prev => ({
                                ...prev,
                                [payload.data.agent]: payload.data.status,
                            }));
                            break;
                        case 'report_section':
                            setReportSections(prev => ({
                                ...prev,
                                [payload.data.section]: payload.data.content,
                            }));
                            break;
                        case 'message':
                        case 'tool_call':
                            setMessages(prev => [...prev, { ...payload.data, msgType: payload.type }]);
                            break;
                        case 'stats':
                            setStats(payload.data);
                            break;
                        case 'complete':
                            completedRef.current = true;
                            clearTimers();
                            if (payload.data.sections) {
                                setReportSections(prev => ({ ...prev, ...payload.data.sections }));
                            }
                            setRating(payload.data.rating);
                            setIsComplete(true);
                            break;
                        case 'error':
                            receivedErrorRef.current = true;
                            clearTimers();
                            setError(payload.data?.message || 'Analysis failed with an unexpected error.');
                            setConnectionState('error');
                            break;
                        default:
                            break;
                    }
                } catch (err) {
                    console.error('Failed to parse ws message', err);
                }
            };

            ws.onerror = () => {
                // onclose always follows onerror; let onclose handle reconnect vs terminal error cleanly
            };

            ws.onclose = (event) => {
                if (wsRef.current === ws) {
                    if (pingRef.current) {
                        clearInterval(pingRef.current);
                        pingRef.current = null;
                    }
                }
                if (ws._superseded || manualCloseRef.current || activeRunIdRef.current !== runId) {
                    return;
                }

                setIsConnected(false);
                if (completedRef.current || receivedErrorRef.current) {
                    return;
                }

                const attempt = reconnectAttemptsRef.current;
                if (attempt < RECONNECT_DELAYS_MS.length) {
                    const delay = RECONNECT_DELAYS_MS[attempt];
                    reconnectAttemptsRef.current = attempt + 1;
                    setConnectionState('reconnecting');
                    reconnectTimerRef.current = setTimeout(() => {
                        reconnectTimerRef.current = null;
                        openSocket();
                    }, delay);
                    return;
                }

                setConnectionState('disconnected');
                const codePart = event?.code ? `code ${event.code}` : 'unexpected close';
                const reasonPart = event?.reason ? `: ${event.reason}` : '';
                setError(prev => prev || `WebSocket connection closed (${codePart}${reasonPart}). Reconnect failed — verify backend server status, memory limits, or VITE_API_URL.`);
            };
        };

        openSocket();
    }, [clearTimers, closeSocket]);

    return { messages, agentStatuses, reportSections, stats, isConnected, connectionState, rating, error, isComplete, connect, disconnect };
};
