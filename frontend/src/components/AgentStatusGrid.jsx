import React from 'react';
import { Loader2, CheckCircle, Clock } from 'lucide-react';

const ALL_AGENTS = [
    { id: "Market Analyst", phase: 1 },
    { id: "Sentiment Analyst", phase: 1 },
    { id: "News Analyst", phase: 1 },
    { id: "Fundamentals Analyst", phase: 1 },
    { id: "Bull Researcher", phase: 2 },
    { id: "Bear Researcher", phase: 2 },
    { id: "Research Manager", phase: 2 },
    { id: "Trader", phase: 3 },
    { id: "Aggressive Analyst", phase: 4 },
    { id: "Conservative Analyst", phase: 4 },
    { id: "Neutral Analyst", phase: 4 },
    { id: "Portfolio Manager", phase: 5 }
];

export default function AgentStatusGrid({ statuses }) {
    const getStatusIcon = (status) => {
        if (status === 'complete') return <CheckCircle size={16} color="#10b981" />;
        if (status === 'in_progress') return <Loader2 size={16} className="animate-spin" color="#3b82f6" />;
        return <Clock size={16} color="#9ca3af" />;
    };

    return (
        <div className="agent-grid">
            {ALL_AGENTS.map(agent => {
                const status = statuses[agent.id] || 'pending';
                return (
                    <div key={agent.id} className="agent-item">
                        <span style={{ fontSize: '0.875rem' }}>{agent.id}</span>
                        <div className={`status-indicator ${status}`}>
                            {getStatusIcon(status)}
                            <span style={{ textTransform: 'capitalize' }}>
                                {status.replace('_', ' ')}
                            </span>
                        </div>
                    </div>
                );
            })}
        </div>
    );
}
