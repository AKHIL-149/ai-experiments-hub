/**
 * Text Display Enhancements
 * Markdown rendering and improved text formatting
 */

// Configure marked.js for better rendering
if (typeof marked !== 'undefined') {
    marked.setOptions({
        breaks: true,        // Convert \n to <br>
        gfm: true,           // GitHub Flavored Markdown
        headerIds: false,    // Don't add IDs to headers
        mangle: false        // Don't mangle email addresses
    });
}

// Enhanced message rendering
class MessageRenderer {
    constructor() {
        this.setupRenderer();
    }

    setupRenderer() {
        // Wait for ChatView to be available
        const checkChatView = setInterval(() => {
            if (window.chatApp && window.chatApp.chatView) {
                clearInterval(checkChatView);
                this.enhanceChatView();
            }
        }, 100);
    }

    enhanceChatView() {
        const chatView = window.chatApp.chatView;

        // Save original methods
        const originalAddMessage = chatView.addMessage.bind(chatView);
        const originalAppendToken = chatView.appendTokenToLastMessage.bind(chatView);

        // Override addMessage to render markdown
        chatView.addMessage = (role, content, streaming = false) => {
            const container = document.getElementById('message-container');
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${role}-message${streaming ? ' streaming' : ''}`;

            const roleLabel = role === 'user' ? 'You' : 'Assistant';
            const renderedContent = this.renderContent(content, role, streaming);

            messageDiv.innerHTML = `
                <div class="message-role">${roleLabel}</div>
                <div class="message-content">${renderedContent}</div>
            `;

            container.appendChild(messageDiv);
            container.scrollTop = container.scrollHeight;

            return messageDiv;
        };

        // Override appendToken to handle streaming
        chatView.appendTokenToLastMessage = (token) => {
            const container = document.getElementById('message-container');
            const lastMessage = container.querySelector('.message.streaming');

            if (lastMessage) {
                const contentDiv = lastMessage.querySelector('.message-content');

                // For streaming, accumulate raw text
                if (!contentDiv.dataset.rawContent) {
                    contentDiv.dataset.rawContent = '';
                }
                contentDiv.dataset.rawContent += token;

                // Render markdown on accumulated content
                const rendered = this.renderContent(contentDiv.dataset.rawContent, 'assistant', true);
                contentDiv.innerHTML = rendered;

                container.scrollTop = container.scrollHeight;
            }
        };

        // Override finishStreaming to do final markdown render
        const originalFinish = chatView.finishStreaming.bind(chatView);
        chatView.finishStreaming = () => {
            const container = document.getElementById('message-container');
            const streamingMessage = container.querySelector('.message.streaming');

            if (streamingMessage) {
                const contentDiv = streamingMessage.querySelector('.message-content');
                const rawContent = contentDiv.dataset.rawContent || contentDiv.textContent;

                // Final markdown render
                contentDiv.innerHTML = this.renderContent(rawContent, 'assistant', false);

                // Remove streaming class
                streamingMessage.classList.remove('streaming');

                // Clean up raw content
                delete contentDiv.dataset.rawContent;
            }
        };

        console.log('Text display enhancements loaded');
    }

    renderContent(content, role, isStreaming) {
        if (!content) return '';

        // For user messages, escape HTML but preserve line breaks
        if (role === 'user') {
            return this.escapeHtml(content).replace(/\n/g, '<br>');
        }

        // For assistant messages, render markdown
        if (typeof marked !== 'undefined') {
            try {
                // Render markdown
                let html = marked.parse(content);

                // Add syntax highlighting class to code blocks
                html = html.replace(/<pre><code class="language-(\w+)">/g,
                    '<pre><code class="language-$1 hljs">');

                return html;
            } catch (error) {
                console.error('Markdown rendering error:', error);
                return this.escapeHtml(content).replace(/\n/g, '<br>');
            }
        }

        // Fallback if marked.js not loaded
        return this.escapeHtml(content).replace(/\n/g, '<br>');
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    // Wait a bit for chatApp to initialize
    setTimeout(() => {
        new MessageRenderer();
    }, 200);
});
