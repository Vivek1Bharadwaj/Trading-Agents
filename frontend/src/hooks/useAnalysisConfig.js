import { useState } from 'react';
import { getDefaults } from '../utils/api';

export const useAnalysisConfig = () => {
    const [config, setConfig] = useState(getDefaults());
    const [step, setStep] = useState(1);

    const updateConfig = (key, value) => {
        setConfig(prev => ({ ...prev, [key]: value }));
    };

    const nextStep = () => setStep(s => Math.min(s + 1, 8));
    const prevStep = () => setStep(s => Math.max(s - 1, 1));
    const reset = () => {
        setConfig(getDefaults());
        setStep(1);
    };

    return { config, updateConfig, step, setStep, nextStep, prevStep, reset };
};
