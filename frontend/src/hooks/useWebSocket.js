import { useState, useRef, useCallback } from 'react';

const getWsUrl = () => {
    const httpUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    return httpUrl.replace(/^http/, 'ws') + '/ws/analysis';
};

export const useWebSocket = () => {
    const [messages, setMessages] = useState([]);
    const [agentStatuses, setAgentStatuses] = useState({});
    const [reportSections, setReportSections] = useState({});
    const [stats, setStats] = useState({ llm_calls: 0, tool_calls: 0, tokens: { input: 0, output: 0 }, elapsed: 0 });
    const [isConnected, setIsConnected] = useState(false);
    const [rating, setRating] = useState(null);
    const [error, setError] = useState(null);
    const [isComplete, setIsComplete] = useState(false);

    const wsRef = useRef(null);

    const connect = useCallback((config) => {
        setIsConnected(false);
        setError(null);
        setMessages([]);
        setAgentStatuses({});
        setReportSections({});
        setIsComplete(false);

        const ws = new WebSocket(getWsUrl());
        wsRef.current = ws;

        ws.onopen = () => {
            setIsConnected(true);
            
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
                        setRating(payload.data.rating);
                        setIsComplete(true);
                        break;
                    case 'error':
                        setError(payload.data.message);
                        break;
                    default:
                        break;
                }
            } catch (err) {
                console.error("Failed to parse ws message", err);
            }
        };

        ws.onerror = () => setError("WebSocket Connection Error");
        ws.onclose = () => setIsConnected(false);
    }, []);

    const disconnect = useCallback(() => {
        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }
    }, []);

    return { messages, agentStatuses, reportSections, stats, isConnected, rating, error, isComplete, connect, disconnect };
};
