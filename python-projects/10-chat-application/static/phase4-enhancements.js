/**
 * Phase 4 Enhancements
 * Provider selection, system prompts, and UX improvements
 */

// Model options for each provider
const PROVIDER_MODELS = {
    'ollama': [
        { value: 'llama3.2:3b', label: 'Llama 3.2 3B (Fast)' },
        { value: 'llama3.2:1b', label: 'Llama 3.2 1B (Fastest)' },
        { value: 'phi3:mini', label: 'Phi-3 Mini' },
        { value: 'gemma2:2b', label: 'Gemma 2 2B' }
    ],
    'openai': [
        { value: 'gpt-4o-mini', label: 'GPT-4o Mini (Recommended)' },
        { value: 'gpt-4o', label: 'GPT-4o' },
        { value: 'gpt-3.5-turbo', label: 'GPT-3.5 Turbo' }
    ],
    'anthropic': [
        { value: 'claude-3-5-sonnet-20241022', label: 'Claude 3.5 Sonnet (Recommended)' },
        { value: 'claude-3-haiku-20240307', label: 'Claude 3 Haiku (Fast)' }
    ]
};

// Modal Manager
class ModalManager {
    constructor() {
        this.setupModals();
    }

    setupModals() {
        // New conversation modal
        this.setupNewConversationModal();

        // Settings modal
        this.setupSettingsModal();
    }

