/**
 * Chat Application Frontend
 * Vanilla JavaScript with class-based architecture
 */

class ChatApp {
    constructor() {
        this.currentUser = null;
        this.currentConversation = null;
        this.websocket = null;

        this.authManager = new AuthManager(this);
        this.conversationManager = new ConversationManager(this);
        this.chatView = new ChatView(this);
        this.authView = new AuthView(this);

        this.init();
    }

    async init() {
        // Check authentication
        try {
            const response = await fetch('/api/auth/me', {
                credentials: 'include'
            });

            if (response.ok) {
                this.currentUser = await response.json();
                this.showChatInterface();
                await this.conversationManager.loadConversations();
            } else {
                this.showAuthInterface();
            }
        } catch (error) {
            console.error('Init error:', error);
            this.showAuthInterface();
        }
    }

    showAuthInterface() {
        document.getElementById('auth-view').style.display = 'flex';
        document.getElementById('chat-view').style.display = 'none';
    }

    showChatInterface() {
        document.getElementById('auth-view').style.display = 'none';
        document.getElementById('chat-view').style.display = 'flex';

        // Update user info
        document.getElementById('current-username').textContent = this.currentUser.username;
    }

    async logout() {
        await fetch('/api/auth/logout', {
            method: 'POST',
            credentials: 'include'
        });

        this.currentUser = null;
        this.currentConversation = null;

        if (this.websocket) {
            this.websocket.close();
            this.websocket = null;
        }

        this.showAuthInterface();
    }
}


class AuthManager {
    constructor(app) {
        this.app = app;
    }

    async register(username, email, password) {
        const response = await fetch('/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ username, email, password })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Registration failed');
        }

        this.app.currentUser = await response.json();
        this.app.showChatInterface();
        await this.app.conversationManager.loadConversations();
    }

    async login(username, password) {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ username, password })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Login failed');
        }

        this.app.currentUser = await response.json();
        this.app.showChatInterface();
        await this.app.conversationManager.loadConversations();
    }
}


class ConversationManager {
    constructor(app) {
        this.app = app;
        this.conversations = [];
    }

    async loadConversations() {
        const response = await fetch('/api/conversations?limit=100', {
            credentials: 'include'
        });

        if (response.ok) {
            const data = await response.json();
            this.conversations = data.conversations;
            this.renderConversationList();
        }
    }

    async createConversation() {
        const response = await fetch('/api/conversations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ llm_provider: 'ollama' })
        });

        if (response.ok) {
            const conversation = await response.json();
            this.conversations.unshift(conversation);
            this.renderConversationList();
            await this.selectConversation(conversation.id);
        }
    }

    async selectConversation(conversationId) {
        const response = await fetch(`/api/conversations/${conversationId}`, {
            credentials: 'include'
        });

        if (response.ok) {
            this.app.currentConversation = await response.json();
            document.getElementById('conversation-title').textContent =
                this.app.currentConversation.title || 'New Chat';
            this.app.chatView.renderMessages();
            this.app.chatView.connectWebSocket();
            this.renderConversationList();  // Update active state
        }
    }

    async deleteConversation(conversationId) {
        if (!confirm('Delete this conversation?')) {
            return;
        }

        await fetch(`/api/conversations/${conversationId}`, {
            method: 'DELETE',
            credentials: 'include'
        });

        this.conversations = this.conversations.filter(c => c.id !== conversationId);
        this.renderConversationList();

        if (this.app.currentConversation?.id === conversationId) {
            this.app.currentConversation = null;
            this.app.chatView.clear();
            document.getElementById('conversation-title').textContent = 'Select a conversation';
        }
    }

    renderConversationList() {
        const list = document.getElementById('conversation-list');
        list.innerHTML = '';

        this.conversations.forEach(conv => {
            const item = document.createElement('div');
            item.className = 'conversation-item';
            if (this.app.currentConversation?.id === conv.id) {
                item.classList.add('active');
            }

            item.innerHTML = `
                <div class="conversation-title">${this.escapeHtml(conv.title || 'New Chat')}</div>
                <button class="delete-btn" data-id="${conv.id}">×</button>
            `;

            item.addEventListener('click', (e) => {
                if (!e.target.classList.contains('delete-btn')) {
                    this.selectConversation(conv.id);
                }
            });

            item.querySelector('.delete-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                this.deleteConversation(conv.id);
            });

            list.appendChild(item);
        });
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}


class ChatView {
    constructor(app) {
        this.app = app;
        this.setupEventListeners();
    }

