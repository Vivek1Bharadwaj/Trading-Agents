import React, { useState, useEffect } from 'react';
import { LANGUAGES, ANALYSTS, DEPTH_OPTIONS } from '../utils/constants';
import { isCrypto, validateTicker, getModels, getProviders } from '../utils/api';
import { ChevronRight, ChevronLeft, Check, AlertCircle } from 'lucide-react';

export default function SetupWizard({ configHook, onStart }) {
    const { config, updateConfig, step, nextStep, prevStep } = configHook;
    const [models, setModels] = useState({ quick: [], deep: [] });
    const [providers, setProviders] = useState([]);
    const [error, setError] = useState('');

    useEffect(() => {
        getProviders().then(data => {
            if (data.length > 0) {
                setProviders(data);
                if (!config.provider) {
                    updateConfig('provider', data[0].key);
                }
            }
        });
    }, []);

    useEffect(() => {
        if (step === 6 && config.provider) {
            getModels(config.provider).then(data => {
                setModels(data);
                if (!config.quickModel && data.quick.length > 0) {
                    updateConfig('quickModel', data.quick[0].value);
                }
                if (!config.deepModel && data.deep.length > 0) {
                    updateConfig('deepModel', data.deep[0].value);
                }
            });
        }
    }, [step, config.provider]);

    const handleNext = () => {
        setError('');
        if (step === 1) {
            if (!config.ticker) return setError("Ticker is required");
            if (!validateTicker(config.ticker)) return setError("Invalid ticker format");
        }
        if (step === 3 && config.analysts.length === 0) {
            return setError("Select at least one analyst");
        }
        nextStep();
    };

    const renderStep = () => {
        switch(step) {
            case 1:
                return (
                    <div>
                        <h3>Step 1: Asset Selection</h3>
                        <label className="label" style={{ marginTop: '1rem' }}>Ticker Symbol</label>
                        <input 
                            className="input-field" 
                            value={config.ticker}
                            onChange={(e) => updateConfig('ticker', e.target.value.toUpperCase())}
                            placeholder="e.g. AAPL, BTC-USD"
                        />
                        {isCrypto(config.ticker) && (
                            <p style={{ color: 'var(--accent)', fontSize: '0.875rem', marginTop: '0.5rem' }}>
                                Crypto detected! Fundamentals Analyst will be disabled.
                            </p>
                        )}
                        <label className="label" style={{ marginTop: '1rem' }}>Analysis Date</label>
                        <input 
                            type="date"
                            className="input-field" 
                            value={config.date}
                            onChange={(e) => updateConfig('date', e.target.value)}
                            max={new Date().toISOString().split('T')[0]}
                        />
                    </div>
                );
            case 2:
                return (
                    <div>
                        <h3>Step 2: Output Language</h3>
                        <div className="radio-group" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                            {LANGUAGES.map(lang => (
                                <label key={lang} className={`radio-label ${config.language === lang ? 'selected' : ''}`} style={{ padding: '0.75rem' }}>
                                    <input 
                                        type="radio" 
                                        name="language" 
                                        checked={config.language === lang}
                                        onChange={() => updateConfig('language', lang)}
                                        style={{ display: 'none' }}
                                    />
                                    <span style={{ fontSize: '0.875rem' }}>{lang}</span>
                                </label>
                            ))}
                        </div>
                        {config.language === 'Custom' && (
                            <input 
                                className="input-field"
                                style={{ marginTop: '1rem' }}
                                value={config.customLanguage}
                                onChange={(e) => updateConfig('customLanguage', e.target.value)}
                                placeholder="Enter custom language..."
                            />
                        )}
                    </div>
                );
            case 3:
                return (
                    <div>
                        <h3>Step 3: Analysts Team</h3>
                        <div className="checkbox-group">
                            {ANALYSTS.map(analyst => {
                                const disabled = isCrypto(config.ticker) && analyst.id === 'Fundamentals Analyst';
                                const selected = config.analysts.includes(analyst.id);
                                return (
                                    <label key={analyst.id} className={`checkbox-label ${selected ? 'selected' : ''}`} style={{ opacity: disabled ? 0.5 : 1 }}>
                                        <input 
                                            type="checkbox" 
                                            disabled={disabled}
                                            checked={selected && !disabled}
                                            onChange={(e) => {
                                                if (e.target.checked) {
                                                    updateConfig('analysts', [...config.analysts, analyst.id]);
                                                } else {
                                                    updateConfig('analysts', config.analysts.filter(a => a !== analyst.id));
                                                }
                                            }}
                                            style={{ display: 'none' }}
                                        />
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                            <div style={{ 
                                                width: 20, height: 20, border: '1px solid var(--border-color)', 
                                                borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                backgroundColor: selected ? 'var(--accent)' : 'transparent'
                                            }}>
                                                {selected && <Check size={14} color="white" />}
                                            </div>
                                            {analyst.label}
                                        </div>
                                    </label>
                                );
                            })}
                        </div>
                    </div>
                );
            case 4:
                return (
                    <div>
                        <h3>Step 4: Research Depth</h3>
                        <div className="radio-group">
                            {DEPTH_OPTIONS.map(opt => (
                                <label key={opt.id} className={`radio-label ${config.depth === opt.id ? 'selected' : ''}`}>
                                    <input 
                                        type="radio" 
                                        name="depth" 
                                        checked={config.depth === opt.id}
                                        onChange={() => updateConfig('depth', opt.id)}
                                        style={{ display: 'none' }}
                                    />
                                    <div>
                                        <div style={{ fontWeight: 600 }}>{opt.label}</div>
                                        <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>{opt.desc}</div>
                                    </div>
                                </label>
                            ))}
                        </div>
                    </div>
                );
            case 5:
                const activeProvider = providers.find(p => p.key === config.provider);
                const needsKey = activeProvider && activeProvider.env_var;
                return (
                    <div>
                        <h3>Step 5: LLM Provider</h3>
                        <select 
                            className="input-field" 
                            value={config.provider}
                            onChange={(e) => updateConfig('provider', e.target.value)}
                        >
                            {providers.map(p => <option key={p.key} value={p.key}>{p.display}</option>)}
                        </select>

                        {needsKey && (
                            <div style={{ marginTop: '1rem' }}>
                                <label className="label">API Key ({activeProvider.env_var})</label>
                                <input 
                                    type="password"
                                    className="input-field" 
                                    value={config.apiKey}
                                    onChange={(e) => updateConfig('apiKey', e.target.value)}
                                    placeholder="Enter API Key"
                                />
                            </div>
                        )}
                        {config.provider === 'openai_compatible' && (
                            <div style={{ marginTop: '1rem' }}>
                                <label className="label">Base URL</label>
                                <input 
                                    type="text"
                                    className="input-field" 
                                    value={config.customUrl}
                                    onChange={(e) => updateConfig('customUrl', e.target.value)}
                                    placeholder="https://api.example.com/v1"
                                />
                            </div>
                        )}
                    </div>
                );
            case 6:
                return (
                    <div>
                        <h3>Step 6: Model Selection</h3>
                        <label className="label" style={{ marginTop: '1rem' }}>Quick-Thinking Model</label>
                        <select 
                            className="input-field" 
                            value={config.quickModel}
                            onChange={(e) => updateConfig('quickModel', e.target.value)}
                        >
                            <option value="">Select a model...</option>
                            {models.quick.map(m => <option key={m.value} value={m.value}>{m.display}</option>)}
                            <option value="custom">Custom...</option>
                        </select>
                        {config.quickModel === 'custom' && (
                            <input className="input-field" style={{marginTop: '0.5rem'}} placeholder="Enter model ID" onChange={(e) => updateConfig('quickModel', e.target.value)} />
                        )}

                        <label className="label" style={{ marginTop: '1rem' }}>Deep-Thinking Model</label>
                        <select 
                            className="input-field" 
                            value={config.deepModel}
                            onChange={(e) => updateConfig('deepModel', e.target.value)}
                        >
                            <option value="">Select a model...</option>
                            {models.deep.map(m => <option key={m.value} value={m.value}>{m.display}</option>)}
                            <option value="custom">Custom...</option>
                        </select>
                        {config.deepModel === 'custom' && (
                            <input className="input-field" style={{marginTop: '0.5rem'}} placeholder="Enter model ID" onChange={(e) => updateConfig('deepModel', e.target.value)} />
                        )}
                    </div>
                );
            case 7:
                return (
                    <div>
                        <h3>Step 7: Provider-Specific Config</h3>
                        {config.provider === 'openai' && (
                            <div>
                                <label className="label">Reasoning Effort</label>
                                <select className="input-field" onChange={(e) => updateConfig('providerConfig', { effort: e.target.value })}>
                                    <option value="low">Low</option>
                                    <option value="medium">Medium</option>
                                    <option value="high">High</option>
                                </select>
                            </div>
                        )}
                        {config.provider === 'google' && (
                            <div>
                                <label className="label">Thinking Mode</label>
                                <select className="input-field" onChange={(e) => updateConfig('providerConfig', { mode: e.target.value })}>
                                    <option value="high">Enable Thinking</option>
                                    <option value="minimal">Minimal/Disable</option>
                                </select>
                            </div>
                        )}
                        {config.provider === 'anthropic' && (
                            <div>
                                <label className="label">Effort Level</label>
                                <select className="input-field" onChange={(e) => updateConfig('providerConfig', { effort: e.target.value })}>
                                    <option value="low">Low</option>
                                    <option value="medium">Medium</option>
                                    <option value="high">High</option>
                                </select>
                            </div>
                        )}
                        {!['openai', 'google', 'anthropic'].includes(config.provider) && (
                            <div style={{ color: 'var(--text-muted)' }}>No provider-specific config needed.</div>
                        )}
                    </div>
                );
            case 8:
                const activeProv = providers.find(p => p.key === config.provider)?.display || config.provider;
                return (
                    <div>
                        <h3>Step 8: Review & Launch</h3>
                        <div style={{ backgroundColor: 'var(--bg-dark)', padding: '1.5rem', borderRadius: '0.5rem', marginTop: '1rem' }}>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                                <div><span style={{ color: 'var(--text-muted)' }}>Ticker:</span> {config.ticker}</div>
                                <div><span style={{ color: 'var(--text-muted)' }}>Date:</span> {config.date}</div>
                                <div><span style={{ color: 'var(--text-muted)' }}>Language:</span> {config.language === 'Custom' ? config.customLanguage : config.language}</div>
                                <div><span style={{ color: 'var(--text-muted)' }}>Depth:</span> {config.depth}</div>
                                <div><span style={{ color: 'var(--text-muted)' }}>Provider:</span> {activeProv}</div>
                                <div><span style={{ color: 'var(--text-muted)' }}>Analysts:</span> {config.analysts.length} selected</div>
                            </div>
                        </div>
                    </div>
                );
            default:
                return null;
        }
    };

    return (
        <div className="setup-wizard glass-panel">
            <div className="step-indicator">Step {step} of 8</div>
            {error && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--bearish)', marginBottom: '1rem', padding: '0.5rem', backgroundColor: 'rgba(239, 68, 68, 0.1)', borderRadius: '0.5rem' }}>
                    <AlertCircle size={16} /> {error}
                </div>
            )}
            
            <div style={{ minHeight: '300px' }}>
                {renderStep()}
            </div>

            <div className="wizard-footer">
                <button 
                    className={`btn-secondary ${step === 1 ? 'btn-disabled' : ''}`} 
                    onClick={prevStep}
                    disabled={step === 1}
                >
                    <ChevronLeft size={16} style={{ verticalAlign: 'middle', marginRight: '0.5rem' }} /> Back
                </button>
                
                {step < 8 ? (
                    <button className="btn-primary" onClick={handleNext}>
                        Next <ChevronRight size={16} style={{ verticalAlign: 'middle', marginLeft: '0.5rem' }} />
                    </button>
                ) : (
                    <button className="btn-primary" onClick={onStart}>
                        Start Analysis <ChevronRight size={16} style={{ verticalAlign: 'middle', marginLeft: '0.5rem' }} />
                    </button>
                )}
            </div>
        </div>
    );
}
