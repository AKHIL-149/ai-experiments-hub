/**
 * Conversation Manager UI - Frontend component for managing conversations
 */
class ConversationManagerUI {
  constructor() {
    this.conversations = [];
    this.currentConversationId = null;
    this.isVisible = false;

    this.init();
  }

  /**
   * Initialize conversation manager UI
   */
  init() {
    // Create UI elements
    this.createUI();
    this.attachEventListeners();
  }

  /**
   * Create conversation manager UI
   */
  createUI() {
    // Create conversation panel
    const panel = document.createElement('div');
    panel.id = 'conversationManagerPanel';
    panel.className = 'conversation-manager-panel hidden';
    panel.innerHTML = `
      <div class="conversation-manager-header">
        <h3>💬 Conversations</h3>
        <button class="btn-icon" id="closeConversationManager">✕</button>
      </div>
      <div class="conversation-manager-body">
        <div class="conversation-actions">
          <button class="btn-primary" id="newConversationBtn">+ New Conversation</button>
          <button class="btn-secondary" id="refreshConversationsBtn">🔄 Refresh</button>
        </div>
        <div class="conversation-stats" id="conversationStats">
          <div class="stat-item">
            <span class="stat-label">Total:</span>
            <span class="stat-value" id="totalConversations">0</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">Messages:</span>
            <span class="stat-value" id="totalMessages">0</span>
          </div>
        </div>
        <div class="conversation-list" id="conversationList">
          <div class="loading-placeholder">Loading conversations...</div>
        </div>
      </div>
    `;

    document.body.appendChild(panel);

    // Store references
    this.panel = panel;
    this.listContainer = document.getElementById('conversationList');
    this.statsContainer = document.getElementById('conversationStats');
  }

  /**
   * Attach event listeners
   */
  attachEventListeners() {
    // Close button
    document.getElementById('closeConversationManager').addEventListener('click', () => {
      this.hide();
    });

    // New conversation button
    document.getElementById('newConversationBtn').addEventListener('click', () => {
      this.createNewConversation();
    });

    // Refresh button
    document.getElementById('refreshConversationsBtn').addEventListener('click', () => {
      this.loadConversations();
    });
  }

  /**
   * Show conversation manager
   */
  async show() {
    this.isVisible = true;
    this.panel.classList.remove('hidden');
    await this.loadConversations();
    await this.loadStats();
  }

  /**
   * Hide conversation manager
   */
  hide() {
    this.isVisible = false;
    this.panel.classList.add('hidden');
  }

  /**
   * Toggle conversation manager
   */
  toggle() {
    if (this.isVisible) {
      this.hide();
    } else {
      this.show();
    }
  }

  /**
   * Load conversations from API
   */
  async loadConversations() {
    try {
      const response = await fetch('/api/conversations?limit=20');
      const data = await response.json();

      if (data.success) {
        this.conversations = data.conversations;
        this.renderConversations();
      } else {
        throw new Error('Failed to load conversations');
      }
    } catch (error) {
      console.error('Error loading conversations:', error);
      this.listContainer.innerHTML = `
        <div class="error-message">Failed to load conversations</div>
      `;
    }
  }

  /**
   * Load conversation statistics
   */
  async loadStats() {
    try {
      const response = await fetch('/api/conversations/stats');
      const data = await response.json();

      if (data.success) {
        this.renderStats(data.stats);
      }
    } catch (error) {
      console.error('Error loading stats:', error);
    }
  }

  /**
   * Render conversation statistics
   */
  renderStats(stats) {
    document.getElementById('totalConversations').textContent = stats.conversationCount;
    document.getElementById('totalMessages').textContent = stats.totalMessages;
  }

  /**
   * Render conversations list
   */
  renderConversations() {
    if (this.conversations.length === 0) {
      this.listContainer.innerHTML = `
        <div class="empty-state">
          <p>No conversations yet</p>
          <p class="empty-state-hint">Start speaking to create your first conversation</p>
        </div>
      `;
      return;
    }

    this.listContainer.innerHTML = '';

    this.conversations.forEach(conversation => {
      const item = this.createConversationItem(conversation);
      this.listContainer.appendChild(item);
    });
  }

