import { useState, useRef, useCallback } from 'react';

const getWsUrl = () => {
    if (import.meta.env.VITE_API_URL) {
        return import.meta.env.VITE_API_URL.replace(/^http/, 'ws') + '/ws/analysis';
    }
    if (typeof window !== 'undefined' && window.location && window.location.host) {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${window.location.host}/ws/analysis`;
    }
    return 'ws://localhost:8000/ws/analysis';
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

    const connect = useCallback((config) => {
        setIsConnected(false);
        setConnectionState('connecting');
        setError(null);
        setRating(null);
        setMessages([]);
        setAgentStatuses({});
        setReportSections({});
        setStats({ llm_calls: 0, tool_calls: 0, tokens: { input: 0, output: 0 }, elapsed: 0 });
        setIsComplete(false);

        if (pingRef.current) {
            clearInterval(pingRef.current);
            pingRef.current = null;
        }
        if (wsRef.current) {
            wsRef.current._manualClose = true;
            try {
                wsRef.current.close();
            } catch (e) {
                // ignore close errors on stale socket
            }
        }

        const ws = new WebSocket(getWsUrl());
        ws._manualClose = false;
        wsRef.current = ws;

        let completed = false;
        let receivedError = false;

        ws.onopen = () => {
            setIsConnected(true);
            setConnectionState('connected');
            
            // Client-side heartbeat ping every 15s to maintain active tunnel through proxies/Render
            pingRef.current = setInterval(() => {
                if (ws.readyState === WebSocket.OPEN) {
                    try {
                        ws.send(JSON.stringify({ type: 'ping' }));
                    } catch (e) {
                        // ignore ping send errors
                    }
                }
            }, 15000);
            
            // Map frontend config state to backend AnalysisRequest schema
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
            };
            
            ws.send(JSON.stringify(analysisRequest));
        };

        ws.onmessage = (event) => {
            try {
                const payload = JSON.parse(event.data);
                switch(payload.type) {
                    case 'status':
                    case 'pong':
                        break;
                    case 'agent_update':
                        setAgentStatuses(prev => ({
                            ...prev,
                            [payload.data.agent]: payload.data.status
                        }));
                        break;
                    case 'report_section':
                        setReportSections(prev => ({
                            ...prev,
                            [payload.data.section]: payload.data.content
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
                        completed = true;
                        if (payload.data.sections) {
                            setReportSections(prev => ({ ...prev, ...payload.data.sections }));
                        }
                        setRating(payload.data.rating);
                        setIsComplete(true);
                        break;
                    case 'error':
                        receivedError = true;
                        setError(payload.data?.message || 'Analysis failed with an unexpected error.');
                        setConnectionState('error');
                        break;
                    default:
                        break;
                }
            } catch (err) {
                console.error("Failed to parse ws message", err);
            }
        };

        ws.onerror = () => {
            if (pingRef.current) {
                clearInterval(pingRef.current);
                pingRef.current = null;
            }
            if (!completed && !ws._manualClose) {
                setError(prev => prev || "WebSocket connection failed. Verify the backend server is running.");
                setConnectionState('error');
            }
        };
        ws.onclose = (event) => {
            if (pingRef.current) {
                clearInterval(pingRef.current);
                pingRef.current = null;
            }
            setIsConnected(false);
            if (!completed && !ws._manualClose) {
                setConnectionState(receivedError ? 'error' : 'disconnected');
                if (!receivedError) {
                    const reason = event?.reason ? ` (${event.reason})` : '';
                    setError(prev => prev || `WebSocket connection closed unexpectedly${reason}.`);
                }
            }
        };
    }, []);

    const disconnect = useCallback(() => {
        if (pingRef.current) {
            clearInterval(pingRef.current);
            pingRef.current = null;
        }
        if (wsRef.current) {
            wsRef.current._manualClose = true;
            wsRef.current.close();
            wsRef.current = null;
        }
        setIsConnected(false);
        setConnectionState('idle');
    }, []);

    return { messages, agentStatuses, reportSections, stats, isConnected, connectionState, rating, error, isComplete, connect, disconnect };
};