    setupNewConversationModal() {
        const modal = document.getElementById('new-conversation-modal');
        const providerSelect = document.getElementById('new-conv-provider');
        const modelSelect = document.getElementById('new-conv-model');
        const closeBtn = document.getElementById('new-conv-close');
        const cancelBtn = document.getElementById('new-conv-cancel');
        const createBtn = document.getElementById('new-conv-create');

        // Provider change updates model options
        providerSelect.addEventListener('change', () => {
            this.updateModelOptions(providerSelect.value, modelSelect);
        });

        // Initialize model options
        this.updateModelOptions(providerSelect.value, modelSelect);

        // Close handlers
        closeBtn.addEventListener('click', () => this.closeModal(modal));
        cancelBtn.addEventListener('click', () => this.closeModal(modal));

        // Create handler
        createBtn.addEventListener('click', async () => {
            await this.handleCreateConversation();
        });

        // Click outside to close
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                this.closeModal(modal);
            }
        });
    }

    setupSettingsModal() {
        const modal = document.getElementById('settings-modal');
        const providerSelect = document.getElementById('settings-provider');
        const modelSelect = document.getElementById('settings-model');
        const closeBtn = document.getElementById('settings-close');
        const cancelBtn = document.getElementById('settings-cancel');
        const saveBtn = document.getElementById('settings-save');

        // Provider change updates model options
        providerSelect.addEventListener('change', () => {
            this.updateModelOptions(providerSelect.value, modelSelect);
        });

        // Close handlers
        closeBtn.addEventListener('click', () => this.closeModal(modal));
        cancelBtn.addEventListener('click', () => this.closeModal(modal));

        // Save handler
        saveBtn.addEventListener('click', async () => {
            await this.handleSaveSettings();
        });

        // Click outside to close
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                this.closeModal(modal);
            }
        });
    }

    updateModelOptions(provider, modelSelect) {
        const models = PROVIDER_MODELS[provider] || [];
        modelSelect.innerHTML = '';

        models.forEach(model => {
            const option = document.createElement('option');
            option.value = model.value;
            option.textContent = model.label;
            modelSelect.appendChild(option);
        });
    }

    openModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.style.display = 'flex';
        }
    }

    closeModal(modal) {
        if (typeof modal === 'string') {
            modal = document.getElementById(modal);
        }
        if (modal) {
            modal.style.display = 'none';
        }
    }

    async handleCreateConversation() {
        const provider = document.getElementById('new-conv-provider').value;
        const model = document.getElementById('new-conv-model').value;
        const systemPrompt = document.getElementById('new-conv-system-prompt').value.trim();

        const payload = {
            llm_provider: provider,
            llm_model: model
        };

        if (systemPrompt) {
            payload.system_prompt = systemPrompt;
        }

        try {
            const response = await fetch('/api/conversations', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify(payload)
            });

            if (response.ok) {
                const conversation = await response.json();

                // Reload conversations and select new one
                await window.chatApp.conversationManager.loadConversations();
                await window.chatApp.conversationManager.selectConversation(conversation.id);

                // Close modal and reset
                this.closeModal('new-conversation-modal');
                document.getElementById('new-conv-system-prompt').value = '';
            } else {
                const error = await response.json();
                alert('Error creating conversation: ' + (error.detail || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error creating conversation:', error);
            alert('Failed to create conversation');
        }
    }

    openSettingsModal(conversation) {
        // Populate current values
        document.getElementById('settings-title').value = conversation.title || '';
        document.getElementById('settings-provider').value = conversation.llm_provider || 'ollama';

        // Update model options for selected provider
        this.updateModelOptions(
            conversation.llm_provider || 'ollama',
            document.getElementById('settings-model')
        );

        document.getElementById('settings-model').value = conversation.llm_model || '';
        document.getElementById('settings-system-prompt').value = conversation.system_prompt || '';

        this.openModal('settings-modal');
    }

    async handleSaveSettings() {
        if (!window.chatApp.currentConversation) {
            return;
        }

        const conversationId = window.chatApp.currentConversation.id;
        const title = document.getElementById('settings-title').value.trim();
        const provider = document.getElementById('settings-provider').value;
        const model = document.getElementById('settings-model').value;
        const systemPrompt = document.getElementById('settings-system-prompt').value.trim();

        const payload = {};
        if (title) payload.title = title;
        if (provider) payload.llm_provider = provider;
        if (model) payload.llm_model = model;
        if (systemPrompt !== null) payload.system_prompt = systemPrompt;

        try {
            const response = await fetch(`/api/conversations/${conversationId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify(payload)
            });

            if (response.ok) {
                const updated = await response.json();

                // Update current conversation
                window.chatApp.currentConversation = updated;
                document.getElementById('conversation-title').textContent = updated.title || 'New Chat';

                // Reload conversations list
                await window.chatApp.conversationManager.loadConversations();

                // Close modal
                this.closeModal('settings-modal');

                // Show success feedback
                this.showToast('Settings saved successfully');
            } else {
                const error = await response.json();
                alert('Error saving settings: ' + (error.detail || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error saving settings:', error);
            alert('Failed to save settings');
        }
    }

    showToast(message) {
        // Simple toast notification
        const toast = document.createElement('div');
        toast.className = 'toast';
        toast.textContent = message;
        toast.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #667eea;
            color: white;
            padding: 15px 20px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
            z-index: 2000;
            animation: slideIn 0.3s ease;
        `;

        document.body.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 2000);
    }
}

// Initialize Phase 4 features when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    // Wait for chatApp to be initialized
    setTimeout(() => {
        if (window.chatApp) {
            window.modalManager = new ModalManager();

            // Override new conversation button to show modal
            const newConvBtn = document.getElementById('new-conversation-btn');
            newConvBtn.onclick = () => {
                window.modalManager.openModal('new-conversation-modal');
            };

            // Add settings button handler
            const settingsBtn = document.getElementById('settings-btn');
            settingsBtn.onclick = () => {
                if (window.chatApp.currentConversation) {
                    window.modalManager.openSettingsModal(window.chatApp.currentConversation);
                }
            };

            // Show settings button when conversation is selected
            const originalSelectConversation = window.chatApp.conversationManager.selectConversation.bind(
                window.chatApp.conversationManager
            );

            window.chatApp.conversationManager.selectConversation = async function(conversationId) {
                await originalSelectConversation(conversationId);
                document.getElementById('settings-btn').style.display = 'block';
            };

            console.log('Phase 4 enhancements loaded');
        }
    }, 100);
});

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }

    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);