  /**
   * Create conversation item element
   */
  createConversationItem(conversation) {
    const item = document.createElement('div');
    item.className = 'conversation-item';
    if (conversation.conversationId === this.currentConversationId) {
      item.classList.add('active');
    }

    const date = new Date(conversation.lastActivity);
    const dateStr = this.formatDate(date);
    const timeStr = this.formatTime(date);

    item.innerHTML = `
      <div class="conversation-item-header">
        <span class="conversation-id">${conversation.conversationId.substring(0, 16)}...</span>
        <span class="conversation-date">${dateStr}</span>
      </div>
      <div class="conversation-item-details">
        <span class="conversation-time">${timeStr}</span>
        <span class="conversation-messages">${conversation.messageCount} messages</span>
      </div>
      <div class="conversation-item-actions">
        <button class="btn-small" data-action="load" data-id="${conversation.conversationId}">Load</button>
        <button class="btn-small btn-danger" data-action="delete" data-id="${conversation.conversationId}">Delete</button>
      </div>
    `;

    // Attach action listeners
    item.querySelector('[data-action="load"]').addEventListener('click', (e) => {
      e.stopPropagation();
      this.loadConversation(conversation.conversationId);
    });

    item.querySelector('[data-action="delete"]').addEventListener('click', (e) => {
      e.stopPropagation();
      this.deleteConversation(conversation.conversationId);
    });

    return item;
  }

  /**
   * Format date for display
   */
  formatDate(date) {
    const now = new Date();
    const diff = now - date;
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));

    if (days === 0) return 'Today';
    if (days === 1) return 'Yesterday';
    if (days < 7) return `${days} days ago`;

    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }

  /**
   * Format time for display
   */
  formatTime(date) {
    return date.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    });
  }

  /**
   * Create new conversation
   */
  async createNewConversation() {
    try {
      const response = await fetch('/api/conversations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userId: 'default' })
      });

      const data = await response.json();

      if (data.success) {
        // Notify parent (VoiceAssistant) about new conversation
        window.dispatchEvent(new CustomEvent('conversationCreated', {
          detail: { conversationId: data.conversationId }
        }));

        await this.loadConversations();
        await this.loadStats();
      }
    } catch (error) {
      console.error('Error creating conversation:', error);
    }
  }

  /**
   * Load conversation
   */
  async loadConversation(conversationId) {
    try {
      const response = await fetch(`/api/conversations/${conversationId}`);
      const data = await response.json();

      if (data.success) {
        // Notify parent (VoiceAssistant) to switch conversation
        window.dispatchEvent(new CustomEvent('conversationLoaded', {
          detail: {
            conversationId: conversationId,
            messages: data.messages
          }
        }));

        this.currentConversationId = conversationId;
        this.renderConversations();
        this.hide();
      }
    } catch (error) {
      console.error('Error loading conversation:', error);
    }
  }

  /**
   * Delete conversation
   */
  async deleteConversation(conversationId) {
    if (!confirm('Are you sure you want to delete this conversation?')) {
      return;
    }

    try {
      const response = await fetch(`/api/conversations/${conversationId}`, {
        method: 'DELETE'
      });

      const data = await response.json();

      if (data.success) {
        // If deleted conversation was current, create new one
        if (conversationId === this.currentConversationId) {
          await this.createNewConversation();
        }

        await this.loadConversations();
        await this.loadStats();
      }
    } catch (error) {
      console.error('Error deleting conversation:', error);
    }
  }

  /**
   * Set current conversation ID
   */
  setCurrentConversation(conversationId) {
    this.currentConversationId = conversationId;
    if (this.isVisible) {
      this.renderConversations();
    }
  }
}

// Export for use in main app
if (typeof window !== 'undefined') {
  window.ConversationManagerUI = ConversationManagerUI;
}