    setupEventListeners() {
        // New conversation button
        document.getElementById('new-conversation-btn').addEventListener('click', () => {
            this.app.conversationManager.createConversation();
        });

        // Logout button
        document.getElementById('logout-btn').addEventListener('click', () => {
            this.app.logout();
        });

        // Send button
        document.getElementById('send-button').addEventListener('click', () => {
            this.sendMessage();
        });

        // Enter key to send (Shift+Enter for newline)
        document.getElementById('user-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
    }

    connectWebSocket() {
        if (!this.app.currentConversation) return;

        if (this.app.websocket) {
            this.app.websocket.close();
        }

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.app.websocket = new WebSocket(
            `${protocol}//${window.location.host}/ws/${this.app.currentConversation.id}`
        );

        this.app.websocket.onopen = () => {
            console.log('WebSocket connected');
        };

        this.app.websocket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleWebSocketMessage(data);
        };

        this.app.websocket.onerror = (error) => {
            console.error('WebSocket error:', error);
        };

        this.app.websocket.onclose = () => {
            console.log('WebSocket closed');
        };
    }

    handleWebSocketMessage(data) {
        if (data.type === 'token') {
            this.appendTokenToLastMessage(data.token);
        } else if (data.type === 'done') {
            this.finishStreaming();
            // Reload conversation title if it was updated
            this.app.conversationManager.loadConversations();
        } else if (data.type === 'error') {
            this.showError(data.error);
            this.finishStreaming();
        }
    }

    sendMessage() {
        const input = document.getElementById('user-input');
        const content = input.value.trim();

        if (!content || !this.app.websocket || !this.app.currentConversation) {
            return;
        }

        // Add user message to UI
        this.addMessage('user', content);
        input.value = '';

        // Create placeholder for assistant response
        this.addMessage('assistant', '', true);

        // Send via WebSocket
        this.app.websocket.send(JSON.stringify({
            type: 'message',
            content: content
        }));
    }

    renderMessages() {
        const container = document.getElementById('message-container');
        container.innerHTML = '';

        if (!this.app.currentConversation) return;

        this.app.currentConversation.messages.forEach(msg => {
            this.addMessage(msg.role, msg.content);
        });
    }

    addMessage(role, content, streaming = false) {
        const container = document.getElementById('message-container');
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}-message${streaming ? ' streaming' : ''}`;
        messageDiv.innerHTML = `
            <div class="message-role">${role === 'user' ? 'You' : 'Assistant'}</div>
            <div class="message-content">${this.escapeHtml(content)}</div>
        `;

        container.appendChild(messageDiv);
        container.scrollTop = container.scrollHeight;

        return messageDiv;
    }

    appendTokenToLastMessage(token) {
        const container = document.getElementById('message-container');
        const lastMessage = container.querySelector('.message.streaming');

        if (lastMessage) {
            const contentDiv = lastMessage.querySelector('.message-content');
            contentDiv.textContent += token;
            container.scrollTop = container.scrollHeight;
        }
    }

    finishStreaming() {
        const container = document.getElementById('message-container');
        const streamingMessage = container.querySelector('.message.streaming');

        if (streamingMessage) {
            streamingMessage.classList.remove('streaming');
        }
    }

    showError(error) {
        const container = document.getElementById('message-container');
        const errorDiv = document.createElement('div');
        errorDiv.className = 'message error-message';
        errorDiv.innerHTML = `
            <div class="message-role">Error</div>
            <div class="message-content">${this.escapeHtml(error)}</div>
        `;
        container.appendChild(errorDiv);
        container.scrollTop = container.scrollHeight;
    }

    clear() {
        document.getElementById('message-container').innerHTML = '';
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}


class AuthView {
    constructor(app) {
        this.app = app;
        this.setupEventListeners();
    }

    setupEventListeners() {
        // Toggle between login and register
        document.getElementById('show-register').addEventListener('click', (e) => {
            e.preventDefault();
            document.getElementById('login-form').style.display = 'none';
            document.getElementById('register-form').style.display = 'block';
        });

        document.getElementById('show-login').addEventListener('click', (e) => {
            e.preventDefault();
            document.getElementById('register-form').style.display = 'none';
            document.getElementById('login-form').style.display = 'block';
        });

        // Login
        document.getElementById('login-submit').addEventListener('click', async () => {
            const username = document.getElementById('login-username').value.trim();
            const password = document.getElementById('login-password').value;

            if (!username || !password) {
                alert('Please enter username and password');
                return;
            }

            try {
                await this.app.authManager.login(username, password);
            } catch (error) {
                alert(error.message);
            }
        });

        // Register
        document.getElementById('register-submit').addEventListener('click', async () => {
            const username = document.getElementById('register-username').value.trim();
            const email = document.getElementById('register-email').value.trim();
            const password = document.getElementById('register-password').value;

            if (!username || !email || !password) {
                alert('Please fill in all fields');
                return;
            }

            try {
                await this.app.authManager.register(username, email, password);
            } catch (error) {
                alert(error.message);
            }
        });

        // Enter key support
        document.getElementById('login-password').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                document.getElementById('login-submit').click();
            }
        });

        document.getElementById('register-password').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                document.getElementById('register-submit').click();
            }
        });
    }
}


// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    window.chatApp = new ChatApp();
});
