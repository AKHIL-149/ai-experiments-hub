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

// What a model's reply may contain once it has been turned from markdown into HTML.
// A reply is untrusted text (a model can be talked into writing anything, and replies are
// saved and shown again), so it is always run through DOMPurify: scripts, on* handlers and
// javascript: links are removed. Images, styles and forms are not allowed at all - a remote
// image is the usual way a prompt-injected reply leaks data (the address carries it out).
const SANITIZE_OPTIONS = {
    FORBID_TAGS: ['img', 'style', 'form', 'input', 'button', 'textarea', 'select'],
    FORBID_ATTR: ['style']
};

if (typeof DOMPurify !== 'undefined' && DOMPurify.addHook) {
    // Links leave the chat in a new tab and cannot reach back into it
    DOMPurify.addHook('afterSanitizeAttributes', (node) => {
        if (node.tagName === 'A') {
            node.setAttribute('target', '_blank');
            node.setAttribute('rel', 'noopener noreferrer');
        }
    });
}

// ---------------------------------------------------------------------------------------------
// Copy button for assistant replies
// ---------------------------------------------------------------------------------------------

/**
 * Put text on the clipboard. Resolves true if it worked.
 * navigator.clipboard only exists on https:// pages and on localhost; anywhere else (the app
 * opened by its network address over http://) it is undefined, so fall back to the old
 * select-and-copy-a-textarea method, which works there.
 */
async function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch (error) {
            // permission denied, or the page is not focused: try the fallback
        }
    }

    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.cssText = 'position: fixed; top: 0; left: -9999px; opacity: 0;';
    document.body.appendChild(area);
    area.select();

    let copied = false;
    try {
        copied = document.execCommand('copy');
    } catch (error) {
        copied = false;
    }
    area.remove();
    return copied;
}

const COPY_LABELS = {
    idle: '\u{1F4CB} Copy',
    copied: '\u2713 Copied',
    failed: '\u26A0 Could not copy'
};
const COPY_FEEDBACK_MS = 1800;

/**
 * Add a "Copy" button under an assistant message. It copies the reply as the model wrote it
 * (the markdown source, kept in dataset.raw), not the rendered HTML, so code and tables paste
 * as they were written. Does nothing for an empty reply, and never adds a second button.
 */
function attachCopyButton(messageDiv, copy = copyToClipboard) {
    if (!messageDiv || messageDiv.querySelector('.copy-btn')) return null;
    if (!(messageDiv.dataset.raw || '').trim()) return null;

    const actions = document.createElement('div');
    actions.className = 'message-actions';
    actions.setAttribute('aria-live', 'polite');       // "Copied" is announced to screen readers

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'copy-btn';
    button.title = 'Copy this response';
    button.setAttribute('aria-label', 'Copy this response to the clipboard');
    button.textContent = COPY_LABELS.idle;

    let resetTimer = null;
    button.addEventListener('click', async () => {
        const ok = await copy(messageDiv.dataset.raw || '');
        button.textContent = ok ? COPY_LABELS.copied : COPY_LABELS.failed;
        button.classList.toggle('copied', ok);
        button.classList.toggle('failed', !ok);

        clearTimeout(resetTimer);
        resetTimer = setTimeout(() => {
            button.textContent = COPY_LABELS.idle;
            button.classList.remove('copied', 'failed');
        }, COPY_FEEDBACK_MS);
    });

    actions.appendChild(button);
    messageDiv.appendChild(actions);
    return button;
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

            // The reply as written, for the Copy button (a streaming reply fills it in when it ends)
            if (role === 'assistant') {
                messageDiv.dataset.raw = content || '';
                if (!streaming) attachCopyButton(messageDiv);
            }

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

                // The reply is complete: it can be copied now
                streamingMessage.dataset.raw = rawContent;
                attachCopyButton(streamingMessage);

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

        // For assistant messages, render markdown - but only ever hand back sanitised HTML.
        // If either library failed to load, show the reply as plain text rather than as markup.
        if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
            try {
                // Render markdown
                let html = marked.parse(content);

                // Add syntax highlighting class to code blocks
                html = html.replace(/<pre><code class="language-(\w+)">/g,
                    '<pre><code class="language-$1 hljs">');

                return DOMPurify.sanitize(html, SANITIZE_OPTIONS);
            } catch (error) {
                console.error('Markdown rendering error:', error);
                return this.escapeHtml(content).replace(/\n/g, '<br>');
            }
        }

        // Fallback if marked.js or DOMPurify did not load
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
