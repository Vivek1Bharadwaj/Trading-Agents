import axios from 'axios';
import { PROVIDERS } from './constants';

const getBaseUrl = () => {
    if (import.meta.env.VITE_API_URL) {
        return import.meta.env.VITE_API_URL;
    }
    // When served from the backend (e.g. Render, production, or local host)
    if (typeof window !== 'undefined' && window.location && window.location.origin) {
        return window.location.origin;
    }
    return 'http://localhost:8000';
};

const API_URL = getBaseUrl();

export const getModels = async (provider) => {
    try {
        const response = await axios.get(`${API_URL}/api/models/${provider}`);
        return {
            quick: response.data.quick || [],
            deep: response.data.deep || []
        };
    } catch (e) {
        console.error("Failed to fetch models", e);
        return { quick: [], deep: [] };
    }
};

export const getProviders = async () => {
    try {
        const response = await axios.get(`${API_URL}/api/providers`);
        if (response.data && response.data.length > 0) {
            return response.data;
        }
        return PROVIDERS;
    } catch (e) {
        console.error("Failed to fetch providers, falling back to static list", e);
        return PROVIDERS;
    }
};

export const validateTicker = (ticker) => {
    const regex = /^[a-zA-Z0-9.\-^=_]+$/;
    return regex.test(ticker);
};

export const isCrypto = (ticker) => {
    if(!ticker) return false;
    const upper = ticker.toUpperCase();
    return upper.endsWith('-USD') || upper.endsWith('-USDT') || upper.endsWith('-USDC') || upper.endsWith('-BTC') || upper.endsWith('-ETH');
};

export const getDefaults = () => {
    return {
        ticker: '',
        date: new Date().toISOString().split('T')[0],
        language: 'English',
        customLanguage: '',
        analysts: ['Market Analyst', 'Sentiment Analyst', 'News Analyst', 'Fundamentals Analyst'],
        depth: 'Medium',
        provider: 'openai', // Use lower case key default
        apiKey: '',
        customUrl: '',
        quickModel: '',
        deepModel: '',
        providerConfig: {}
    };
};
