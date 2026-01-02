const express = require('express');
const cors = require('cors');
const path = require('path');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());
app.use(express.static('public'));

app.post('/api/generate', async (req, res) => {
    const { backend, model, prompt, temperature, maxTokens } = req.body;

    if (!prompt) {
        return res.status(400).json({ error: 'Prompt is required' });
    }

    try {
        if (backend === 'ollama') {
            const result = await generateOllama(model, prompt, temperature, maxTokens);
            res.json({ text: result });
        } else {
            res.status(400).json({ error: `Unsupported backend: ${backend}` });
        }
    } catch (error) {
        console.error('Generation error:', error.message);
        res.status(500).json({ error: error.message });
    }
});

async function generateOllama(model, prompt, temperature, maxTokens) {
    const ollamaUrl = process.env.OLLAMA_API_URL || 'http://localhost:11434';

    const response = await fetch(`${ollamaUrl}/api/generate`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            model: model,
            prompt: prompt,
            stream: false,
            options: {
                temperature: temperature || 0.7,
                num_predict: maxTokens || 500
            }
        })
    });

    if (!response.ok) {
        throw new Error(`Ollama API error: ${response.statusText}`);
    }

    const data = await response.json();
    return data.response;
}

app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, '../public/index.html'));
});

app.listen(PORT, () => {
    console.log(`Prompt Playground running at http://localhost:${PORT}`);
    console.log(`Make sure Ollama is running at ${process.env.OLLAMA_API_URL || 'http://localhost:11434'}`);
});
